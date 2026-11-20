# Stage 3, WP3.1: revised proposal v3 (contract-only), for ChatGPT's review

**Status:** REVISED PROPOSAL v3. v2 (`eb9af24`) was reviewed in PR #8 comment 7051242604: the boundary and decisions D1 to D3 are **approved**; this revision makes the three requested contract-precision corrections (marked **[v3]**) and nothing else. **Nothing in this document is implemented.** No contract, runtime or test code is written until ChatGPT reviews this revision. It replaces v1 (`44bb884`, `6f93317`).
**Base:** `eb9af24` (v2). The frozen 1.0 hashes below were taken at `aa0fc53` and are unchanged since. Frozen API 1.0 files at this base: `contracts/atlas-contracts.schema.json` sha256 `65f5a3f6ac41410ea494e2902759a8dca3c2d3ef48e023ebdb6fe548a66a386c`; `contracts/openapi.yaml` sha256 `c653a427fc632dd6f834338b4c1c0cbf6513e12771b541aff68935682e034393`.

## 1. The two corrections, applied
1. **Compatibility.** API 1.0 stays frozen and **byte-identical**; a test pins both hashes. API 1.1 is a *separate* contract, validated only on its own path. Nothing in 1.1 (including "required when 1.1 is negotiated") is ever applied to 1.0. 1.0 compatibility is proved against the 1.0 contract; 1.1 is tested independently.
2. **Consent.** WP3.1 only **specifies** the consent and index endpoints and the identity role as contract text. It implements no route, grant or revoke lifecycle, replay state, OS-permission discovery or enforcement. Those belong to a separately reviewed package (section 7). The earlier acceptance criterion 4 (role enforcement, replay rejection) is removed from WP3.1.

## 2. Version negotiation (specified; the runtime is unchanged)
- Request header `x-atlas-api-version` (already used by Stage 2). **Absent means 1.0.** `1.0` selects 1.0. `1.1` selects 1.1 **only when the server advertises it** in `GET /v1/version`. Any other value, or `1.1` when not advertised, fails closed with the existing `unsupported_version` error. The response echoes the version that was applied.
- A pure function `negotiate(requested, advertised) -> "1.0" | "1.1"` (raises on anything else) lives in `contracts.py` and is tested; the Core runtime still advertises only `("1.0",)` in WP3.1, so a client asking for `1.1` is refused today. A later package changes that line only when it can actually serve 1.1.
- Validation: `contracts.validate(name, value)` keeps its signature and means 1.0 (default). `contracts.validate(name, value, version="1.1")` validates against the 1.1 document.
- **[v3] Echo, exactly.** Today the Core sends no version header and the 1.0 OpenAPI documents the request header only in the `SignedRequest` security-scheme description. In the **1.1 OpenAPI file only**: (a) an optional request parameter `ApiVersion` (header `X-Atlas-Api-Version`, enum `1.0`, `1.1`) is added to every operation except `/v1/version`; (b) every non-`/v1/version` response gains a header `X-Atlas-Api-Version` whose value is the version **applied** to that request (`1.0` when the request had no header or asked for `1.0`; `1.1` only when negotiated); (c) **`/v1/version` is the exception**: it is the discovery call, is never negotiated and never refused for its version header, carries no echo header, and returns `{api_version, supported}` exactly as in 1.0 (the runtime already answers it before it looks at the header). The 1.0 file gets none of this and the runtime keeps sending no echo in WP3.1.
- **[v3] Observation for ChatGPT, not decided here:** in 1.0 the version header is **not** part of the signed string (method, path, timestamp, nonce, body hash). A re-labelled request could therefore be negotiated to a different version. For 1.1 I recommend the signed string includes the applied version, and that a 1.1 client refuses a response whose echo differs from what it asked. This is specification text in WP3.1 (a "Signing" paragraph in `CONTRACT_1_1.md`); enforcement belongs to the identity package.

## 3. Contract diff (1.1 relative to 1.0)
**Mechanism (approved D1), specified as a deterministic build/load operation [v3].** A new file `contracts/atlas-contracts.1.1.delta.schema.json` holds exactly three things: `x-overrides` (an array of 1.0 definition names to replace), `x-additions` (an array of new names) and `$defs` (the definitions for both lists). `build_1_1(base, delta)` is a pure function:
1. Start from a deep copy of the 1.0 document and **keep its root metadata** (`$schema`, `$id`, title, description) unchanged; the 1.0 file is never read for writing, never mutated and stays hash-pinned.
2. Refuse (raise) if `x-overrides` or `x-additions` contains a duplicate; if any override name is **not** a 1.0 definition; if any addition name **is** already a 1.0 definition; if a name is in both lists; or if `delta.$defs` contains a name that is in neither list or lacks a definition for a listed name.
3. Replace **only** the listed override definitions and add the listed additions, nothing else; sort the keys so the result is deterministic.
4. Validate the result: every `$ref` resolves, and every definition compiles as a Draft 2020-12 schema.
A replaced `Locator` therefore applies wherever 1.0 references it (for example `EvidenceRef`). Replaced types accept every value the 1.0 type accepted for the unchanged fields (tested), except where a field is newly required (marked below).

