# Stage 3, WP3.1: proposed contract delta, threat model and test matrix

**Status:** the developer's *proposal* for ChatGPT's WP3.1 brief. It is input, not authority: ChatGPT owns the target contract (`docs/genesis/STAGE-3-EXECUTION-PLAN.md` WP3.1). Nothing here is implemented; `core/` is unchanged. Written against API 1.0 as frozen in `contracts/atlas-contracts.schema.json`.
**Sources:** `PRD.md` §4.3a and §4.4, `INTERNET_AND_NETWORK_POLICY.md` §10, `USE_CASE_REGISTER.md` UC-001/002/007/008/009/012/016/032, UC-L01 to L09/L19/L26/L28, UC-039/041/047/048, plan WP3.1 to WP3.3, G-021 to G-026.

## 1. Principles
- **Additive and compatible.** API 1.0 clients keep working. The version becomes `1.1` (`supported: ["1.0","1.1"]`); every new field is optional in 1.0 responses and required only for clients that ask for 1.1. Model identity is the planned minor-version addition (plan constraint 10).
- **The Core stays the only policy authority.** A new endpoint may only be called by an enrolled **owner-interactive** client (new identity role, §2.2); models, content and automation can never reach it.
- **No new content in events.** Every new safe event is an enumeration or a count; never a path, subject, address, query or amount.

## 2. Contract delta (API 1.1)
### 2.1 Coverage on every answer (UC-L26, plan F2)
`AnswerEnvelope.coverage`: `{state: complete | partial | indexing, searched: int, total: int | null, pending: [{category, count}], failed: [{reason_code, count}], as_of: Timestamp}`. `total` is `null` while discovery is incomplete. Rule: an answer with `state != complete` must also carry the limitation `indexing_incomplete`; no code path may omit coverage when `source_scope` is non-empty.

### 2.2 Get Started consent and revocation (G-025, UC-L01/L02/L19)
- `POST /v1/consent` body `{sources: ["documents","mail"]}` creates one grant per source type (existing `SourceGrant`, `designated_by: "owner"`, `purpose: "answer_question"`, `expires_at: null`, `max_sensitivity` set by the policy default of that type). One call, no per-folder fields.
- `GET /v1/consent` lists grants; `DELETE /v1/consent/{grant_id}` revokes **immediately** (the next read or model boundary already re-validates, Stage 2).
- New identity attribute `role: owner_interactive` on a registered client, set at enrolment; requests to these routes from any other client return `forbidden`. Audited by the safe event `consent.changed` (`{action: granted|revoked, source_type}`).
- OS-level access (Full Disk Access, Mail automation) is a separate state: `GET /v1/consent` reports per source `os_access: granted | missing | unknown`. Missing access yields the user-safe error and limitation `os_access_missing`, never a partial silent answer.

### 2.3 Locators for real sources (UC-047/048, plan WP3.2/3.3)
Extend `Locator.kind` with `header_field`, `attachment_part`, `sheet_cell`; new optional fields `header` (`from|to|date|subject|message_id`), `attachment_id` (opaque), `sheet` (string), `cell` (A1 notation), `authenticity` (`claimed` for every header field: sender and date are values the message says about itself, not verified identity).
Mail evidence: body, header fields, thread and attachment parts keep distinct `source_type` values (`mail`, `mail_attachment`), so they keep separate grants, labels and provenance. **Quoted or forwarded text is not the sender's**: a citation into quoted text carries `quoted: true` and must never be attributed to the message sender.

### 2.4 Model identity and route event (G-020, plan WP3.1)
`AnswerEnvelope.model`: `{model_id, role, runtime}` (strings from a closed registry; `runtime` is `mlx` or `stub`; never prompt text). Safe event `model.routed` with `{role, model_id}`; the route re-enters the same policy gate (existing `GatedModel`), so a switch cannot widen permissions.

### 2.5 Index status, states and limitations (UC-L03/L04/L24)
- `GET /v1/index/status`: `{state: idle | building | rebuilding | needs_attention, indexed, total | null, newest_indexed: Timestamp | null, failed: [{reason_code, count}]}`. Counts only.
- New `Limitation` values: `indexing_incomplete`, `source_unsupported`, `os_access_missing`, `attachment_pending`. New error codes: `os_access_missing`, `index_unavailable` (user-safe text fixed in `errors.py`).
- Existing `attachments_not_searched` stays for 1.0 clients; 1.1 replaces it with `attachment_pending` until WP3.3b is accepted.

### 2.6 Egress (policy §10) is not a public API
The egress gateway is an internal Core tool. Its only external trace is the safe event `egress.decision` `{decision: allow|deny, reason_code, destination_class: search_provider|connector|update_manifest|model_manifest}`: a class, never a host, URL or query.

