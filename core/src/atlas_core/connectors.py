"""Connectors (Stage 6; USE_CASE_REGISTER section 5): the one place outside services plug in, so the app and the rules are the same for every one of them.

* **A catalogue held as data** (`connectors.json`): for each integration, what it can read, what it can change and how each change is judged (reversible, sends something out, spends money, unlocks physical
  access), how it behaves offline, what is kept and how a failure is reported. Adding an integration to the catalogue adds it to the app with no code.
* **A small adapter interface** (`Adapter`): `check`, `read`, `act`. The bundled `RestProfileAdapter` speaks a documented profile (`CONNECTOR_PROFILE.md`) to any service or bridge that implements it; a vendor's
  own adapter replaces it under the same id with `ConnectorHub.install`, and nothing else changes.
* **The same rules for all.** Every change a connector can make is an action in the Action Gateway with the approval category its effect implies, so approval stays the closed list in PRD 4.4 and everything else is
  prompt-free; the owner connects, checks and disconnects only as the owner client; disconnecting refuses every action of that connector and deletes its credentials; credentials live in the secret store (the
  Keychain on the Mac) and are never logged, returned or put in an audit entry.
* **Nothing is assumed.** A service that does not answer is `needs_attention`, never "connected"; a command is reported as done only if the service said so.
"""

from __future__ import annotations

import json
import re
import urllib.parse
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from importlib import resources
from typing import Any, Protocol

from .actions import ActionGateway, ActionSpec
from .connector_transport import request as urllib_transport
from .errors import CoreError

EFFECT = {"reversible": "local_reversible", "send": "external_send", "spend": "spend", "unlock": "physical_security"}  # the catalogue's words and the gateway's
FIELDS = (("address", False), ("token", True))  # what connecting asks for: where the service is, and the access token (the only secret)
ADDRESS = re.compile(r"https?://[A-Za-z0-9._~:/?#\[\]@!$&'()*+,;=%-]{1,300}\Z")
STATES = ("not_connected", "connected", "needs_attention")


@dataclass(frozen=True)
class Entry:
    id: str
    title: str
    category: str
    summary: str
    read_scopes: tuple[str, ...]
    writes: tuple[dict[str, str], ...]
    offline: str
    retention: str
    failure: str


def catalogue() -> dict[str, Entry]:
    raw = json.loads(resources.files("atlas_core").joinpath("connectors.json").read_text())
    return {
        key: Entry(key, v["title"], v["category"], v["summary"], tuple(v["read_scopes"]), tuple(v["write_scopes"]), v["offline"], v["retention"], v["failure"])
        for key, v in raw.items()
    }


class SecretStore(Protocol):
    def get(self, name: str) -> str | None: ...
    def set(self, name: str, value: str) -> None: ...
    def delete(self, name: str) -> None: ...


class MemorySecrets:
    """TEST ONLY and development: secrets kept in memory."""

    def __init__(self) -> None:
        self.items: dict[str, str] = {}

    def get(self, name: str) -> str | None:
        return self.items.get(name)

    def set(self, name: str, value: str) -> None:
        self.items[name] = value

    def delete(self, name: str) -> None:
        self.items.pop(name, None)


class Adapter(Protocol):
    def check(self, credentials: Mapping[str, str]) -> str:
        """`ok`, `unauthorised` or `unreachable`."""
        ...

    def read(self, scope: str, credentials: Mapping[str, str]) -> dict[str, Any]: ...

    def act(self, action: str, payload: dict[str, Any], credentials: Mapping[str, str]) -> dict[str, Any]:
        """Do it and say what it did. A reversible action returns `previous`, the state it replaced."""
        ...


Transport = Callable[[str, str, dict[str, str], bytes | None], tuple[int, bytes]]