| Type | Change | Detail |
|---|---|---|
| `Coverage` (new) | new | `{state: complete \| partial \| indexing, searched: int >= 0, total: int >= 0 \| null, pending: [{category: not_yet_indexed \| attachments \| unsupported_source \| os_access, count}], failed: [{reason_code: unsupported_format \| encrypted \| corrupt \| too_large \| limit_exceeded \| extraction_failed \| timeout, count}], as_of: Timestamp}`, all required, no extra fields **[v3: closed enumerations]**; `total` is `null` while discovery is incomplete |
| `AnswerEnvelope` | replaced | 1.0 fields plus `coverage` (**required in 1.1**) and `model` (optional); the coverage-to-limitation rules of the next subsection are checked by schema `if/then` clauses **[v3]** |
| `ModelDescriptor` (new) | new | `{model_id: pattern, role: pattern, runtime: mlx \| stub}`; closed, content-free: no prompt, source text, path, query or personal data (negative tests) |
| `Locator` | replaced (superset) **[v3]** | `anyOf` of: the exact 1.0 definition limited to the 1.0 kinds (`page`, `block`, `message_part`, `span_only`) with its 1.0 fields only, so every 1.0 locator stays valid and the new fields are **refused on old kinds**; and three strict branches, each with `additionalProperties: false`: `header_field` requires `header` (`from\|to\|date\|subject\|message_id`) and `authenticity` = `claimed`; `attachment_part` requires `attachment_id` and allows optional `page` or `block`; `sheet_cell` requires `sheet` and `cell` (A1 notation). `quoted` (boolean) is allowed only on `message_part` locators |
| `Limitation` | replaced (superset) | adds `indexing_incomplete`, `source_unsupported`, `os_access_missing`, `attachment_pending` |
| `ErrorCode` | replaced (superset) | adds `os_access_missing`, `index_unavailable` (the user-safe texts are added to `errors.py` in the implementing package, not here) |
| `SafeEvent` | replaced (superset) | adds events `consent.changed` (`action: granted\|revoked`, `source_type`), `model.routed` (`role`, `model_id`), `egress.decision` (`decision`, `reason_code`, `destination_class: search_provider\|connector\|update_manifest\|model_manifest`): enumerations and counts only |
| `IndexStatus` (new) | new | `{state: idle\|building\|rebuilding\|needs_attention, indexed, total \| null, newest_indexed: Timestamp \| null, failed: [{reason_code, count}]}` |
| `ConsentRequest`, `ConsentState` (new) | new | request `{sources: [SourceType], minItems 1, unique}`; state `{grants: [SourceGrant], sources: [{source_type, os_access: granted\|missing\|unknown}]}`. **Shape only.** |
| OpenAPI 1.1 | new file | all 1.0 paths and operation ids unchanged, plus `GET/POST /v1/consent`, `DELETE /v1/consent/{grant_id}`, `GET /v1/index/status`, each marked `x-atlas-status: specification-only; not served`; the owner-interactive role is described as a security requirement of those paths (text only); the negotiation header is defined for every operation |

### 3.1 [v3] Coverage state to limitation mapping (schema `if/then`, positive and negative tests)
Rule 1: `indexing_incomplete` is in `limitations` **if and only if** `coverage.state` is `indexing`. Rule 2: `complete` requires `pending: []` and `failed: []`. Rule 3: `partial` requires at least one of `pending` or `failed` to be non-empty and must **not** carry `indexing_incomplete`; each non-empty class must be disclosed by its truthful limitation:

| In `coverage` | Required in `limitations` |
|---|---|
| `state = indexing` | `indexing_incomplete` |
| `pending` contains `attachments` | `attachment_pending` |
| `pending` contains `unsupported_source` | `source_unsupported` |
| `pending` contains `os_access` | `os_access_missing` |
| `pending` contains `not_yet_indexed` while `state = partial` | `partial_work` |
| `failed` is non-empty | `partial_work` |
The equality `searched = total` for `complete` cannot be expressed in a schema; it is a semantic invariant for the coverage implementation package (recorded in `STAGE3_TRACEABILITY.md`, test pending).

