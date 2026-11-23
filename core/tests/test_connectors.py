"""Connectors: one catalogue, one adapter interface, the same approval rules for every integration, credentials only in the secret store, and a service that does not answer is never called connected.

A synthetic service implements the Atlas connector profile on 127.0.0.1 (so no real vendor, account or device is involved) and a vendor adapter is plugged in under the same id.
"""

from __future__ import annotations

import http.server
import json
import threading

import pytest
from test_client import atlas_client
from test_operations_api import OpsWorld

from atlas_core.connectors import MemorySecrets, RestProfileAdapter, catalogue

pytestmark = pytest.mark.criterion(15)
TOKEN = "synthetic-token-value-1"


class Service:
    """The profile: `/atlas/v1/ping`, `/atlas/v1/read/{scope}`, `/atlas/v1/act/{action}`, bearer token. A light that is on or off; `fail` makes every act fail."""

    def __init__(self):
        self.light, self.calls, self.fail, self.sent = "off", [], False, []
        service = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def _reply(self, status, body):
                raw = json.dumps(body).encode()
                self.send_response(status)
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def _authorised(self):
                return self.headers.get("Authorization") == f"Bearer {TOKEN}"

            def do_GET(self):
                service.calls.append(self.path)
                if not self._authorised():
                    return self._reply(401, {})
                if self.path == "/atlas/v1/ping":
                    return self._reply(200, {"ok": True})
                if self.path == "/atlas/v1/read/device_state":
                    return self._reply(200, {"light": service.light})
                return self._reply(404, {})

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                service.calls.append(self.path)
                if not self._authorised():
                    return self._reply(401, {})
                if service.fail:
                    return self._reply(500, {})
                if self.path == "/atlas/v1/act/control_device":
                    previous = {"light": service.light}
                    service.light = body["light"]
                    return self._reply(200, {"done": True, "previous": previous})
                if self.path == "/atlas/v1/act/unlock_door":
                    service.sent.append(body)
                    return self._reply(200, {"done": True})
                return self._reply(404, {})

            def log_message(self, *args):
                return None

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.address = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def rig(tmp_path):
    service, secrets = Service(), MemorySecrets()
    (tmp_path / "a").mkdir()
    world = OpsWorld(tmp_path / "a", secrets=secrets)
    world.build().start()
    yield world, service, secrets
    world.close()
    service.close()


def test_the_catalogue_is_data_and_every_integration_states_its_scopes_offline_retention_and_failure_behaviour():
    entries = catalogue()
    assert {"home", "travel", "work", "shopping", "messaging", "cloud_storage"} <= set(entries)
    for entry in entries.values():
        assert entry.read_scopes and entry.writes and entry.offline and entry.retention and entry.failure
        assert all(w["effect"] in ("reversible", "send", "spend", "unlock") for w in entry.writes)


def test_the_owner_connects_checks_and_disconnects_and_the_token_is_stored_once_and_never_returned(rig):
    world, service, secrets = rig
    owner = world.client()
    home = next(c for c in owner.connectors() if c["id"] == "home")
    assert home["state"] == "not_connected" and [f["name"] for f in home["fields"]] == ["address", "token"]
    assert {w["name"]: w["approval"] for w in home["writes"]} == {
        "control_device": "never",
        "unlock_door": "always",
    }  # the closed approval list, shown in advance
    wrong = owner.connect_connector("home", service.address, "not-the-token")
    assert wrong["state"] == "not_connected" and wrong["problem"] == "unauthorised" and secrets.items == {}  # nothing stored for refused credentials
    ok = owner.connect_connector("home", service.address, TOKEN)
    assert ok["state"] == "connected" and TOKEN not in json.dumps(ok) and TOKEN not in json.dumps(owner.connectors())
    assert TOKEN in secrets.items["connector-home"]  # only in the secret store
    assert owner.check_connector("home")["state"] == "connected"
    service.close()
    assert owner.check_connector("home")["state"] == "needs_attention"  # a service that does not answer is never called connected
    gone = owner.disconnect_connector("home")
    assert gone["state"] == "not_connected" and "connector-home" not in secrets.items
    with pytest.raises(atlas_client.ClientError) as e:
        world.device().connectors()
    assert e.value.code == "forbidden"


def test_a_reversible_change_is_prompt_free_and_undoable_while_unlocking_a_door_needs_the_owners_approval(rig):
    world, service, _ = rig
    owner = world.client()
    owner.connect_connector("home", service.address, TOKEN)
    done = owner.act("home.control_device", {"light": "on"})
    assert done["status"] == "done" and service.light == "on" and done["category"] is None
    owner.undo(done["action_id"])
    assert service.light == "off"  # put back what it replaced
    asked = owner.act("home.unlock_door", {"door": "front"})
    assert asked["status"] == "needs_approval" and asked["category"] == 4 and service.sent == []  # nothing happened yet
    owner.approve(asked["approval_id"])
    after = owner.act("home.unlock_door", {"door": "front"}, approval_id=asked["approval_id"])
    assert after["status"] == "done" and service.sent == [{"door": "front"}]


def test_disconnecting_refuses_every_action_and_a_command_the_service_did_not_confirm_is_not_reported_done(rig):
    world, service, _ = rig
    owner = world.client()
    assert owner.act("home.control_device", {"light": "on"})["status"] == "refused"  # never connected: refused, not attempted
    owner.connect_connector("home", service.address, TOKEN)
    service.fail = True
    assert owner.act("home.control_device", {"light": "on"})["status"] == "failed" and service.light == "off"
    service.fail = False
    owner.disconnect_connector("home")
    assert owner.act("home.control_device", {"light": "on"})["status"] == "refused"
    owner.connect_connector("home", service.address, TOKEN)
    assert owner.act("home.control_device", {"light": "on"})["status"] == "done"  # connecting again works


def test_a_vendors_own_adapter_replaces_the_bundled_one_without_changing_anything_else(tmp_path):
    class VendorAdapter:
        def __init__(self):
            self.acted = []

        def check(self, credentials):
            return "ok"

        def read(self, scope, credentials):
            return {"scope": scope}

        def act(self, action, payload, credentials):
            self.acted.append((action, payload))
            return {"done": True, "previous": {"light": "off"}}

    vendor, secrets = VendorAdapter(), MemorySecrets()
    (tmp_path / "a").mkdir()
    world = OpsWorld(tmp_path / "a", secrets=secrets, connector_adapters={"home": vendor})
    world.build().start()
    try:
        owner = world.client()
        assert owner.connect_connector("home", "http://127.0.0.1:1", "any-token")["state"] == "connected"  # the vendor's check decides, not the profile
        assert owner.act("home.control_device", {"light": "on"})["status"] == "done" and vendor.acted == [("control_device", {"light": "on"})]
        assert isinstance(RestProfileAdapter(), RestProfileAdapter)
    finally:
        world.close()


def test_connector_traffic_only_goes_where_the_owner_pointed_it_and_never_plain_http_to_the_public_internet():
    from atlas_core.connector_transport import permitted

    assert (
        permitted("https://api.example.com/x")
        and permitted("http://127.0.0.1:8080/x")
        and permitted("http://192.168.1.20/x")
        and permitted("http://hub.local/x")
    )
    assert (
        not permitted("http://api.example.com/x") and not permitted("ftp://127.0.0.1/x") and not permitted("file:///etc/passwd") and not permitted("http:///x")
    )