class RestProfileAdapter:
    """The bundled adapter: the Atlas connector profile over HTTP (`CONNECTOR_PROFILE.md`). `GET /atlas/v1/ping`, `GET /atlas/v1/read/{scope}`, `POST /atlas/v1/act/{action}`, bearer token."""

    def __init__(self, transport: Transport = urllib_transport) -> None:
        self._transport = transport

    def _call(self, method: str, path: str, credentials: Mapping[str, str], body: dict[str, Any] | None = None) -> tuple[int, dict[str, Any]]:
        address = credentials.get("address", "")
        if not ADDRESS.match(address):
            raise OSError("bad_address")
        headers = {"Authorization": f"Bearer {credentials.get('token', '')}", "Accept": "application/json", "Content-Type": "application/json"}
        status, raw = self._transport(method, address.rstrip("/") + path, headers, None if body is None else json.dumps(body).encode())
        try:
            data = json.loads(raw) if raw else {}
        except ValueError:
            data = {}
        return status, data if isinstance(data, dict) else {}

    def check(self, credentials: Mapping[str, str]) -> str:
        try:
            status, _ = self._call("GET", "/atlas/v1/ping", credentials)
        except OSError:
            return "unreachable"
        if status in (401, 403):
            return "unauthorised"
        return "ok" if status == 200 else "unreachable"  # noqa: PLR2004

    def read(self, scope: str, credentials: Mapping[str, str]) -> dict[str, Any]:
        status, data = self._call("GET", f"/atlas/v1/read/{urllib.parse.quote(scope, safe='')}", credentials)
        if status != 200:  # noqa: PLR2004
            raise OSError("read_failed")
        return data

    def act(self, action: str, payload: dict[str, Any], credentials: Mapping[str, str]) -> dict[str, Any]:
        status, data = self._call("POST", f"/atlas/v1/act/{urllib.parse.quote(action, safe='')}", credentials, payload)
        if status != 200 or data.get("done") is not True:  # noqa: PLR2004
            raise OSError("act_failed")  # a command is reported as done only if the service said so
        return data