## 4. Exact file list
**New:** `contracts/atlas-contracts.1.1.delta.schema.json`; `contracts/openapi-1.1.yaml`; `tests/test_contracts_v11.py`; `tests/test_contracts_frozen.py`; `docs/CONTRACT_1_1.md` (contract documentation: negotiation rules, the diff above, compatibility rules); `docs/STAGE3_TRACEABILITY.md` (section 6).
**Changed:** `src/atlas_core/contracts.py` (version-aware loader and `negotiate`; default behaviour identical); `docs/THREAT_REVIEW.md` (one pointer row); `README.md` and `docs/TEST_PLAN.md` (test counts).
**Unchanged, hash-pinned:** `contracts/atlas-contracts.schema.json`, `contracts/openapi.yaml`. **Unchanged code:** `__init__.py`, `api.py`, `service.py`, `errors.py`, `identity.py`, `policy.py`, `policy-rules.json`, every other module. **No new dependency.**

## 5. Test matrix (contract and schema tests only)
- **Frozen 1.0** (`test_contracts_frozen.py`): both 1.0 file hashes; every existing contract and API test passes unchanged; the runtime advertises only `1.0`; a request for `1.1` returns `unsupported_version`.
- **Negotiation** (`test_contracts_v11.py`): absent header selects 1.0; `1.0`; `1.1` accepted only when advertised; `1.2`, `2`, empty, repeated or non-string values fail closed; the response version equals the applied version.
- **1.1 independently**, positive and negative for every new or replaced item: `Coverage` (complete, partial, indexing, `total: null`; missing field, negative count, extra field, bad state); the `coverage` / `indexing_incomplete` rule; `AnswerEnvelope` (valid 1.1 answer; 1.0-shaped answer without `coverage` is invalid in 1.1 and still valid in 1.0); `ModelDescriptor` (valid; prompt text, path, query or extra field refused); the new `Locator` kinds and `authenticity` rule, and that every 1.0 locator is still valid in 1.1; each new `Limitation`, `ErrorCode` and `SafeEvent` (valid; content-bearing extras refused); `IndexStatus`; `ConsentRequest` and `ConsentState` shapes.
- **Redaction sentinel:** none of the new event types or shapes can carry a free-text field (schema-level check that every new string field is an enumeration, pattern or opaque id).
- **OpenAPI 1.1 [v3: parity of paths and operation ids, plus the permitted delta, not whole-operation identity]:** valid OpenAPI 3.1 by the same validator as 1.0; every `$ref` resolves against the 1.1 document; **every 1.0 path and `operationId` is present** (set equality on the 1.0 side, new paths only the three listed); after removing exactly the permitted additions (the `ApiVersion` parameter, the response `X-Atlas-Api-Version` header, and the retargeting of schema `$ref`s to the 1.1 document) each 1.0 operation equals its 1.1 counterpart; `/v1/version` has neither the parameter nor the echo header and its response schema is the 1.0 `ApiVersion`; the new paths carry `x-atlas-status: specification-only`; no new path is reachable on the running Core (the runtime still answers `not_found`).
- **Deterministic merge [v3]:** `build_1_1` raises on a duplicate override or addition name, an unknown override name, an addition that collides with a 1.0 name, a name in both lists, a `$defs` entry in neither list or a listed name with no definition, and a dangling `$ref`; it keeps the 1.0 root metadata; two runs give identical output; it never mutates the base (deep-equal before and after, 1.0 file hash unchanged).
- **Locator [v3]:** each of `header_field` without `header`, with `authenticity` other than `claimed`, or without `authenticity`; `attachment_part` without `attachment_id`; `sheet_cell` without `sheet` or without `cell` is refused; irrelevant fields are refused (`header` on `page`, `cell` on `block`, `attachment_id` on `message_part`, `quoted` on `page`); every 1.0 locator stays valid.
- **Coverage and limitations [v3]:** positive cases for `complete` (empty pending and failed), `indexing` (with `indexing_incomplete`, with `total: null`), `partial` caused by each of the four pending categories and by failed items (each with its mapped limitation); negative cases: `indexing` without `indexing_incomplete`, `indexing_incomplete` with `partial` or `complete`, `partial` with nothing pending or failed, `partial` with attachments pending but without `attachment_pending` (and likewise for `unsupported_source`, `os_access`, `failed`), `complete` with a non-empty pending or failed, and an unknown category or reason code.
- **Isolation:** the 1.0 validator (default) never accepts a 1.1-only field, and no 1.1 requirement (`coverage`) is applied to a 1.0 answer.

## 6. Threat model T1 to T12 as a traceability matrix (no later test is pretended to exist)
Evidence: **L** = provable on Linux CI, **M** = needs the Mac. Status of every row except "existing" is **pending**. Package names are those of section 7.

