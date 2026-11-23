"""The one place connector traffic leaves the Core (see `connectors`): to the address the OWNER typed for that connector, and nowhere else.

This is deliberately separate from the egress gateway. The egress gateway is for public research and refuses private addresses and anything that echoes private content; connectors are the opposite case, a
service the owner chose and authorised (often on the home network), whose every change already goes through the Action Gateway's approval rules. So this module is narrow instead:

* a plain `https` address, or `http` only to a loopback or private (home network) address, never plain http to the public Internet;
* no redirect is ever followed (a redirect to another place is an error, not a hop);
* a bounded reply, a short timeout, no cookies kept, and the caller's own headers only.
"""

from __future__ import annotations

import ipaddress
import urllib.error
import urllib.request
from urllib.parse import urlsplit

MAX_REPLY_BYTES = 1_000_000
TIMEOUT = 15.0


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args: object, **kwargs: object) -> None:
        return None  # a redirect is returned to the caller as the 3xx it is


def _private(host: str) -> bool:
    if host in ("localhost",):
        return True
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return host.endswith(".local")  # a home-network name
    return address.is_loopback or address.is_private or address.is_link_local


def permitted(url: str) -> bool:
    parts = urlsplit(url)
    host = parts.hostname or ""
    return bool(host) and (parts.scheme == "https" or (parts.scheme == "http" and _private(host)))


def request(method: str, url: str, headers: dict[str, str], body: bytes | None) -> tuple[int, bytes]:
    """Returns the status and the (bounded) body. Raises OSError for an address that is not permitted or does not answer."""
    if not permitted(url):
        raise OSError("address_not_permitted")
    opener = urllib.request.build_opener(_NoRedirect)
    req = urllib.request.Request(url, data=body, headers=headers, method=method)  # noqa: S310  (the scheme and host were checked above)
    try:
        with opener.open(req, timeout=TIMEOUT) as reply:
            return int(reply.status), reply.read(MAX_REPLY_BYTES)
    except urllib.error.HTTPError as error:
        return int(error.code), b""
    except (urllib.error.URLError, TimeoutError, ConnectionError) as error:
        raise OSError("unreachable") from error
