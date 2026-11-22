"""The Core API, independent of any transport: a request in, a response out.

Order of every request: identity (signed, fresh, single-use, not revoked), version negotiation, routing, contract validation, the service. Errors are always a
UserSafeError from the fixed taxonomy; the text of an exception, a question or a source never reaches a response or a log.
"""

from __future__ import annotations

import base64
import json
import re
import time
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from urllib.parse import parse_qs, urlsplit

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from . import API_VERSION, SUPPORTED_VERSIONS
from .contracts import ContractError, validate
from .errors import CoreError, status_of, user_error
from .events import SafeLog, new_id
from .identity import H_VERSION, BootstrapGate, ClientRegistry
from .service import TERMINAL, ConsentPort, DevicesPort, ModePort, OpsPort, TaskService

JSON = "application/json"
SSE = "text/event-stream"
MAX_BODY_BYTES = 64 * 1024
FOLLOW_SECONDS = 30.0  # a stream of an unfinished task is followed this long, then ends (the client resumes with ?after=)
FOLLOW_POLL = 0.05
HTTP_ERROR = 400  # a code whose status is below this is a task outcome, reported on the stream; as a direct reply it is a conflict
ROUTE = re.compile(r"^/v1/(?:(version)|(tasks)|tasks/([A-Za-z0-9_-]{8,64})(?:/(cancel|answer|receipt|events)|/citations/([0-9]{1,4}))?)$")
CONSENT = re.compile(
    r"^/v1/(?:(consent)|consent/([A-Za-z0-9_-]{8,64})|(index/status)|(mode))$"
)  # API 1.1 only, and only when the Core was given a consent service
H_NONCE_NAME = "x-atlas-nonce"
COMPUTE = "/v1/compute"  # API 1.1 only
RESEARCH = re.compile(r"^/v1/tasks/([A-Za-z0-9_-]{8,64})/research$")  # API 1.1 only
ENROL = "/v1/enrol"  # API 1.1 only
DEVICE_PAIR = "/v1/devices/pair"  # API 1.1 only, unsigned (the device is not enrolled yet), guarded by the single-use code
DEVICE_PATHS = frozenset({"/v1/devices", "/v1/devices/offer", "/v1/devices/revoke"})  # API 1.1 only, an enrolled OWNER client only
OPS_PATHS = frozenset(
    {"/v1/actions", "/v1/actions/approve", "/v1/actions/undo", "/v1/sync"}
)  # API 1.1 only, and only when the Core was given the owner's edits store


@dataclass(frozen=True)
class Request:
    method: str
    target: str
    headers: Mapping[str, str]
    body: bytes = b""


@dataclass
class Response:
    status: int
    headers: dict[str, str] = field(default_factory=dict)
    body: bytes = b""
    stream: Iterator[bytes] | None = None


def _json(status: int, value: Any) -> Response:
    return Response(status, {"content-type": JSON}, json.dumps(value).encode())


def _error(code: str, task_id: str | None = None) -> Response:
    return _json(status_of(code) if status_of(code) >= HTTP_ERROR else 409, user_error(code, task_id))


def framing_error() -> Response:
    """The reply for a request whose framing the transport refused before reading any body (the same fixed, user-safe error as any other bad request)."""
    return _error("invalid_request")


def _applied(request: Request, headers: dict[str, str]) -> str:
    """The contract version this request is handled under: 1.1 only when the client asked for exactly `1.1` and the Core serves it; `/v1/version` is never negotiated."""
    if headers.get(H_VERSION) == "1.1" and "1.1" in SUPPORTED_VERSIONS and urlsplit(request.target).path != "/v1/version":
        return "1.1"
    return "1.0"