class ConnectorHub:
    def __init__(self, gateway: ActionGateway, secrets: SecretStore, adapters: Mapping[str, Adapter] | None = None) -> None:
        self._gateway, self._secrets = gateway, secrets
        self._entries = catalogue()
        default = RestProfileAdapter()
        self._adapters: dict[str, Adapter] = dict.fromkeys(self._entries, default) | dict(adapters or {})
        self._health: dict[str, str] = {}
        for entry in self._entries.values():
            for write in entry.writes:
                gateway.register(self._spec(entry, write))
            gateway.revoke_connector(
                entry.id
            )  # nothing may act until a check in THIS run has positively authenticated it (`verify_all`, or the owner's connect or check)
            if self._credentials(entry.id) is not None:
                self._health[entry.id] = "unverified"

    # -- plugging in ------------------------------------------------------------------------------------------------------------------------------
    def install(self, connector_id: str, adapter: Adapter) -> None:
        """Replace the bundled adapter for one integration with the vendor's own. The catalogue, the actions, the approval rules and the screen do not change."""
        if connector_id not in self._entries:
            raise CoreError("not_found")
        self._adapters[connector_id] = adapter

    # -- state ------------------------------------------------------------------------------------------------------------------------------------
    def _credentials(self, connector_id: str) -> dict[str, str] | None:
        stored = self._secrets.get(f"connector-{connector_id}")
        if stored is None:
            return None
        try:
            data = json.loads(stored)
        except ValueError:
            return None
        return {str(k): str(v) for k, v in data.items()} if isinstance(data, dict) else None

    def _state(self, connector_id: str) -> str:
        if self._credentials(connector_id) is None:
            return "not_connected"
        return "needs_attention" if self._health.get(connector_id) in ("unauthorised", "unreachable", "unverified") else "connected"

    def listing(self) -> dict[str, Any]:
        return {"connectors": [self._describe(e) for e in self._entries.values()]}

    def _describe(self, entry: Entry) -> dict[str, Any]:
        state = self._state(entry.id)
        return {
            "id": entry.id,
            "title": entry.title,
            "category": entry.category,
            "summary": entry.summary,
            "state": state,
            "problem": self._health.get(entry.id) if state == "needs_attention" else None,
            "read_scopes": list(entry.read_scopes),
            "writes": [{"name": w["name"], "title": w["title"], "approval": self._approval(w["effect"])} for w in entry.writes],
            "offline": entry.offline,
            "retention": entry.retention,
            "failure": entry.failure,
            "fields": [{"name": name, "secret": secret} for name, secret in FIELDS],
        }

    @staticmethod
    def _approval(effect: str) -> str:
        return {"reversible": "never", "send": "always", "spend": "always", "unlock": "always"}[effect]

    # -- the owner's three moves ------------------------------------------------------------------------------------------------------------------
    def link(self, connector_id: str, fields: Mapping[str, str]) -> dict[str, Any]:
        entry = self._entry(connector_id)
        credentials = {name: str(fields.get(name, "")) for name, _secret in FIELDS}
        if not credentials["address"] or not credentials["token"]:
            raise CoreError("invalid_request")
        verdict = self._adapters[connector_id].check(credentials)
        if verdict == "unauthorised":
            self._health[connector_id] = verdict
            return self._describe(entry) | {"state": "not_connected", "problem": "unauthorised"}  # nothing is stored for credentials the service refused
        self._secrets.set(f"connector-{connector_id}", json.dumps(credentials))
        self._apply(
            connector_id, verdict
        )  # only a positively authenticated answer lets it act; an unreachable service is kept (so it can be checked later) but cannot act
        return self._describe(entry)

    def _apply(self, connector_id: str, verdict: str) -> None:
        """The one place a health result changes authority: `ok` enables the connector's actions, anything else revokes them at once."""
        self._health[connector_id] = verdict
        if verdict == "ok":
            self._gateway.allow_connector(connector_id)
        else:
            self._gateway.revoke_connector(connector_id)

    def check(self, connector_id: str) -> dict[str, Any]:
        entry = self._entry(connector_id)
        credentials = self._credentials(connector_id)
        if credentials is None:
            raise CoreError("conflict")
        try:
            verdict = self._adapters[connector_id].check(credentials)
        except Exception:  # noqa: BLE001  (an adapter that fails is a service that did not answer: its authority is withdrawn, never left as it was)
            verdict = "unreachable"
        self._apply(connector_id, verdict)
        return self._describe(entry)

    def verify_all(self) -> None:
        """Check every connected integration once (run in the background when the Core starts): each that answers `ok` may act, every other stays refused."""
        for entry in self._entries.values():
            credentials = self._credentials(entry.id)
            if credentials is not None:
                try:
                    self._apply(entry.id, self._adapters[entry.id].check(credentials))
                except Exception:  # noqa: BLE001  (an adapter that fails is a service that did not answer)
                    self._apply(entry.id, "unreachable")

    def unlink(self, connector_id: str) -> dict[str, Any]:
        entry = self._entry(connector_id)
        self._gateway.revoke_connector(connector_id)  # every action of this connector is refused from now on
        self._secrets.delete(f"connector-{connector_id}")
        self._health.pop(connector_id, None)
        return self._describe(entry)

    def _entry(self, connector_id: str) -> Entry:
        entry = self._entries.get(connector_id)
        if entry is None:
            raise CoreError("not_found")
        return entry

    # -- reading and acting (for the agents and the action gateway) ---------------------------------------------------------------------------------
    def read(self, connector_id: str, scope: str) -> dict[str, Any]:
        entry = self._entry(connector_id)
        credentials = self._credentials(connector_id)
        if credentials is None or scope not in entry.read_scopes:
            raise CoreError("source_denied")
        return self._adapters[connector_id].read(scope, credentials)

    def _spec(self, entry: Entry, write: dict[str, str]) -> ActionSpec:
        name = f"{entry.id}.{write['name']}"
        reversible = write["effect"] == "reversible"

        def handler(payload: dict[str, Any]) -> dict[str, Any]:
            credentials = self._credentials(entry.id)
            if credentials is None:
                raise OSError("not_connected")
            return self._adapters[entry.id].act(write["name"], payload, credentials)

        def undo(_payload: dict[str, Any], result: dict[str, Any]) -> None:
            credentials = self._credentials(entry.id)
            previous = result.get("previous")
            if credentials is not None and isinstance(previous, dict):
                self._adapters[entry.id].act(write["name"], previous, credentials)  # put back what it replaced

        return ActionSpec(name, frozenset({EFFECT[write["effect"]]}), handler, undo if reversible else None, connector=entry.id)
