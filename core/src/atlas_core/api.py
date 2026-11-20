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
from .service import TERMINAL, TaskService

JSON = "application/json"
SSE = "text/event-stream"
MAX_BODY_BYTES = 64 * 1024
FOLLOW_SECONDS = 30.0  # a stream of an unfinished task is followed this long, then ends (the client resumes with ?after=)
FOLLOW_POLL = 0.05
HTTP_ERROR = 400  # a code whose status is below this is a task outcome, reported on the stream; as a direct reply it is a conflict
ROUTE = re.compile(r"^/v1/(?:(version)|(tasks)|tasks/([A-Za-z0-9_-]{8,64})(?:/(cancel|answer|receipt|events))?)$")


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


class CoreApi:
    def __init__(
        self, service: TaskService, registry: ClientRegistry, log: SafeLog, clock: Callable[[], datetime] | None = None, check_responses: bool = False
    ) -> None:
        self._service, self._registry, self._log = service, registry, log
        self._clock = clock or (lambda: datetime.now(UTC))
        self._check = check_responses  # tests: every JSON response must match its contract type

    def handle(self, request: Request) -> Response:
        correlation, began = new_id(), time.perf_counter()
        headers = {k.lower(): v for k, v in request.headers.items()}
        try:
            response = self._dispatch(request, headers, correlation)
        except CoreError as e:
            self._log.emit("client.rejected" if e.code in ("unauthenticated", "forbidden") else "api.request", "api", correlation, error_code=e.code)
            response = _error(e.code, e.task_id)
        except ContractError:
            response = _error("invalid_request")
        except Exception:  # noqa: BLE001  (the one place that must never leak: whatever happened, the owner sees a fixed message)
            self._log.emit("api.request", "api", correlation, error_code="internal_error")
            response = _error("internal_error")
        self._log.emit("api.request", "api", correlation, status=response.status, duration_ms=round((time.perf_counter() - began) * 1000, 3))
        return response

    def _dispatch(self, request: Request, headers: dict[str, str], correlation: str) -> Response:
        if len(request.body) > MAX_BODY_BYTES:
            raise CoreError("invalid_request")
        self._registry.verify(request.method, request.target, headers, request.body, self._clock())
        parts = urlsplit(request.target)
        match = ROUTE.match(parts.path)
        if match is None:
            raise CoreError("not_found")
        if match.group(1):
            return self._version(request)
        wanted = headers.get(H_VERSION)
        if wanted is not None and wanted not in SUPPORTED_VERSIONS:
            raise CoreError("unsupported_version")
        return self._route(request, match, parse_qs(parts.query), correlation)

    def _version(self, request: Request) -> Response:
        if request.method != "GET":
            raise CoreError("invalid_request")
        return self._reply(200, {"api_version": API_VERSION, "supported": list(SUPPORTED_VERSIONS)}, "ApiVersion")

    def _route(self, request: Request, match: re.Match[str], query: dict[str, list[str]], correlation: str) -> Response:
        method, task_id, action = request.method, match.group(3), match.group(4)
        if match.group(2):
            if method != "POST":
                raise CoreError("invalid_request")
            return self._create(request.body)
        if task_id is None:
            raise CoreError("not_found")
        if action is None and method == "GET":
            return self._reply(200, self._service.get(task_id), "TaskRecord")
        if action == "cancel" and method == "POST":
            return self._reply(200, self._service.cancel(task_id), "TaskRecord")
        if action == "answer" and method == "GET":
            return self._reply(200, self._service.answer(task_id), "AnswerEnvelope")
        if action == "receipt" and method == "GET":
            return self._reply(200, self._service.receipt(task_id), "ExecutionReceipt")
        if action == "events" and method == "GET":
            return self._events(task_id, query, correlation)
        raise CoreError("invalid_request")

    def _create(self, body: bytes) -> Response:
        try:
            request = json.loads(body)
        except ValueError:
            raise CoreError("invalid_request") from None
        validate("TaskRequest", request)
        record, created = self._service.submit(request)
        return self._reply(201 if created else 200, record, "TaskRecord")

    def _reply(self, status: int, value: dict[str, Any], contract: str) -> Response:
        if self._check:
            validate(contract, value)
        return _json(status, value)

    def _events(self, task_id: str, query: dict[str, list[str]], correlation: str) -> Response:
        try:
            after = int(query.get("after", ["0"])[0])
        except ValueError:
            raise CoreError("invalid_request") from None
        self._service.get(task_id)  # 404 before the stream opens
        self._log.emit("stream.opened", "stream", correlation, count=after)
        return Response(200, {"content-type": SSE, "cache-control": "no-store"}, stream=self._follow(task_id, after))

    def _follow(self, task_id: str, after: int) -> Iterator[bytes]:
        deadline = time.monotonic() + FOLLOW_SECONDS
        while True:
            for event in self._service.events_after(task_id, after):
                after = event["seq"]
                yield f"id: {after}\ndata: {json.dumps(event)}\n\n".encode()
            if self._service.get(task_id)["state"] in TERMINAL and not self._service.events_after(task_id, after):
                return
            if time.monotonic() > deadline:
                return
            time.sleep(FOLLOW_POLL)
