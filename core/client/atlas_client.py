"""A reference client for the Core API over its Unix socket (WP3.5). It speaks the real signed contract, so the whole conversation path can be exercised without the Mac app.

It is NOT the macOS app: the SwiftUI interface, Keychain key storage, permission dialogs and accessibility are built and verified on a Mac. This module fixes what the app must
do with the contract: sign every request (the applied version too), refuse a response whose version echo is wrong, show progress, cancel, show citations with their quotes, always
say which local model answered, and turn every state, error and limitation into plain words from `ux_catalogue.json`. Nothing here ever shows a raw error body, a stack trace, a
path or a source's content other than the cited quote.
"""

from __future__ import annotations

import base64
import http.client
import json
import socket
import time
import uuid
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from atlas_core.identity import sign_request

CATALOGUE = json.loads((Path(__file__).with_name("ux_catalogue.json")).read_text(encoding="utf-8"))
TERMINAL = ("completed", "partially_completed", "failed", "cancelled", "expired")
ECHO = "x-atlas-api-version"
DEFAULT_BUDGET = {"max_seconds": 120, "max_retries": 1}


class ClientError(Exception):
    """What the owner is told. `message` is catalogue text only; `code` is the Core's error code (or `connection`); nothing from the wire is kept."""

    def __init__(self, code: str, message: str, retryable: bool = False) -> None:
        super().__init__(message)
        self.code, self.message, self.retryable = code, message, retryable


def message_for(code: str) -> str:
    return CATALOGUE["errors"].get(code, CATALOGUE["errors"]["internal_error"])


class _Unix(http.client.HTTPConnection):
    def __init__(self, path: str, timeout: float) -> None:
        super().__init__("localhost", timeout=timeout)
        self._path = path

    def connect(self) -> None:
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(self._path)


