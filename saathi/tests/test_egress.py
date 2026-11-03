import asyncio

from saathi.egress import Proxy


async def _roundtrip(make_proxy, target_host, target_port=None):
    async def echo(r, w):
        w.write(b"hello:" + await r.read(5))
        await w.drain()
        w.close()

    target = await asyncio.start_server(echo, "127.0.0.1", 0)
    tport = target.sockets[0].getsockname()[1]
    srv = await asyncio.start_server(make_proxy(tport).handle, "127.0.0.1", 0)
    r, w = await asyncio.open_connection("127.0.0.1", srv.sockets[0].getsockname()[1])
    w.write(f"CONNECT {target_host}:{target_port or tport} HTTP/1.1\r\nHost: x\r\n\r\n".encode())
    status = (await r.readline()).decode()
    body = b""
    if " 200 " in status:
        await r.readline()
        w.write(b"world")
        body = await r.read(100)
    w.close()
    srv.close()
    target.close()
    return status, body


def run(*a, **k):
    return asyncio.run(_roundtrip(*a, **k))


def test_allowed_host_tunnels():
    s, body = run(lambda t: Proxy({"localhost"}, ports=(t,), allow_private=True), "localhost")
    assert " 200 " in s and body == b"hello:world"


def test_unlisted_host_denied():
    s, _ = run(lambda t: Proxy({"localhost"}, ports=(t,), allow_private=True), "evil.example.com", 443)
    assert " 403 " in s


def test_private_addresses_refused_by_default():
    s, _ = run(lambda t: Proxy({"localhost"}, ports=(t,)), "localhost")
    assert " 403 " in s


def test_wrong_port_denied():
    s, _ = run(lambda t: Proxy({"localhost"}, ports=(443,), allow_private=True), "localhost", 22)
    assert " 403 " in s
