# Egress gateway for public research (Stage 3, `egress.py`)

Requirement: STAGE-3-EXECUTION-PLAN.md ("Public Internet research through the Core egress gateway when useful, using synthetic fixtures in CI and never sending private owner data to public search") and
INTERNET_AND_NETWORK_POLICY.md sections 1-3, 7, 8. Status: **implemented and tested with synthetic fixtures; not wired into the answer flow; never run against the real Internet; unsafe to enable until the known taint defect below is fixed.**

## What it enforces
- **One door.** Only `egress`, `transport` (the local Unix socket server) and `confinement` (tries a connection only to be refused) may import anything that opens a socket or speaks HTTP
  (`tests/test_architecture.py::test_only_the_egress_gateway_and_the_local_transport_can_open_a_network_connection`). No model module can.
- **Typed operations:** `search(query, taint)` and `fetch(url, taint)`. Both refuse with a code (`Denied.code`) and send nothing when a check fails.
- **No private data out.** A task's `TaintSet` holds fingerprints (not text) of every private passage and the question: 4-word shingles (2-word runs for passages, not for the question), identifier-like tokens, every word of 4+ letters of a passage in any case (so a name written only in lower case is caught; English and Dutch function words are exempt) and capitalised names in the question. A query or URL (path and query string) that repeats a
  shingle or a token is refused (`private_content_in_request`); an e-mail address, a long number or a long token is refused outright (`identifier_in_request`); and a task whose context holds Finance or Health data may
  not use the network at all (`restricted_context`, G-021 and the policy's "Finance, Health ... prohibited").
- **Destination.** https only, no credentials, port 443, every resolved address public (no loopback, private, link-local, reserved, multicast, shared address space); every redirect hop is checked again as a new request;
  at most 3 redirects. The real transport connects to the address that was checked, not to a second lookup.
- **Content is untrusted data.** Text types only (HTML, plain text, JSON); scripts and styles are dropped from HTML; size-bounded and flagged when truncated; returned as `WebDocument` with URL, domain, retrieval time and
  content hash, `trust="untrusted"`, `authority="none"`. Instruction-like text is flagged (`instruction_like_text`), never obeyed: nothing the document says can cause another request, add a source, a tool, a grant or an action.
- **Audit** (`AuditRecord`): host, purpose, data class, time, status, byte count. Never a query, URL path, header or content; a refusal records that something was refused, not what.

## Not built / not verified
- Not wired into the answer flow: no part of the API or the task service asks for public research yet (it needs a contract extension, an architect decision). `CoreConfig.egress` is `None` by default, so a Core makes no
  outbound request.
- `UrllibTransport` has never touched the real Internet; the search provider URL is configuration (the default is a placeholder). robots.txt, rate limits and page-date extraction are not implemented.
- **Normalisation.** Before every check the text is read as a receiver would: percent-escapes undone (also when applied twice), full-width and compatibility forms folded, accents removed, camelCase and underscores split into words. A URL is checked as a whole: host labels, path, query and fragment, and every redirect hop. Tests: `tests/test_egress.py` (encodings, host, fragment).
- **Over-refusal by design.** A public query or URL (including its host name) that shares any word of 4+ letters, or any two-word run, with a private passage is refused, so a search about the same topic as a retrieved passage will often be refused. Not detected: a paraphrase, and 1-3 letter words or names. No "no private egress" guarantee is claimed until real transport testing is done; the gateway stays disconnected and disabled.
- The taint check is a fingerprint match, not a guarantee: a paraphrase of private text is not detected (the policy's minimisation rule is then the caller's). It over-refuses rather than under-refuses.
- Approval for uploads/sends is outside this gateway: it has no operation that sends owner content anywhere.

Tests: `tests/test_egress.py` (public query with provenance and a redacted audit; private content, identifiers and restricted context refused before anything is sent; destinations; redirects; response types, bounds and
instruction-like text; private names (any case) and two-word phrases in queries and URL paths/queries; network failure without error text; fingerprints not text; mutation-checked by disabling the taint check).
