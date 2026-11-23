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
import unicodedata
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from html.parser import HTMLParser
from typing import Protocol
from urllib.parse import quote, unquote_plus, urljoin, urlsplit

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


def _decode(text: str) -> str:
    """What a receiver would read: percent-escapes undone (even if applied more than once), compatibility forms folded (full-width letters), accents removed."""
    for _ in range(3):
        decoded = unquote_plus(text)
        if decoded == text:
            break
        text = decoded
    folded = unicodedata.normalize("NFKD", text)
    return unicodedata.normalize("NFC", "".join(c for c in folded if not unicodedata.combining(c)))


CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")


def _normal(text: str) -> str:
    """`_decode`, plus word breaks inside camelCase and underscores, so "AlexandraJanssen" and "tax_debt" are read as the words they are made of."""
    return CAMEL.sub(" ", _decode(text)).replace("_", " ")


def _words(text: str) -> list[str]:
    return re.findall(r"\w+", _normal(text).casefold())


def _fingerprint(words: list[str]) -> str:
    return hashlib.sha256(" ".join(words).encode()).hexdigest()[:16]


def _token_fingerprint(token: str) -> str:
    return _fingerprint([re.sub(r"\W+", "", token.casefold())])


def _candidates(text: str) -> list[str]:
    return PRIVATE_TOKEN.findall(text) + IDENTIFIER.findall(text)


SENTENCE_END = re.compile(r"[.!?\n]+")
SHORT_PHRASE_WORDS = 2  # 2-word runs of a passage AND of the question are fingerprinted: a lower-case private phrase of any length is caught
MIN_NAME_CHARS = 3
MIN_WORD_CHARS = 4  # every word of a private passage with this many letters is fingerprinted, in any case: a name written only in lower case is still caught
STOP_WORDS = frozenset(
    [
        "that",
        "this",
        "with",
        "from",
        "have",
        "been",
        "were",
        "will",
        "would",
        "could",
        "should",
        "there",
        "their",
        "about",
        "which",
        "when",
        "what",
        "where",
        "your",
        "they",
        "them",
        "then",
        "than",
        "into",
        "over",
        "also",
        "more",
        "most",
        "some",
        "such",
        "only",
        "very",
        "just",
        "like",
        "each",
        "other",
        "dit",
        "dat",
        "een",
        "het",
        "van",
        "voor",
        "niet",
        "zijn",
        "maar",
        "ook",
        "nog",
        "wel",
        "dan",
        "als",
        "bij",
        "naar",
        "door",
        "over",
        "uit",
        "heeft",
        "hebben",
        "wordt",
        "worden",
        "deze",
        "die",
        "dit",
    ]
)  # function words (English, Dutch) that no public query should be refused for


def _names(text: str) -> set[str]:
    """Proper-name-like words: capitalised, not at the start of a sentence; a sentence-initial capitalised word counts only if the text never writes it in lower case (so "Alexandra called"
    is a name and "The" or "Invoice ... invoice" is not). Fingerprints of the words, the words themselves are not returned for storage."""
    found: set[str] = set()
    text = _normal(text)
    lowercase = {w.casefold() for w in re.findall(r"\w+", text) if w[0].islower()}
    for sentence in SENTENCE_END.split(text):
        for position, word in enumerate(re.findall(r"\w+", sentence)):
            if len(word) < MIN_NAME_CHARS or not word[0].isupper() or word.isdigit():
                continue
            if position == 0 and word.casefold() in lowercase:
                continue
            found.add(_fingerprint([word.casefold()]))
    return found


@dataclass
class TaintSet:
    """What a task has read in private, kept as FINGERPRINTS (the text is not kept): 4-word shingles (2-word runs for passages), identifier-like tokens (any token of 8+ characters that contains a
    digit, an e-mail address, a long number), every word of 4+ letters of a passage or of the question (names in any case), plus whether Finance/Health data is in its context.

    Not detected: a paraphrase, and 1-3 letter words or names. A public query that shares a word of 4+ letters (other than a function word) with a private passage OR with the question is refused: the gateway over-refuses, never under-refuses, within what it can see. A research query therefore has to be worded without the question's own content words; that cost is deliberate."""

    shingles: set[str] = field(default_factory=set)
    identifiers: set[str] = field(default_factory=set)
    names: set[str] = field(default_factory=set)
    restricted_in_context: bool = False

    def add(self, text: str, *, restricted: bool = False, question: bool = False) -> None:
        words = _words(text)
        for size in (
            SHINGLE_WORDS,
            SHORT_PHRASE_WORDS,
        ):  # the question is private context exactly like a passage: its 2-word runs and its words are fingerprinted too
            for i in range(len(words) - size + 1):
                self.shingles.add(_fingerprint(words[i : i + size]))
        self.names |= {_fingerprint([w]) for w in words if len(w) >= MIN_WORD_CHARS and w not in STOP_WORDS}
        for token in _candidates(text):
            if any(c.isdigit() for c in token) or "@" in token:
                self.identifiers.add(_token_fingerprint(token))
        self.names |= _names(text)
        self.restricted_in_context = self.restricted_in_context or restricted

    def leaks(self, text: str) -> bool:
        words = _words(text)
        for size in (SHINGLE_WORDS, SHORT_PHRASE_WORDS):
            if any(_fingerprint(words[i : i + size]) in self.shingles for i in range(len(words) - size + 1)):
                return True
        if any(_fingerprint([w]) in self.names for w in words):
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
        self._check_text(self._url_text(url), taint, purpose, self._host(url))
        return self._get(url, taint, purpose)

    # -- the checks ----------------------------------------------------------------------------------------------------------------------------
    @staticmethod
    def _url_text(url: str) -> str:
        parts = urlsplit(url)
        return " ".join(
            [*(parts.hostname or "").split("."), parts.path, parts.query, parts.fragment]
        )  # host labels and fragment too: any part of the URL can carry content

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
        if IDENTIFIER.search(_decode(text)):
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
                self._check_text(self._url_text(current), taint, purpose, urlsplit(current).hostname or "")
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
