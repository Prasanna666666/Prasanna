# Stage 3, WP3.1: revised proposal (contract-only), for ChatGPT's review

**Status:** REVISED PROPOSAL v2, written to ChatGPT's authoritative brief (PR #8 comment 7051135695). **Nothing in this document is implemented.** No contract, runtime or test code is written until ChatGPT approves this scope. It replaces v1 (commits `44bb884`, `6f93317`), which mixed contract work with consent behaviour and later packages.
**Base:** `aa0fc53` (G-027 recorded). Frozen API 1.0 files at this base: `contracts/atlas-contracts.schema.json` sha256 `65f5a3f6ac41410ea494e2902759a8dca3c2d3ef48e023ebdb6fe548a66a386c`; `contracts/openapi.yaml` sha256 `c653a427fc632dd6f834338b4c1c0cbf6513e12771b541aff68935682e034393`.

## 1. The two corrections, applied
1. **Compatibility.** API 1.0 stays frozen and **byte-identical**; a test pins both hashes. API 1.1 is a *separate* contract, validated only on its own path. Nothing in 1.1 (including "required when 1.1 is negotiated") is ever applied to 1.0. 1.0 compatibility is proved against the 1.0 contract; 1.1 is tested independently.
2. **Consent.** WP3.1 only **specifies** the consent and index endpoints and the identity role as contract text. It implements no route, grant or revoke lifecycle, replay state, OS-permission discovery or enforcement. Those belong to a separately reviewed package (section 7). The earlier acceptance criterion 4 (role enforcement, replay rejection) is removed from WP3.1.

## 2. Version negotiation (specified; the runtime is unchanged)
- Request header `x-atlas-api-version` (already used by Stage 2). **Absent means 1.0.** `1.0` selects 1.0. `1.1` selects 1.1 **only when the server advertises it** in `GET /v1/version`. Any other value, or `1.1` when not advertised, fails closed with the existing `unsupported_version` error. The response echoes the version that was applied.
- A pure function `negotiate(requested, advertised) -> "1.0" | "1.1"` (raises on anything else) lives in `contracts.py` and is tested; the Core runtime still advertises only `("1.0",)` in WP3.1, so a client asking for `1.1` is refused today. A later package changes that line only when it can actually serve 1.1.
- Validation: `contracts.validate(name, value)` keeps its signature and means 1.0 (default). `contracts.validate(name, value, version="1.1")` validates against the 1.1 document.

## 3. Contract diff (1.1 relative to 1.0)
**Mechanism:** a new file `contracts/atlas-contracts.1.1.delta.schema.json` holds only the types that are new or replaced; the 1.1 document is the 1.0 `$defs` overridden by name with the delta (so a replaced `Locator` automatically applies wherever 1.0 references it, such as `EvidenceRef`). The 1.0 file is never edited. 1.1 types that replace a 1.0 type must accept every value the 1.0 type accepted for all unchanged fields (tested), except where a field is newly required (marked below).

| Type | Change | Detail |
|---|---|---|
| `Coverage` (new) | new | `{state: complete \| partial \| indexing, searched: int >= 0, total: int >= 0 \| null, pending: [{category: pattern, count}], failed: [{reason_code, count}], as_of: Timestamp}`, all required, no extra fields; `total` is `null` while discovery is incomplete |
| `AnswerEnvelope` | replaced | 1.0 fields plus `coverage` (**required in 1.1**) and `model` (optional); a `coverage.state` other than `complete` requires the limitation `indexing_incomplete` (checked by a schema `if/then`) |
| `ModelDescriptor` (new) | new | `{model_id: pattern, role: pattern, runtime: mlx \| stub}`; closed, content-free: no prompt, source text, path, query or personal data (negative tests) |
| `Locator` | replaced (superset) | kinds add `header_field`, `attachment_part`, `sheet_cell`; optional `header` (`from\|to\|date\|subject\|message_id`), `attachment_id`, `sheet`, `cell` (A1), `quoted` (boolean), `authenticity` (`claimed`, required with `header_field`) |
| `Limitation` | replaced (superset) | adds `indexing_incomplete`, `source_unsupported`, `os_access_missing`, `attachment_pending` |
| `ErrorCode` | replaced (superset) | adds `os_access_missing`, `index_unavailable` (the user-safe texts are added to `errors.py` in the implementing package, not here) |
| `SafeEvent` | replaced (superset) | adds events `consent.changed` (`action: granted\|revoked`, `source_type`), `model.routed` (`role`, `model_id`), `egress.decision` (`decision`, `reason_code`, `destination_class: search_provider\|connector\|update_manifest\|model_manifest`): enumerations and counts only |
| `IndexStatus` (new) | new | `{state: idle\|building\|rebuilding\|needs_attention, indexed, total \| null, newest_indexed: Timestamp \| null, failed: [{reason_code, count}]}` |
| `ConsentRequest`, `ConsentState` (new) | new | request `{sources: [SourceType], minItems 1, unique}`; state `{grants: [SourceGrant], sources: [{source_type, os_access: granted\|missing\|unknown}]}`. **Shape only.** |
| OpenAPI 1.1 | new file | all 1.0 paths and operation ids unchanged, plus `GET/POST /v1/consent`, `DELETE /v1/consent/{grant_id}`, `GET /v1/index/status`, each marked `x-atlas-status: specification-only; not served`; the owner-interactive role is described as a security requirement of those paths (text only); the negotiation header is defined for every operation |

