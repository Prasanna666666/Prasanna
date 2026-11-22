"""The Core API, independent of any transport: a request in, a response out.

Order of every request: identity (signed, fresh, single-use, not revoked), version negotiation, routing, contract validation, the service. Errors are always a
UserSafeError from the fixed taxonomy; the text of an exception, a question or a source never reaches a response or a log.
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from urllib.parse import parse_qs, urlsplit

from . import API_VERSION, SUPPORTED_VERSIONS
from .contracts import ContractError, validate
from .errors import CoreError, status_of, user_error
from .events import SafeLog, new_id
from .identity import H_VERSION, ClientRegistry
from .service import TERMINAL, ConsentPort, TaskService

JSON = "application/json"
SSE = "text/event-stream"
MAX_BODY_BYTES = 64 * 1024
FOLLOW_SECONDS = 30.0  # a stream of an unfinished task is followed this long, then ends (the client resumes with ?after=)
FOLLOW_POLL = 0.05
HTTP_ERROR = 400  # a code whose status is below this is a task outcome, reported on the stream; as a direct reply it is a conflict
ROUTE = re.compile(r"^/v1/(?:(version)|(tasks)|tasks/([A-Za-z0-9_-]{8,64})(?:/(cancel|answer|receipt|events))?)$")
CONSENT = re.compile(r"^/v1/(?:(consent)|consent/([A-Za-z0-9_-]{8,64})|(index/status))$")  # API 1.1 only, and only when the Core was given a consent service
H_NONCE_NAME = "x-atlas-nonce"


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
    def __init__(
        self,
        service: TaskService,
        registry: ClientRegistry,
        log: SafeLog,
        clock: Callable[[], datetime] | None = None,
        check_responses: bool = False,
        consent: ConsentPort | None = None,
    ) -> None:
        self._service, self._registry, self._log, self._consent = service, registry, log, consent
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

    def _dispatch(self, request: Request, headers: dict[str, str], correlation: str, version: str) -> Response:
        if len(request.body) > MAX_BODY_BYTES:
            raise CoreError("invalid_request")
        client = self._registry.verify(request.method, request.target, headers, request.body, self._clock(), version)
        parts = urlsplit(request.target)
        match = ROUTE.match(parts.path)
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

    def _version(self, request: Request) -> Response:
        if request.method != "GET":
            raise CoreError("invalid_request")
        return self._reply(200, {"api_version": API_VERSION, "supported": list(SUPPORTED_VERSIONS)}, "ApiVersion")

    def _route(self, request: Request, match: re.Match[str], query: dict[str, list[str]], correlation: str, version: str) -> Response:
        method, task_id, action = request.method, match.group(3), match.group(4)
        if match.group(2):
            if method != "POST":
                raise CoreError("invalid_request")
            return self._create(request.body, version)
        if task_id is None:
            raise CoreError("not_found")
        if action is None and method == "GET":
            return self._reply(200, self._service.get(task_id), "TaskRecord", version)
        if action == "cancel" and method == "POST":
            return self._reply(200, self._service.cancel(task_id), "TaskRecord", version)
        if action == "answer" and method == "GET":
            return self._reply(200, self._service.answer_v11(task_id) if version == "1.1" else self._service.answer(task_id), "AnswerEnvelope", version)
        if action == "receipt" and method == "GET":
            return self._reply(200, self._service.receipt(task_id), "ExecutionReceipt", version)
        if action == "events" and method == "GET":
            return self._events(task_id, query, correlation, version)
        raise CoreError("invalid_request")

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
