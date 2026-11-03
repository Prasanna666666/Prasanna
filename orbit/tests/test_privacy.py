import socket
import threading

import pytest

from orbit import agent, netguard
from orbit.modules import world


@pytest.fixture
def guard():
    netguard.install()
    yield
    netguard.uninstall()


def test_blocks_dns_and_direct_ip(guard):
    with pytest.raises(netguard.EgressBlocked):
        socket.getaddrinfo("example.com", 443)
    s = socket.socket()
    with pytest.raises(netguard.EgressBlocked):
        s.connect(("93.184.216.34", 443))
    s.close()


def test_loopback_still_works(guard):
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    threading.Thread(target=lambda: srv.accept()[0].close(), daemon=True).start()
    c = socket.create_connection(("127.0.0.1", srv.getsockname()[1]))
    c.close()
    srv.close()


def test_place_and_currency_are_strictly_validated(conn):
    for bad in ["Bengaluru; my mother's BP is 150/90", "Amma\nsalary 90000", "x" * 50, "123"]:
        with pytest.raises(ValueError):
            world.weather(conn, {"place": bad})
    with pytest.raises(ValueError):
        world.exchange_rate(conn, {"base": "USD", "quote": "my password"})
    assert conn.execute("SELECT COUNT(*) FROM net_audit").fetchone()[0] == 0  # nothing was sent


def test_exchange_rate_is_audited(conn, monkeypatch):
    seen = {}

    def fake_get(conn_, host, path, params):
        conn_.execute("INSERT INTO net_audit (host, path, query) VALUES (?,?,?)", (host, path, str(params)))
        seen.update(host=host, params=params)
        return {"date": "2026-11-03", "rates": {"INR": 88.5}}

    monkeypatch.setattr(world, "_get", fake_get)
    r = world.exchange_rate(conn, {"base": "usd", "quote": "inr", "amount": 10})
    assert r["converted"] == 885.0 and seen["params"] == {"from": "USD", "to": "INR"}
    assert world.network_log(conn, {})[0]["host"] == "api.frankfurter.app"


def test_non_allowlisted_host_refused(conn):
    with pytest.raises(ValueError):
        world._get(conn, "evil.example.com", "/", {})


def test_time_is_offline(conn):
    assert world.current_time(conn, {"timezone": "Asia/Kolkata"})["timezone"] == "Asia/Kolkata"
    assert agent.run_tool(conn, "current_time", {"timezone": "Mars/Base"})[1]