| # | Threat | Control owner | Implemented by | Test (proposed name; pending unless marked) | Evidence |
|---|---|---|---|---|---|
| T1 | Hostile content steers model or widens scope | Core scope from grants only (existing `policy.py`, `gate.py`) | Existing; real-model part in WP3.4 | existing hostile-source tests; `test_real_model_injection_resistance` (M) | L existing; M pending |
| T2 | Parser bombs, traversal, symlinks, encrypted or huge files | Isolated parser with explicit limits | WP3.2 parser package | `test_parser_limits_end_in_needs_attention` | L |
| T3 | Index poisoning replayed | Retrieved text labelled untrusted at read time | WP3.2 index package | `test_poisoned_passage_cannot_widen_scope` | L |
| T4 | Stale grant, cache or index serves revoked content | Revalidation (existing); index and cache invalidation | Existing; index part in WP3.2 | existing revocation tests; `test_revocation_invalidates_index_entries` | L |
| T5 | Deleted or changed source still cited | `EvidenceRef.version_sha256` (existing) plus deletion propagation | WP3.2 index package | `test_source_change_invalidates_citation_and_index` | L |
| T6 | Consent route abused by a non-owner client or content | Owner-interactive role and replay protection (specified in WP3.1, built in the consent package) | Consent package | `test_only_owner_interactive_client_can_change_consent` | L |
| T7 | Spoofed sender or date believed; quoted text misattributed | `authenticity: claimed`, `quoted` flag (schema in WP3.1) | WP3.3 mail package | `test_quoted_text_never_cites_the_sender` | L |
| T8 | Private data leaves through egress | Typed tools, taint rule, leak check (policy §10) | Egress package; OS isolation in WP3.4 | `test_tainted_task_cannot_exfiltrate`; `test_model_worker_has_no_network` (M) | L / M |
| T9 | Logs, events or artefacts contain content | SafeEvent allow-list; new events are enumerations (schema in WP3.1) | WP3.1 (shape), each package (use) | schema sentinel test in section 5 (this package); per-package sentinel scans | L |
| T10 | Index or parser jobs starve interactive work or fill the disk | Bounded concurrency and explicit limits | WP3.2 and WP3.6 | `test_slow_parser_and_full_disk_degrade_explicitly`; real load (M) | L / M |
| T11 | Real data processed with a weak key provider | Keychain provider required for real data | WP3.6; real Keychain on the Mac | `test_real_data_requires_keychain_provider` (L); real Keychain (M) | L / M |
| T12 | Crash mid-index or mid-answer duplicates or loses state | Stage 2 checkpoints and idempotency extended to index jobs | WP3.2 index package | `test_index_crash_matrix` | L |

## 7. Later packages (not WP3.1; each separately reviewed on its exact SHA)
(a) consent and identity behaviour (routes, grant and revoke lifecycle, owner-interactive enforcement, replay, OS-access discovery); (b) parser adapter and tier-1 index with newest-first ordering and coverage; (c) locators, labels and citation resolution for documents; (d) egress gateway with fakes; (e) Mail (WP3.3), then attachments; (f) model adapter (WP3.4) and the Mac client (WP3.5).

## 8. Commands and results
**Baseline at the base (developer-reported, local):** `core` 167 passed on Python 3.13 and 3.11, ruff and mypy clean; `kit` 165 (including `kit/tests/test_architecture.py`), `images` 100, `library` 299, `atlas` 111, `finance` 701. **CI-verified:** `bdfc343` 22 of 22 checks successful; the later heads are not yet complete.
**Commands for the implementation commit (from `core/`):** `ruff check .`; `mypy src`; `python -m pytest -q -p no:cacheprovider` (Python 3.13 and 3.11); `sha256sum contracts/atlas-contracts.schema.json contracts/openapi.yaml` (must equal the hashes above); from each of `kit/`, `images/`, `library/`, `atlas/`, `finance/`: `python -m pytest -q -p no:cacheprovider`; exact-string mutation checks (alter one 1.0 byte, drop a required 1.1 field, let a 1.1 field validate on 1.0, advertise 1.1 in the runtime): each must fail a test.

## 9. Rollback and evidence classification
**Rollback:** `git revert` of the implementation commit; API 1.0 files, runtime and clients are untouched, so nothing depends on 1.1.
**Evidence:** contract, schema, negotiation and frozen-hash tests are Linux-provable: developer-reported until GitHub Actions completes for the exact head, then CI-verified. Every M row in section 6 stays pending hardware. No performance claim. No network, no real owner data, no new dependency.

## 10. Decisions
1. **1.1 mechanism: APPROVED** by ChatGPT (comment 7051242604): delta merged over the frozen 1.0 definitions, specified as the deterministic operation in section 3.
2. **Runtime advertising: APPROVED:** `SUPPORTED_VERSIONS = ("1.0",)` stays; a 1.1 request fails closed until a later reviewed package serves it.
3. **Answer fields: APPROVED:** `coverage` required and `model` optional in 1.1; no 1.1 requirement reaches 1.0 validation.
4. **Open, for ChatGPT [v3]:** whether the 1.1 signed string includes the applied version (section 2 observation). Specification text only in WP3.1.