class CoreApi:
    def __init__(  # noqa: PLR0913, PLR0917  (each part is a separate injected seam)
        self,
        service: TaskService,
        registry: ClientRegistry,
        log: SafeLog,
        clock: Callable[[], datetime] | None = None,
        check_responses: bool = False,
        consent: ConsentPort | None = None,
        bootstrap: BootstrapGate | None = None,
        mode: ModePort | None = None,
        ops: OpsPort | None = None,
        devices: DevicesPort | None = None,
    ) -> None:
        self._service, self._registry, self._log, self._consent, self._bootstrap, self._mode, self._ops, self._devices = (
            service,
            registry,
            log,
            consent,
            bootstrap,
            mode,
            ops,
            devices,
        )
        self._clock = clock or (lambda: datetime.now(UTC))
        self._check = check_responses  # tests: every JSON response must match its contract type

    def handle(self, request: Request) -> Response:
        correlation, began = new_id(), time.perf_counter()
        headers = {k.lower(): v for k, v in request.headers.items()}
        version = _applied(request, headers)
        try:
            response = self._dispatch(request, headers, correlation, version)
        except CoreError as e:
            self._log.emit("client.rejected" if e.code in ("unauthenticated", "forbidden") else "api.request", "api", correlation, error_code=e.code)
            response = _error(e.code, e.task_id)
        except ContractError:
            response = _error("invalid_request")
        except Exception:  # noqa: BLE001  (the one place that must never leak: whatever happened, the owner sees a fixed message)
            self._log.emit("api.request", "api", correlation, error_code="internal_error")
            response = _error("internal_error")
        if version == "1.1":
            response.headers[H_VERSION] = version  # the version applied, on every response except /v1/version (CONTRACT_1_1.md, Echo)
        self._log.emit("api.request", "api", correlation, status=response.status, duration_ms=round((time.perf_counter() - began) * 1000, 3))
        return response

    def _extension_route(self, request: Request, path: str, client: str, version: str) -> Response | None:
        """The API 1.1 routes outside the task and consent families: compute, the owner's actions and sync, and public research. None means the path is not one of them."""
        if version != "1.1":
            return None
        if path == COMPUTE:
            return self._compute(request)
        if path in OPS_PATHS:
            return self._ops_route(request, path, client)
        if path in DEVICE_PATHS:
            return self._device_route(request, path, client)
        research = RESEARCH.match(path)
        return None if research is None else self._research(request, research.group(1), client, version)

    def _dispatch(self, request: Request, headers: dict[str, str], correlation: str, version: str) -> Response:
        if len(request.body) > MAX_BODY_BYTES:
            raise CoreError("invalid_request")
        parts = urlsplit(request.target)
        if parts.path == ENROL and request.method == "POST" and version == "1.1":
            return self._enrol(request, headers, version)  # decides for itself whether a signature is required
        if parts.path == DEVICE_PAIR and request.method == "POST" and version == "1.1":
            return self._pair(request)
        client = self._registry.verify(request.method, request.target, headers, request.body, self._clock(), version)
        match = ROUTE.match(parts.path)
        extension = self._extension_route(request, parts.path, client, version)
        if extension is not None:
            return extension
        if match is None:
            owned = CONSENT.match(parts.path)
            if owned is None or version != "1.1" or self._consent is None:
                raise CoreError("not_found")
            return self._consent_route(request, owned, client, headers.get(H_NONCE_NAME, ""))
        if match.group(1):
            return self._version(request)
        wanted = headers.get(H_VERSION)
        if wanted is not None and wanted not in SUPPORTED_VERSIONS:
            raise CoreError("unsupported_version")
        return self._route(request, match, parse_qs(parts.query), correlation, version)

    def _consent_route(self, request: Request, match: re.Match[str], client: str, nonce: str) -> Response:
        """The consent and index-status routes (1.1). Reading the index status is for any enrolled client; the consent state and every change need an enrolled OWNER client.
        The signed request's nonce is the single-use id of a change, so replaying a request changes nothing (the identity layer already refuses it, the store refuses it again)."""
        port, method = self._consent, request.method
        if port is None:
            raise CoreError("not_found")
        if match.group(3):
            if method != "GET":
                raise CoreError("invalid_request")
            return self._reply(200, port.index_status(), "IndexStatus", "1.1")
        if not self._registry.is_owner(client):
            raise CoreError("forbidden")
        if match.group(4):
            return self._mode_route(request)
        request_id = f"n-{client}-{nonce}"[-64:] if nonce else ""
        if match.group(1) and method == "GET":
            return self._reply(200, port.state(), "ConsentState", "1.1")
        if match.group(1) and method == "POST":
            try:
                body = json.loads(request.body)
            except ValueError:
                raise CoreError("invalid_request") from None
            validate("ConsentRequest", body, "1.1")
            return self._reply(201, port.enable(list(body["sources"]), request_id), "ConsentState", "1.1")
        if match.group(2) and method == "DELETE":
            return self._reply(200, port.revoke(match.group(2), request_id), "ConsentState", "1.1")
        raise CoreError("invalid_request")

    def _mode_route(self, request: Request) -> Response:
        """The owner's model mode: owner-only (checked by the caller). A change takes effect on the next model call and is lost on restart (back to `default`)."""
        if self._mode is None:
            raise CoreError("not_found")
        if request.method == "GET":
            return self._reply(200, {"mode": self._mode.get()}, "ModeState", "1.1")
        if request.method != "POST":
            raise CoreError("invalid_request")
        try:
            body = json.loads(request.body)
        except ValueError:
            raise CoreError("invalid_request") from None
        validate("ModeState", body, "1.1")
        self._mode.set(body["mode"])
        return self._reply(200, {"mode": self._mode.get()}, "ModeState", "1.1")

    def _version(self, request: Request) -> Response:
        if request.method != "GET":
            raise CoreError("invalid_request")
        return self._reply(200, {"api_version": API_VERSION, "supported": list(SUPPORTED_VERSIONS)}, "ApiVersion")

    def _route(self, request: Request, match: re.Match[str], query: dict[str, list[str]], correlation: str, version: str) -> Response:
        method, task_id, action = request.method, match.group(3), match.group(4)
        if match.group(5) is not None:
            return self._passage(method, task_id or "", int(match.group(5)), version)
        if match.group(2):
            if method != "POST":
                raise CoreError("invalid_request")
            return self._create(request.body, version)
        if task_id is None:
            raise CoreError("not_found")
        service = self._service
        answer = service.answer_v11 if version == "1.1" else service.answer
        actions: dict[tuple[str | None, str], tuple[Callable[[str], dict[str, Any]], str]] = {
            (None, "GET"): (service.get, "TaskRecord"),
            ("cancel", "POST"): (service.cancel, "TaskRecord"),
            ("answer", "GET"): (answer, "AnswerEnvelope"),
            ("receipt", "GET"): (service.receipt, "ExecutionReceipt"),
        }
        if (action, method) in actions:
            handler, contract = actions[(action, method)]
            return self._reply(200, handler(task_id), contract, version)
        if action == "events" and method == "GET":
            return self._events(task_id, query, correlation, version)
        raise CoreError("invalid_request")

    def _enrol(self, request: Request, headers: dict[str, str], version: str) -> Response:
        """Enrol a client by its public key. While NO owner client is enrolled, an unsigned request (it still arrives over the owner-only socket, whose peer user was checked) may enrol
        the first owner client, exactly once. After that only a signed request from an enrolled owner client may enrol a client, and only as a member."""
        try:
            body = json.loads(request.body)
        except ValueError:
            raise CoreError("invalid_request") from None
        validate("EnrolRequest", body, version)
        try:
            key = Ed25519PublicKey.from_public_bytes(base64.b64decode(body["public_key"], validate=True))
        except ValueError:
            raise CoreError("invalid_request") from None
        if not self._registry.has_owner():
            if body["role"] != "owner":
                raise CoreError("invalid_request")
            if self._bootstrap is not None and not self._bootstrap.check(body.get("bootstrap_code")):
                raise CoreError("unauthenticated")  # a missing or wrong first-run code: nothing about why
            if not self._registry.enrol_first_owner(body["client_id"], key):
                raise CoreError("conflict")
            if self._bootstrap is not None:
                self._bootstrap.consume()
        else:
            caller = self._registry.verify(request.method, request.target, headers, request.body, self._clock(), version)
            if not self._registry.is_owner(caller):
                raise CoreError("forbidden")
            if body["role"] != "member":
                raise CoreError("invalid_request")
            if not self._registry.enrol(body["client_id"], key):
                raise CoreError("conflict")
        return self._reply(201, {"client_id": body["client_id"], "role": body["role"]}, "EnrolResponse", version)

    def _compute(self, request: Request) -> Response:
        if request.method != "POST":
            raise CoreError("invalid_request")
        try:
            body = json.loads(request.body)
        except ValueError:
            raise CoreError("invalid_request") from None
        validate("ComputeRequest", body, "1.1")
        return self._reply(200, self._service.compute(body["kind"], body["args"]), "ComputeResult", "1.1")

    def _pair(self, request: Request) -> Response:
        if self._devices is None:
            raise CoreError("not_found")
        try:
            body = json.loads(request.body)
        except ValueError:
            raise CoreError("invalid_request") from None
        validate("PairRequest", body, "1.1")
        return self._reply(200, self._devices.pair(body), "PairResult", "1.1")

    def _device_route(self, request: Request, path: str, client: str) -> Response:
        if self._devices is None:
            raise CoreError("not_found")
        if not self._registry.is_owner(client):
            raise CoreError("forbidden")
        if path == "/v1/devices":
            if request.method != "GET":
                raise CoreError("invalid_request")
            return self._reply(200, self._devices.listing(), "DeviceList", "1.1")
        if request.method != "POST":
            raise CoreError("invalid_request")
        if path == "/v1/devices/offer":
            return self._reply(200, self._devices.offer(client), "DeviceOffer", "1.1")
        try:
            body = json.loads(request.body)
        except ValueError:
            raise CoreError("invalid_request") from None
        validate("RevokeRequest", body, "1.1")
        return self._reply(200, self._devices.revoke(client, body["device_id"]), "RevokeResult", "1.1")

    def _ops_route(self, request: Request, path: str, client: str) -> Response:
        """The owner's actions (propose, approve, undo: an enrolled OWNER client only; the origin is always the owner's own request) and a device's sync (any enrolled client; the device is the authenticated client)."""
        if self._ops is None:
            raise CoreError("not_found")
        if request.method != "POST":
            raise CoreError("invalid_request")
        try:
            body = json.loads(request.body)
        except ValueError:
            raise CoreError("invalid_request") from None
        if path == "/v1/sync":
            validate("SyncRequest", body, "1.1")
            return self._reply(200, self._ops.sync(client, body["ops"]), "SyncResult", "1.1")
        if not self._registry.is_owner(client):
            raise CoreError("forbidden")
        if path == "/v1/actions":
            validate("ActionRequest", body, "1.1")
            return self._reply(200, self._ops.act(body["action"], body["payload"], body["idempotency_key"], body.get("approval_id")), "ActionOutcome", "1.1")
        if path == "/v1/actions/approve":
            validate("ApprovalRequest", body, "1.1")
            return self._reply(200, self._ops.approve(body["approval_id"]), "ApprovalResult", "1.1")
        validate("UndoRequest", body, "1.1")
        return self._reply(200, self._ops.undo(body["action_id"]), "ActionOutcome", "1.1")

    def _research(self, request: Request, task_id: str, client: str, version: str) -> Response:
        """`POST /v1/tasks/{id}/research`: API 1.1 only, an enrolled OWNER client only. Off unless the Core's live-network gate is on (then `forbidden`)."""
        if version != "1.1":
            raise CoreError("not_found")
        if request.method != "POST":
            raise CoreError("invalid_request")
        if not self._registry.is_owner(client):
            raise CoreError("forbidden")
        try:
            body = json.loads(request.body)
        except ValueError:
            raise CoreError("invalid_request") from None
        validate("ResearchRequest", body, "1.1")
        if body["task_id"] != task_id:
            raise CoreError("invalid_request")
        return self._reply(200, self._service.research(task_id, body["query"]), "ResearchResult", "1.1")

    def _passage(self, method: str, task_id: str, index: int, version: str) -> Response:
        """`/citations/{index}`: API 1.1 only."""
        if version != "1.1":
            raise CoreError("not_found")
        if method != "GET":
            raise CoreError("invalid_request")
        return self._reply(200, self._service.passage(task_id, index), "PassageText", version)

    def _create(self, body: bytes, version: str) -> Response:
        try:
            request = json.loads(body)
        except ValueError:
            raise CoreError("invalid_request") from None
        validate("TaskRequest", request, version)
        record, created = self._service.submit(request)
        return self._reply(201 if created else 200, record, "TaskRecord", version)

    def _reply(self, status: int, value: dict[str, Any], contract: str, version: str = "1.0") -> Response:
        if self._check:
            validate(contract, value, version)
        return _json(status, value)

    def _events(self, task_id: str, query: dict[str, list[str]], correlation: str, version: str) -> Response:
        try:
            after = int(query.get("after", ["0"])[0])
        except ValueError:
            raise CoreError("invalid_request") from None
        self._service.get(task_id)  # 404 before the stream opens
        self._log.emit("stream.opened", "stream", correlation, count=after)
        return Response(200, {"content-type": SSE, "cache-control": "no-store"}, stream=self._follow(task_id, after, version))

    def _follow(self, task_id: str, after: int, version: str) -> Iterator[bytes]:
        deadline = time.monotonic() + FOLLOW_SECONDS
        while True:
            for event in self._service.events_after(task_id, after, version):
                after = event["seq"]
                yield f"id: {after}\ndata: {json.dumps(event)}\n\n".encode()
            if self._service.get(task_id)["state"] in TERMINAL and not self._service.events_after(task_id, after, version):
                return
            if time.monotonic() > deadline:
                return
            time.sleep(FOLLOW_POLL)
