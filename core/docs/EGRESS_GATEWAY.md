# Egress gateway for public research (Stage 3, `egress.py`)

Requirement: STAGE-3-EXECUTION-PLAN.md ("Public Internet research through the Core egress gateway when useful, using synthetic fixtures in CI and never sending private owner data to public search") and
INTERNET_AND_NETWORK_POLICY.md sections 1-3, 7, 8. Status: **implemented and tested with synthetic fixtures; not wired into the answer flow; never run against the real Internet; unsafe to enable until the known taint defect below is fixed.**

## What it enforces
- **One door.** Only `egress`, `transport` (the local Unix socket server) and `confinement` (tries a connection only to be refused) may import anything that opens a socket or speaks HTTP
  (`tests/test_architecture.py::test_only_the_egress_gateway_and_the_local_transport_can_open_a_network_connection`). No model module can.
- **Typed operations:** `search(query, taint)` and `fetch(url, taint)`. Both refuse with a code (`Denied.code`) and send nothing when a check fails.
- **Taint-based minimisation, not a no-egress guarantee.** A task's `TaintSet` holds fingerprints (not raw text) of 4-word shingles and selected identifier-like tokens. Matching shingles/tokens and a task whose context holds Finance or Health data are refused. However, the current implementation fingerprints an 8+ character candidate token only when it contains a digit or `@`; ordinary private names (for example, `Alexandra`) and short 2–3 word private phrases can evade the check. This is a known P1 defect, not an accepted privacy guarantee.
- **Destination.** https only, no credentials, port 443, every resolved address public (no loopback, private, link-local, reserved, multicast, shared address space); every redirect hop is checked again as a new request;
  at most 3 redirects. The real transport connects to the address that was checked, not to a second lookup.
- **Content is untrusted data.** Text types only (HTML, plain text, JSON); scripts and styles are dropped from HTML; size-bounded and flagged when truncated; returned as `WebDocument` with URL, domain, retrieval time and
  content hash, `trust="untrusted"`, `authority="none"`. Instruction-like text is flagged (`instruction_like_text`), never obeyed: nothing the document says can cause another request, add a source, a tool, a grant or an action.
- **Audit** (`AuditRecord`): host, purpose, data class, time, status, byte count. Never a query, URL path, header or content; a refusal records that something was refused, not what.

## Not built / not verified
- Not wired into the answer flow: no part of the API or the task service asks for public research yet (it needs a contract extension, an architect decision). `CoreConfig.egress` is `None` by default, so a Core makes no
  outbound request.
- `UrllibTransport` has never touched the real Internet; the search provider URL is configuration (the default is a placeholder). robots.txt, rate limits and page-date extraction are not implemented.
- The taint check is a fingerprint match, not a guarantee: paraphrases are not detected, and the current candidate-token rule also misses ordinary private names and short phrases. Do not wire or enable the gateway until this is fixed with regression tests for single names and 2–3 word phrases in search queries and URL path/query. Do not retain or log raw private text to implement the fix.
- Approval for uploads/sends is outside this gateway: it has no operation that sends owner content anywhere.

Tests: `tests/test_egress.py` (public query with provenance and a redacted audit; private content, identifiers and restricted context refused before anything is sent; destinations; redirects; response types, bounds and
instruction-like text; network failure without error text; fingerprints not text; mutation-checked by disabling the taint check).