### 2.7 Policy data (not code)
`policy-rules.json`: add source types `documents_index` rules only if the index needs its own grant (proposal: no, it inherits `documents`); keep `finance` and `health` unconfigured in Stage 3 (no ingestion until Stage 5; the Stage 2 `restricted_domains` entries are replaced by owner-authorised grants under G-021 in Stage 5, via a separately reviewed rule change); `mail_attachment` becomes active only when WP3.3b is accepted.

## 3. Threat model (new assets: the real index, parsers, the consent route, egress)
| # | Threat | Control | Test (L = provable on Linux CI, M = needs the Mac) |
|---|---|---|---|
| T1 | Hostile document or mail text steers the model or widens scope | Content is data; Core scope comes only from grants; citations must be retrieved passages | L: hostile fixtures cannot change `source_scope`, cause an action or alter limitations. M: real-model resistance |
| T2 | Decompression bomb, path traversal, symlink escape, huge or encrypted file | Isolated parser with explicit limits (time, size, depth, files), no network, read-only mount | L: bomb, `../` and symlink fixtures end in `needs_attention`, never silent skip |
| T3 | Index poisoning: injected text persists in the index and is replayed | Retrieved text is labelled untrusted at read time every time; index holds text only, never instructions or grants | L: poisoned fixture is retrieved and still cannot widen scope |
| T4 | Stale grant, cache or index serves revoked content | Revalidate at each read and model boundary (Stage 2); revocation invalidates dependent index entries, caches and citations | L: revoke mid-run, mid-index and after answer (extends Stage 2 tests) |
| T5 | Source deleted or changed but still cited | Version hash in every `EvidenceRef` (Stage 2) plus deletion propagation to index and caches; rebuild on corruption | L: delete, edit and corrupt-index scenarios; stale citation fails closed |
| T6 | Consent route abused by a non-owner client or by content | `role: owner_interactive` only; signed, fresh, replay-protected request (Stage 2 identity) | L: other client, replayed request and content-driven attempt all rejected and audited |
| T7 | Spoofed sender or date believed | `authenticity: claimed`; quoted text never attributed to the sender | L: forged-header and quoted-reply fixtures |
| T8 | Private data leaves through egress (URL, query, path, subdomain, header, image) | Typed tools, taint rule and leak check (policy §10.1), no remote auto-load | L: sentinel secrets in a tainted task are blocked and audited. M: OS-level no-network model worker |
| T9 | Logs, events or CI artefacts contain content | SafeEvent allow-list; new events are enumerations and counts | L: sentinel scans over the new events, index status and consent audit |
| T10 | Index or parser jobs starve interactive work or exhaust disk | Bounded concurrency, back-pressure, explicit visible limits | L: injected slow parser and full disk degrade with explicit states. M: real load |
| T11 | Real owner data processed with a weak key provider | Keychain provider required for real data; file or env provider refused when not in test mode | L: provider-selection tests. M: real Keychain |
| T12 | Crash mid-index or mid-answer duplicates work or loses state | Stage 2 checkpoints and idempotency extended to index jobs | L: crash matrix over index stages (extract, normalise, index, publish) |

## 4. Test matrix by plan acceptance theme
Default deny and revocation: T4, T6. Citation integrity and locators: T5, T7. Injection resistance: T1, T3. Coverage and progressive usefulness: new tests that an answer from a partly built index states `searched/total`, that indexing is newest-first per the per-source definition in the plan, and that time-to-first-useful-answer is measured on the synthetic corpus (threshold frozen before the first baseline, plan line 297). Honest failure: `os_access_missing`, `index_unavailable`, `source_unsupported` each produce a user-safe state. Local-only and egress: T8. Redaction: T9. Durability: T12. Evidence labels: every Linux result is "CI-verified"; every M item stays pending until the Mac.

## 5. What this proposal does not decide
The Core language (G-O20), storage and key custody (G-O02/G-O05; the Stage 3 index is additive, rebuildable and encrypted with its own key), packaging (G-O12), or anything about Finance and Health ingestion (Stage 5). It needs no owner decision.

## 6. If accepted: implementation order (each its own reviewed commit)
1. Schema and OpenAPI 1.1 plus contract tests (no behaviour). 2. Consent routes, identity role, `consent.changed`. 3. Coverage and index-status types with a stub index. 4. Parser adapter and the tier-1 index (WP3.2) test-first on a synthetic corpus. 5. Locators, labels and citation resolution for documents. 6. Egress gateway with fakes. 7. Mail (WP3.3) once the Get Started designation and attachment format matrix are accepted.