class AtlasClient:
    def __init__(
        self, socket_path: str, key: Ed25519PrivateKey, client_id: str, version: str = "1.1", clock: Callable[[], datetime] | None = None, timeout: float = 10.0
    ) -> None:
        self._path, self._key, self._id, self.version, self._timeout = socket_path, key, client_id, version, timeout
        self._clock = clock or (lambda: datetime.now(UTC))

    # -- transport -------------------------------------------------------------------------------------------------------------------------
    def _call(self, method: str, target: str, body: dict[str, Any] | None = None, *, discovery: bool = False, signed: bool = True) -> http.client.HTTPResponse:
        raw = json.dumps(body).encode() if body is not None else b""
        applied = "1.0" if discovery else self.version
        headers = sign_request(self._key, self._id, method, target, raw, self._clock(), version=applied) if signed else {"x-atlas-api-version": applied}
        connection = _Unix(self._path, self._timeout)
        try:
            connection.request(method, target, body=raw or None, headers={**headers, "content-type": "application/json"})
            response = connection.getresponse()
        except (OSError, http.client.HTTPException):
            connection.close()
            raise ClientError("connection", "Atlas is not running or cannot be reached. Open Atlas and try again.", True) from None
        response._conn = connection  # type: ignore[attr-defined]  # closed by the caller with _done
        if not discovery and self.version == "1.1" and response.getheader(ECHO) != "1.1":
            self._done(response)
            raise ClientError("internal_error", message_for("unsupported_version"))  # a 1.1 client rejects a response whose echo is absent or different
        return response

    @staticmethod
    def _done(response: http.client.HTTPResponse) -> None:
        response.close()
        response._conn.close()  # type: ignore[attr-defined]

    def _json(self, method: str, target: str, body: dict[str, Any] | None = None, *, discovery: bool = False, signed: bool = True) -> Any:
        response = self._call(method, target, body, discovery=discovery, signed=signed)
        try:
            status, data = response.status, response.read()
        finally:
            self._done(response)
        try:
            value = json.loads(data or b"{}")
        except ValueError:
            raise ClientError("internal_error", message_for("internal_error"), True) from None
        if status >= 400:  # noqa: PLR2004
            code = value.get("code") if isinstance(value, dict) else None
            raise ClientError(
                code if code in CATALOGUE["errors"] else "internal_error", message_for(code or ""), bool(isinstance(value, dict) and value.get("retryable"))
            )
        return value

    # -- the conversation path ------------------------------------------------------------------------------------------------------------
    def discover(self) -> dict[str, Any]:
        return self._json("GET", "/v1/version", discovery=True)

    def ask(self, question: str, scope: list[str], idempotency_key: str | None = None, budget: dict[str, int] | None = None) -> str:
        record = self._json(
            "POST",
            "/v1/tasks",
            {"objective": question, "source_scope": scope, "budget": budget or DEFAULT_BUDGET, "idempotency_key": idempotency_key or uuid.uuid4().hex},
        )
        return str(record["task_id"])

    def passage(self, task_id: str, index: int) -> str:
        """The cited span's text, for the "show the source passage" action (API 1.1)."""
        return str(self._json("GET", f"/v1/tasks/{task_id}/citations/{index}")["text"])

    def compute(self, kind: str, *args: str) -> dict[str, Any]:
        """An exact computation done by code (never by a model): arithmetic, convert, days_between, add_days, add_months, weekday (API 1.1)."""
        return self._json("POST", "/v1/compute", {"kind": kind, "args": list(args)})

    def research(self, task_id: str, query: str) -> dict[str, Any]:
        """A public web search for one task (API 1.1; owner client only; refused unless the Core's live-network gate is on). The result is untrusted data, never evidence."""
        return self._json("POST", f"/v1/tasks/{task_id}/research", {"task_id": task_id, "query": query})

    def act(self, action: str, payload: dict[str, Any], idempotency_key: str | None = None, approval_id: str | None = None) -> dict[str, Any]:
        """Propose one typed action as the owner (API 1.1; owner client only). The answer is `done`, `needs_approval` (with the exact payload and an approval id), `refused` or `failed`, with a code."""
        body: dict[str, Any] = {"action": action, "payload": payload, "idempotency_key": idempotency_key or uuid.uuid4().hex}
        if approval_id is not None:
            body["approval_id"] = approval_id
        return self._json("POST", "/v1/actions", body)

    def approve(self, approval_id: str) -> bool:
        """The owner approves one pending approval id; then the SAME action and payload are proposed again with it."""
        return bool(self._json("POST", "/v1/actions/approve", {"approval_id": approval_id})["granted"])

    def undo(self, action_id: str) -> dict[str, Any]:
        return self._json("POST", "/v1/actions/undo", {"action_id": action_id})

    def sync(self, ops: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Send a device's offline queue (API 1.1): each operation is applied once, in order; the results say applied, duplicate, conflict or rejected."""
        return list(self._json("POST", "/v1/sync", {"ops": ops})["results"])

    def library_search(self, query: str, scope: list[str]) -> dict[str, Any]:
        """Search the enabled sources (API 1.1): results with a title and excerpt, plus how much of each source has been read."""
        return self._json("POST", "/v1/library/search", {"query": query, "scope": scope})

    def open_pairing_offer(self) -> dict[str, Any]:
        """An owner client opens a pairing offer for a new device (API 1.1): a single-use code, five minutes, and the Core's fingerprint to pin."""
        return self._json("POST", "/v1/devices/offer", {})

    def pair_device(self, code: str, device_id: str, label: str, public_key_b64: str, nonce: str) -> dict[str, Any]:
        """A NEW device pairs with the offer code (unsigned: it is not enrolled yet)."""
        return self._json(
            "POST", "/v1/devices/pair", {"code": code, "device_id": device_id, "label": label, "public_key": public_key_b64, "nonce": nonce}, signed=False
        )

    def devices(self) -> list[dict[str, Any]]:
        return list(self._json("GET", "/v1/devices")["devices"])

    def revoke_device(self, device_id: str) -> bool:
        return bool(self._json("POST", "/v1/devices/revoke", {"device_id": device_id})["revoked"])

    def enrol_self(self, role: str = "owner", bootstrap_code: str | None = None) -> dict[str, Any]:
        """First run: enrol THIS client's public key with the Core (unsigned, once, while no owner client exists; over the owner-only socket). Afterwards an owner client may
        enrol a member with a signed call (`enrol`)."""
        body = self._enrol_body(self._id, role)
        if bootstrap_code is not None:
            body["bootstrap_code"] = bootstrap_code  # the single-use code the process that started the Core handed to this app
        return self._json("POST", "/v1/enrol", body, signed=False)

    def enrol(self, client_id: str, public_key: Ed25519PublicKey, role: str = "member") -> dict[str, Any]:
        return self._json("POST", "/v1/enrol", self._enrol_body(client_id, role, public_key))

    def _enrol_body(self, client_id: str, role: str, public_key: Ed25519PublicKey | None = None) -> dict[str, Any]:
        raw = (public_key or self._key.public_key()).public_bytes_raw()
        return {"client_id": client_id, "public_key": base64.b64encode(raw).decode(), "role": role}

    def mode(self) -> str:
        """The owner's selected model mode (owner client only)."""
        return str(self._json("GET", "/v1/mode")["mode"])

    def set_mode(self, mode: str) -> str:
        """Select `default` or `research` (the deep model tier). Owner client only."""
        return str(self._json("POST", "/v1/mode", {"mode": mode})["mode"])

    def consent(self) -> dict[str, Any]:
        """The owner's grants and, per source, whether macOS access is granted (an enrolled owner client only)."""
        return self._json("GET", "/v1/consent")

    def enable(self, sources: list[str]) -> dict[str, Any]:
        """The single Get Started consent: enable these source types."""
        return self._json("POST", "/v1/consent", {"sources": sources})

    def withdraw(self, grant_id: str) -> dict[str, Any]:
        return self._json("DELETE", f"/v1/consent/{grant_id}")

    def index_status(self) -> dict[str, Any]:
        return self._json("GET", "/v1/index/status")

    def cancel(self, task_id: str) -> dict[str, Any]:
        return self._json("POST", f"/v1/tasks/{task_id}/cancel")

    def status(self, task_id: str) -> dict[str, Any]:
        return self._json("GET", f"/v1/tasks/{task_id}")

    def events(self, task_id: str, after: int = 0) -> Iterator[dict[str, Any]]:
        """Events with seq > after, in order, until the task is finished (resumes by itself if the stream ends early)."""
        while True:
            response = self._call("GET", f"/v1/tasks/{task_id}/events?after={after}")
            try:
                if response.status != 200:  # noqa: PLR2004
                    code = json.loads(response.read() or b"{}").get("code", "")
                    raise ClientError(code if code in CATALOGUE["errors"] else "internal_error", message_for(code))
                for line in response:
                    if line.startswith(b"data: "):
                        event = json.loads(line[6:])
                        after = event["seq"]
                        yield event
                        if event["type"] in ("final", "error"):
                            return
            finally:
                self._done(response)
            if self.status(task_id)["state"] in TERMINAL:
                return
            time.sleep(0.05)

    def answer(self, task_id: str) -> dict[str, Any]:
        return self._json("GET", f"/v1/tasks/{task_id}/answer")

    def result(self, task_id: str, on_progress: Callable[[str], None] | None = None) -> dict[str, Any]:
        """Show progress until the task ends, then return the view of the answer (or raise ClientError with plain words)."""
        for event in self.events(task_id):
            if on_progress and event["type"] == "state":
                on_progress(CATALOGUE["task_states"][event["state"]])
            elif on_progress and event["type"] == "progress":
                on_progress(CATALOGUE["progress_steps"][event["step"]])
            elif event["type"] == "error":
                raise ClientError(event["error"]["code"], message_for(event["error"]["code"]), bool(event["error"].get("retryable")))
        return render(self.answer(task_id))

    def run_question(self, question: str, scope: list[str], on_progress: Callable[[str], None] | None = None) -> dict[str, Any]:
        return self.result(self.ask(question, scope), on_progress)


# -- turning an answer into what the owner sees ---------------------------------------------------------------------------------------------------------------
def _locator(evidence: dict[str, Any]) -> str:
    kinds, locator = CATALOGUE["locator_kinds"], evidence["locator"]
    try:
        return str(kinds.get(locator["kind"], kinds["span_only"]).format_map(locator))
    except KeyError:  # a locator without the field its template needs: say "a passage" rather than guess
        return str(kinds["span_only"])


def render(answer: dict[str, Any]) -> dict[str, Any]:
    """The view model of an answer: text, how far to trust it, which model wrote it, what was searched and what was not, and each citation with its quote."""
    cat = CATALOGUE
    model = answer.get("model")
    coverage = answer.get("coverage")
    searched_line = None
    if coverage is not None:
        template = cat["coverage_line_unknown_total"] if coverage["total"] is None else cat["coverage_line"]
        searched_line = f"{cat['coverage_state'][coverage['state']]} " + template.format(searched=coverage["searched"], total=coverage["total"])
    return {
        "text": answer["answer"],
        "trust": cat["verification"][answer["verification"]["status"]],
        "model_line": cat["model_line"].format(model_id=model["model_id"], role=cat["model_roles"].get(model["role"], model["role"]))
        if model
        else cat["model_line_unknown"],
        "coverage_line": searched_line,
        "notices": [cat["limitations"][x] for x in answer["limitations"]],
        "not_searched": [
            f"{cat['source_kinds'].get(n['source_type'], n['source_type'])}: {cat['not_searched_reasons'].get(n['reason_code'], '')}".strip()
            for n in answer["not_searched"]
        ],
        "citations": [
            {
                "label": f"{cat['source_kinds'].get(c['evidence']['source_type'], c['evidence']['source_type'])}, {_locator(c['evidence'])}",
                "quote": c.get("quote"),
                "evidence": c["evidence"],
            }
            for c in answer["citations"]
        ]
        or cat["no_citations"],
        "unproven_figures": answer["verification"]["unproven_figures"],
        "unproven_dates": answer["verification"]["unproven_dates"],
    }