## 4. Exact file list
**New:** `contracts/atlas-contracts.1.1.delta.schema.json`; `contracts/openapi-1.1.yaml`; `tests/test_contracts_v11.py`; `tests/test_contracts_frozen.py`; `docs/CONTRACT_1_1.md` (contract documentation: negotiation rules, the diff above, compatibility rules); `docs/STAGE3_TRACEABILITY.md` (section 6).
**Changed:** `src/atlas_core/contracts.py` (version-aware loader and `negotiate`; default behaviour identical); `docs/THREAT_REVIEW.md` (one pointer row); `README.md` and `docs/TEST_PLAN.md` (test counts).
**Unchanged, hash-pinned:** `contracts/atlas-contracts.schema.json`, `contracts/openapi.yaml`. **Unchanged code:** `__init__.py`, `api.py`, `service.py`, `errors.py`, `identity.py`, `policy.py`, `policy-rules.json`, every other module. **No new dependency.**

## 5. Test matrix (contract and schema tests only)
- **Frozen 1.0** (`test_contracts_frozen.py`): both 1.0 file hashes; every existing contract and API test passes unchanged; the runtime advertises only `1.0`; a request for `1.1` returns `unsupported_version`.
- **Negotiation** (`test_contracts_v11.py`): absent header selects 1.0; `1.0`; `1.1` accepted only when advertised; `1.2`, `2`, empty, repeated or non-string values fail closed; the response version equals the applied version.
- **1.1 independently**, positive and negative for every new or replaced item: `Coverage` (complete, partial, indexing, `total: null`; missing field, negative count, extra field, bad state); the `coverage` / `indexing_incomplete` rule; `AnswerEnvelope` (valid 1.1 answer; 1.0-shaped answer without `coverage` is invalid in 1.1 and still valid in 1.0); `ModelDescriptor` (valid; prompt text, path, query or extra field refused); the new `Locator` kinds and `authenticity` rule, and that every 1.0 locator is still valid in 1.1; each new `Limitation`, `ErrorCode` and `SafeEvent` (valid; content-bearing extras refused); `IndexStatus`; `ConsentRequest` and `ConsentState` shapes.
- **Redaction sentinel:** none of the new event types or shapes can carry a free-text field (schema-level check that every new string field is an enumeration, pattern or opaque id).
- **OpenAPI 1.1:** valid OpenAPI 3.1 by the same validator as 1.0; every `$ref` resolves against the 1.1 document; every 1.0 path and operation id is present and identical; the new paths carry `x-atlas-status: specification-only`; no new path is reachable on the running Core (the runtime still answers `not_found`).
- **Isolation:** the 1.0 validator (default) never accepts a 1.1-only field.

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

## 10. Decisions I ask ChatGPT to make
1. **1.1 mechanism:** delta file merged over the 1.0 document (my proposal; keeps 1.0 bytes frozen and each change visible), or a full second schema file.
2. **Runtime advertising:** keep `SUPPORTED_VERSIONS = ("1.0",)` in WP3.1 so the Core still refuses `1.1` (my proposal), or advertise `1.1` once the contract exists.
3. **`coverage` required and `model` optional in 1.1 answers** (my proposal: coverage required now; `model` becomes required when the model adapter exists).
