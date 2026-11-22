"""The Core's egress gateway for PUBLIC Internet research (INTERNET_AND_NETWORK_POLICY.md sections 1-3, 7, 8).

Nothing else in the Core opens a network connection for research (an architecture test enforces it). A request leaves only if ALL of these hold, and every refusal is a typed reason, not an
exception that carries content:

* the destination is https, has no credentials in the URL, and resolves only to public addresses (no loopback, private, link-local, reserved or multicast address; each redirect is checked again);
* the request carries no private content: the task's `TaintSet` (fingerprints of the passages and the question that are in its context) is checked against the query and the URL, and any
  identifier-like value (an e-mail address, a long digit run, a long token) is refused; a task whose context holds Finance or Health data may not use the network at all;
* the response is bounded (size, redirects, time), text-only, and returned as UNTRUSTED DATA with its provenance (URL, domain, retrieval time, content hash). It carries no authority: it
  cannot add a tool, a source, a grant or an action, and instruction-like text in it is flagged, never obeyed.

The audit record holds the destination host, purpose, data class, time, status and byte count; never a query, URL path, header or content. The transport is injected: CI uses synthetic fixtures and
no test reaches the Internet. `UrllibTransport` is the real one and has NOT been run against the real Internet.
"""

from __future__ import annotations

import hashlib
import ipaddress
import re
import socket
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from html.parser import HTMLParser
from typing import Protocol
from urllib.parse import quote, urljoin, urlsplit

MAX_BYTES = 512 * 1024
MAX_REDIRECTS = 3
HTTP_OK = 200
REDIRECTS = (301, 302, 303, 307, 308)
MAX_QUERY_CHARS = 256
SHINGLE_WORDS = 4  # a query that repeats this many consecutive words of private text is private text
TEXT_TYPES = ("text/html", "text/plain", "application/json", "application/xhtml+xml")
IDENTIFIER = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+|\b\d[\d \-]{5,}\d\b|\b[A-Za-z0-9_-]{24,}\b")
INSTRUCTION_LIKE = re.compile(
    r"ignore (all |any |the )?(previous|prior|above) (instructions|rules)|disregard .{0,40}instructions|you (must|should) now|system prompt|"
    r"send (the |your |all )?(files|documents|emails|data)|upload|exfiltrate|reveal (your|the) (instructions|prompt|secrets?)|run (this|the following) (command|script)",
    re.IGNORECASE,
)


