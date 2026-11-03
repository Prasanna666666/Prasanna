"""Allowlist egress proxy (HTTP CONNECT only). The ONLY container with a route to the internet.

    python -m saathi.egress          # listens on :3128, allows EGRESS_ALLOW hosts on port 443

Everything else gets 403. Hosts that resolve to private/loopback addresses are refused (no SSRF into your LAN).
It sees only hostnames and byte counts - TLS is end-to-end between the app and the public API.
"""

from __future__ import annotations

import asyncio
import ipaddress
import os
import socket
import sys

from .netguard import PUBLIC_ALLOW


class Proxy:
    def __init__(self, allow=None, ports=(443,), allow_private=False):
        self.allow, self.ports, self.allow_private = set(allow or PUBLIC_ALLOW), set(ports), allow_private

    async def _deny(self, w, code, why):
        w.write(f"HTTP/1.1 {code} {why}\r\nConnection: close\r\n\r\n".encode())
        await w.drain()
        w.close()
        print(f"DENY {code} {why}", file=sys.stderr, flush=True)

    async def handle(self, r: asyncio.StreamReader, w: asyncio.StreamWriter):
        try:
            parts = (await r.readline()).decode("latin1").split()
            while (await r.readline()) not in (b"\r\n", b"\n", b""):
                pass
            if len(parts) < 2 or parts[0] != "CONNECT":
                return await self._deny(w, 405, "only CONNECT")
            host, _, port = parts[1].rpartition(":")
            if host not in self.allow or not port.isdigit() or int(port) not in self.ports:
                return await self._deny(w, 403, f"host not allowed: {host}")
            infos = await asyncio.get_running_loop().getaddrinfo(host, int(port), type=socket.SOCK_STREAM)
            ip = infos[0][4][0]
            if not self.allow_private and not ipaddress.ip_address(ip).is_global:
                return await self._deny(w, 403, "address not public")
            try:
                ur, uw = await asyncio.open_connection(ip, int(port))
            except OSError:
                return await self._deny(w, 502, "upstream unreachable")
            print(f"ALLOW {host}:{port}", flush=True)
            w.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            await w.drain()

            async def pipe(src, dst):
                try:
                    while data := await src.read(65536):
                        dst.write(data)
                        await dst.drain()
                except OSError:
                    pass
                finally:
                    dst.close()

            await asyncio.gather(pipe(r, uw), pipe(ur, w))
        except Exception as e:
            print(f"ERR {e!r}", file=sys.stderr, flush=True)
            w.close()

    async def serve(self, host="0.0.0.0", port=3128):  # noqa: S104 - container-internal interface
        server = await asyncio.start_server(self.handle, host, port)
        async with server:
            await server.serve_forever()


if __name__ == "__main__":
    allow = [h for h in os.environ.get("EGRESS_ALLOW", "").split(",") if h.strip()] or None
    asyncio.run(Proxy(allow).serve(port=int(os.environ.get("EGRESS_PORT", "3128"))))
