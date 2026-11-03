import ast
import pathlib
import socket
import threading

import pytest

from orbit import netguard
from orbit.modules import ALL, tools

SRC = pathlib.Path(__file__).parent.parent / "src" / "orbit"
NETWORK_MODULES = {"requests", "httpx", "aiohttp", "http.client", "ftplib", "smtplib", "imaplib", "poplib",
                   "telnetlib", "websockets", "anthropic", "openai"}


@pytest.fixture
def guard():
    netguard.install()
    yield
    netguard.uninstall()


def test_blocks_all_dns_and_direct_ip(guard):
    for name in ("example.com", "api.open-meteo.com", "api.frankfurter.app"):
        with pytest.raises(netguard.EgressBlocked):
            socket.getaddrinfo(name, 443)
    s = socket.socket()
    with pytest.raises(netguard.EgressBlocked):
        s.connect(("93.184.216.34", 443))
    s.close()


def test_loopback_still_works(guard):
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    threading.Thread(target=lambda: srv.accept()[0].close(), daemon=True).start()
    socket.create_connection(("127.0.0.1", srv.getsockname()[1])).close()
    srv.close()


def test_no_internet_capable_tools():
    banned = {"weather", "exchange_rate", "network_log", "search_web", "fetch_url"}
    assert not banned & set(tools(ALL))


def test_no_network_libraries_imported_anywhere():
    """Build-time check: only llm.py (local Ollama over urllib) may touch the network, and egress is guarded."""
    for f in SRC.rglob("*.py"):
        for node in ast.walk(ast.parse(f.read_text())):
            names = [a.name for a in node.names] if isinstance(node, ast.Import) else \
                    [node.module or ""] if isinstance(node, ast.ImportFrom) else []
            for n in names:
                assert n not in NETWORK_MODULES, f"{f.name} imports {n}"
                if n.startswith("urllib") and "request" in n:
                    assert f.name == "llm.py", f"{f.name} uses urllib.request"