class Denied(Exception):
    """A request was refused. Carries only a code."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


PRIVATE_TOKEN = re.compile(r"[\w.+@-]{8,}")


def _words(text: str) -> list[str]:
    return re.findall(r"\w+", text.casefold())


def _fingerprint(words: list[str]) -> str:
    return hashlib.sha256(" ".join(words).encode()).hexdigest()[:16]


def _token_fingerprint(token: str) -> str:
    return _fingerprint([re.sub(r"\W+", "", token.casefold())])


def _candidates(text: str) -> list[str]:
    return PRIVATE_TOKEN.findall(text) + IDENTIFIER.findall(text)


@dataclass
class TaintSet:
    """What a task has read in private, kept as FINGERPRINTS (the text is not kept): word shingles and identifier-like tokens (any token of 8+ characters that contains a digit, an e-mail address,
    a long number), plus whether Finance/Health data is in its context."""

    shingles: set[str] = field(default_factory=set)
    identifiers: set[str] = field(default_factory=set)
    restricted_in_context: bool = False

    def add(self, text: str, *, restricted: bool = False) -> None:
        words = _words(text)
        for i in range(len(words) - SHINGLE_WORDS + 1):
            self.shingles.add(_fingerprint(words[i : i + SHINGLE_WORDS]))
        for token in _candidates(text):
            if any(c.isdigit() for c in token) or "@" in token:
                self.identifiers.add(_token_fingerprint(token))
        self.restricted_in_context = self.restricted_in_context or restricted

    def leaks(self, text: str) -> bool:
        words = _words(text)
        if any(_fingerprint(words[i : i + SHINGLE_WORDS]) in self.shingles for i in range(len(words) - SHINGLE_WORDS + 1)):
            return True
        return any(_token_fingerprint(token) in self.identifiers for token in _candidates(text))


@dataclass(frozen=True)
class Response:
    status: int
    content_type: str
    body: bytes
    location: str | None = None  # for a redirect


class Transport(Protocol):
    def get(self, url: str, timeout: float, max_bytes: int) -> Response: ...


@dataclass(frozen=True)
class WebDocument:
    """Public content, always untrusted data. `authority` is always "none"."""

    url: str
    domain: str
    retrieved_at: str
    content_hash: str
    text: str
    truncated: bool
    injection_flags: tuple[str, ...]
    trust: str = "untrusted"
    authority: str = "none"


@dataclass(frozen=True)
class AuditRecord:
    host: str
    purpose: str
    data_class: str
    at: str
    status: str
    bytes: int


class _Text(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._skip += tag in ("script", "style", "template", "noscript")

    def handle_endtag(self, tag: str) -> None:
        self._skip -= tag in ("script", "style", "template", "noscript") and self._skip > 0

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self.parts.append(data)


def public_address(host: str, resolve: Callable[[str], Iterable[str]]) -> bool:
    """True only if the host is a name or address that resolves ONLY to public addresses."""
    try:
        addresses = list(resolve(host))
    except OSError:
        return False
    if not addresses:
        return False
    for raw in addresses:
        try:
            ip = ipaddress.ip_address(raw.split("%")[0])
        except ValueError:
            return False
        if not ip.is_global or ip.is_multicast:
            return False
    return True


def _resolve(host: str) -> list[str]:
    return [str(info[4][0]) for info in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)]


class EgressGateway:
    def __init__(
        self,
        transport: Transport,
        *,
        search_url: str = "https://search.example.invalid/?q={query}",
        resolve: Callable[[str], Iterable[str]] = _resolve,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        audit: Callable[[AuditRecord], None] | None = None,
        timeout: float = 10.0,
    ) -> None:
        self._transport, self._search_url, self._resolve, self._clock, self._timeout = transport, search_url, resolve, clock, timeout
        self._audit = audit or (lambda record: None)

    # -- the two typed operations ------------------------------------------------------------------------------------------------------------
    def search(self, query: str, taint: TaintSet, *, purpose: str = "public_research") -> WebDocument:
        """A public web search. The query must carry no private content; the result is untrusted data."""
        self._check_text(query, taint, purpose, self._host(self._search_url))
        return self._get(self._search_url.format(query=quote(query.strip(), safe="")), taint, purpose)

    def fetch(self, url: str, taint: TaintSet, *, purpose: str = "public_research") -> WebDocument:
        """Retrieve one public page. The URL (path and query too) must carry no private content."""
        self._check_text(urlsplit(url).path + " " + urlsplit(url).query, taint, purpose, self._host(url))
        return self._get(url, taint, purpose)

    # -- the checks ----------------------------------------------------------------------------------------------------------------------------
    @staticmethod
    def _host(url: str) -> str:
        return urlsplit(url).hostname or ""

    def _refuse(self, code: str, host: str, purpose: str) -> Denied:
        self._audit(AuditRecord(host, purpose, "none_sent", self._clock().isoformat(), f"denied:{code}", 0))  # the refusal is recorded; what was refused is not
        return Denied(code)

    def _check_text(self, text: str, taint: TaintSet, purpose: str, host: str) -> None:
        if taint.restricted_in_context:
            raise self._refuse("restricted_context", host, purpose)  # Finance or Health data in this task's context: no network at all
        if not text.strip() or len(text) > MAX_QUERY_CHARS * 4:
            raise self._refuse("bad_request", host, purpose)
        if IDENTIFIER.search(text):
            raise self._refuse("identifier_in_request", host, purpose)  # an e-mail address, a long number or a long token is never a public query
        if taint.leaks(text):
            raise self._refuse("private_content_in_request", host, purpose)

    def _check_url(self, url: str, purpose: str) -> str:
        parts = urlsplit(url)
        host = parts.hostname or ""
        if parts.scheme != "https" or not host or parts.username or parts.password or parts.port not in (None, 443):
            raise self._refuse("destination_not_allowed", host, purpose)
        if not public_address(host, self._resolve):
            raise self._refuse("destination_not_public", host, purpose)
        return host

    def _get(self, url: str, taint: TaintSet, purpose: str) -> WebDocument:
        current, host, size = url, "", 0
        for _hop in range(MAX_REDIRECTS + 1):
            host = self._check_url(current, purpose)
            try:
                response = self._transport.get(current, self._timeout, MAX_BYTES)
            except Exception:  # noqa: BLE001  (a network failure is a code, never text that could carry content)
                raise self._refuse("unavailable", host, purpose) from None
            size += len(response.body)
            if response.status in REDIRECTS and response.location:
                current = urljoin(current, response.location)
                self._check_text(urlsplit(current).path + " " + urlsplit(current).query, taint, purpose, urlsplit(current).hostname or "")
                continue  # every hop is checked again as a new request
            break
        else:
            raise self._refuse("too_many_redirects", host, purpose)
        kind = response.content_type.split(";")[0].strip().lower()
        if response.status != HTTP_OK or kind not in TEXT_TYPES:
            raise self._refuse("unsupported_response", host, purpose)  # downloads, binaries and scripts are never fetched here
        body, truncated = response.body[:MAX_BYTES], len(response.body) > MAX_BYTES
        raw = body.decode("utf-8", "replace")
        if kind in ("text/html", "application/xhtml+xml"):
            extractor = _Text()
            extractor.feed(raw)
            raw = " ".join("".join(extractor.parts).split())
        flags = ("instruction_like_text",) if INSTRUCTION_LIKE.search(raw) else ()
        self._audit(AuditRecord(host, purpose, "public_query", self._clock().isoformat(), "ok", size))
        return WebDocument(current, host, self._clock().isoformat(), hashlib.sha256(body).hexdigest(), raw[:200_000], truncated, flags)


class UrllibTransport:
    """The real transport: https GET, no cookies, no credentials, no redirects followed (the gateway checks and follows them), at most `max_bytes`. NOT run against the real Internet in CI."""

    def get(self, url: str, timeout: float, max_bytes: int) -> Response:
        import http.client
        import ssl

        parts = urlsplit(url)
        host = parts.hostname or ""
        address = _resolve(host)[0]
        if not public_address(host, lambda _h: [address]):
            raise OSError("not public")
        raw = socket.create_connection((address, 443), timeout=timeout)  # connect to the address that was checked, not to a second lookup of the name
        tls = ssl.create_default_context().wrap_socket(raw, server_hostname=host)
        connection = http.client.HTTPSConnection(host, timeout=timeout)
        connection.sock = tls
        try:
            connection.request(
                "GET",
                (parts.path or "/") + (f"?{parts.query}" if parts.query else ""),
                headers={"User-Agent": "Atlas-Core/1", "Accept": "text/html, text/plain, application/json"},
            )
            answer = connection.getresponse()
            body = answer.read(max_bytes + 1)
            return Response(answer.status, answer.getheader("Content-Type", ""), body, answer.getheader("Location"))
        finally:
            connection.close()
