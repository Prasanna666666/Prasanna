# Atlas — implementation-to-documentation conformance audit

**Created:** 2026-11-25  
**Current code/test patch baseline:** PR #8, branch `genesis-stage2-foundation`, `67c7ee475db4188b0460a48807a8f0210c78a7d9` (latest source/test/contract/UI-test patch snapshot; exact-head CI run 45576209883 queued)  
**Branch head:** refresh from GitHub before resuming; this document deliberately avoids a self-referential HEAD hash  
**Purpose:** Establish one evidence-led method for deciding whether the completed implementation matches the canonical product and technical documentation.

## 1. Scope and non-claims

This is the audit control document, not a declaration that conformance has passed. The code/evidence baseline contained 282 PR-changed paths, including macOS app sources, Atlas Core, iOS client sources, tests, contracts, scripts and documentation. File presence alone does not establish end-to-end behaviour.

The PR description records bounded acceptances for Stage 2, WP3.1 and WP3.2, but those acceptances apply only to their named scopes and exact commits. Stage 3 is not accepted. Stage 4–8 work is present on the branch but is not architect-reviewed or accepted. The CI run associated with the observed head was queued when checked. No result is inferred from a queued run.

## 2. Canonical requirement sources

| Priority | Source | What must be reconciled |
|---|---|---|
| 1 | `docs/genesis/PRD.md` | Product promise, functional behaviour, scope, autonomy/approval, platform and service requirements |
| 2 | `docs/genesis/UI_UX_SPECIFICATION.md` | Everyday navigation, hierarchy, dashboards, contextual Spaces, screens, states, accessibility |
| 3 | `docs/genesis/TARGET_ARCHITECTURE.md` | Boundaries, flows, contracts, security controls and sole stage roadmap (§11) |
| 4 | `docs/genesis/USE_CASE_REGISTER.md` | User journeys, integrations, normal/failure/edge cases and acceptance evidence |
| 5 | `docs/genesis/DECISIONS.md` | Owner decisions, recommendations and unresolved decisions |
| 6 | `docs/genesis/LOW_LEVEL_DESIGN.md` and focused Genesis specifications | Data models, state transitions, algorithms, retention, ingestion, memory, intelligence and network behaviour |
| 7 | `core/docs/*`, `app/README.md`, `ios/README.md` | Implementation contracts, platform-specific constraints, technical evidence and limitations |

If two documents conflict, record the conflict before changing either. PRD governs product behaviour; UI/UX governs interaction and presentation; TARGET_ARCHITECTURE §11 governs stage sequence; DECISIONS governs accepted owner choices; DELIVERY_PROTOCOL governs process and acceptance.

## 3. Classification vocabulary

Each requirement is assigned exactly one primary status:

- **ALIGNED** — implementation and tests support the documented behaviour; no material discrepancy found.
- **PARTIALLY ALIGNED** — a meaningful portion works, but one or more specified paths, states, constraints or edge cases do not.
- **DOCUMENTATION DRIFT** — implementation is intentionally or demonstrably correct, but one or more documents are stale, contradictory or inaccurate.
- **NOT IMPLEMENTED** — the documented requirement has no corresponding implemented behaviour at the audited commit.
- **UNVERIFIED** — evidence is insufficient (for example, code exists but no relevant test, test not run, target hardware unavailable, or real integration not exercised).
- **NOT APPLICABLE / DEFERRED** — only when the canonical scope explicitly says so and the reason/stage is recorded.

Do not label a requirement ALIGNED based only on a symbol, file, mock, stub, unit test of an isolated helper or developer assertion.

## 4. Required traceability record

For every PRD requirement and every use case, record:

| Field | Required content |
|---|---|
| Requirement/scenario ID | Stable canonical ID and exact document section |
| User-visible promise | What the owner expects Atlas to do |
| Implementation | Exact source path(s), symbol(s), platform and commit |
| Runtime path | Entry point → Core/service → policy → data/provider → result/UI |
| Data and permissions | Sources, sensitivity, grants, retention, external egress and revocation |
| Tests | Exact test path/name and what it proves; include negative/adversarial/restart tests |
| Evidence | Exact CI run/result, manual exercise and environment; identify target-Mac requirements |
| Failure behaviour | Offline, denied permission, partial coverage, timeout, crash/restart, duplicate/conflict and unsupported input |
| Classification | One status from §3 |
| Documentation action | Exact file/section to correct, or “none” |
| Residual risk / owner decision | Named gate, decision or limitation |

A requirement with no traceability row is **not audited**.

## 5. Granular review dimensions

### 5.1 Product and experience
- Single coherent personal smart intranet, not a collection of mini-apps.
- Calm everyday UX; persistent navigation limited to Home, Ask Atlas, Explore and Library; specialist capabilities contextual.
- Chat, voice, dashboards, notifications, task activity, search/history and capability discovery.
- Personal context and Spaces; cross-domain retrieval without leaking across permission boundaries.
- Discover/news, finance/investments, sports/statistics, home/energy, travel, health, fitness, work/projects and shopping capabilities where specified.
- Every screen's loading, empty, partial, stale, offline, denied, error, success and destructive-confirmation states.
- Accessibility, keyboard/VoiceOver, dynamic type, contrast, reduced motion and responsive layout.

### 5.2 Functional behaviour
- Local sources, Mail, Calendar, public research and every connector actually claimed as supported.
- Read/write scope, authentication, credential storage, rate limits, event/poll cadence, sync, deduplication and disconnect/revocation.
- Search, indexing, progressive newest-first coverage, ranking, citations, provenance, multilingual content and unsupported-format handling.
- Memory creation, relevance, source traceability, correction, expiry, deletion, sensitive-data controls and cache invalidation.
- Model selection/routing, model identity, deterministic tools, answer verification, uncertainty and no-cloud-fallback behaviour.
- Task orchestration, durable state, retries, cancellation, idempotency, concurrency, receipts and undo/compensation.
- App/browser automation: typed capabilities, isolation, prompt-injection/taint controls, exact approval binding and postcondition verification.
- Home energy: measured versus estimated values, meter/device coverage, units, tariffs, time zones, gaps and schedule-to-usage comparisons.
- Finance: source freshness, currency/FX, deterministic arithmetic, exposure/overlap and no unauthorised transactions.
- Sports/Stats and Discover: entity/season resolution, live-versus-historical status, source timestamps and citation accuracy.

### 5.3 Security, privacy and reliability
- Owner-client identity, enrolment/revocation, request freshness, replay protection and settings authority.
- Permission checks at every read/model/action boundary; grant narrowing and immediate revocation semantics.
- Local data protection, Keychain, secrets, logs, backups, restore, migration and rollback.
- Public-web egress data minimisation, taint handling, bounded guarantees and explicit disabled-by-default gates.
- Untrusted documents, email, attachments, webpages, calendar invites and agent outputs.
- Process crash, host reboot, power loss, partial writes, provider timeout and duplicate external side effects.
- Resource pressure, thermal behaviour, background budgets and interactive priority.

### 5.4 Delivery and operations
- Native macOS packaging, self-contained installation, launch/restart, TCC, signing/notarisation and updates.
- Target-Mac model runtime, real-model quality, latency, memory and energy measurements.
- iOS secure remote access, device trust, offline behaviour, sync, conflict handling and revocation.
- Operational diagnostics, support/recovery instructions and owner-visible system health.

## 6. Evidence rules

1. Freeze the exact commit before reviewing. Any code change invalidates claims tied to the previous head unless re-run/re-reviewed.
2. Read source code and tests; do not rely on PR prose alone.
3. For every claimed passing suite, capture the workflow run URL, job, commit SHA, environment and result. A queued/running job is not a pass.
4. Distinguish unit, integration, contract, end-to-end, UI, adversarial, performance and owner-machine evidence.
5. A test proves only the behaviour it exercises. Record omitted paths and negative cases.
6. Never infer target-Mac, real-account, real-Internet or human UX success from hosted CI.
7. A source file, test fixture, protocol stub or mock is not proof of a production integration.
8. Keep historical exact-commit acceptances intact; do not transfer them to a later head.
9. Preserve all review comments and classify them as current/outdated, resolved/unresolved, addressed/not addressed. Do not close comments merely because a nearby code change exists.
10. Do not merge, release or mark owner acceptance as complete as part of this documentation audit.

## 7. Baseline observations (2026-11-25)

- PR #8 is open, draft and unmerged; observed head: `83eec5378fff9f26f435492104c4efa2b30d18ca`.
- PR changed-file inventory: 281 paths.
- Review-thread snapshot: 127 total; 21 resolved and 106 unresolved. Of the unresolved threads, 31 were marked outdated and 75 current at the time queried. This is a point-in-time count, not a claim that every thread is a valid defect; each must be reconciled.
- The workflow run associated with the observed head was queued; no passing result is claimed for that run.
- PR description records earlier exact-scope acceptances: Stage 2 at `58210223398a5715b618d1163397104efd358d49`; WP3.1 at `800d13743f6cf4ce0ab87b4b8e098d441e459a56`; WP3.2 at `ad6e59bcb6fb5d6124ac56ea419f8330dc913e4c`.
- Stage 3 is not accepted; F-4, F-11, F-12 and F-13 are identified as unmet, unwaived and release-blocking in the PR description and `core/docs/STAGE3_ACCEPTANCE.md`.
- Stage 4–8 work is present but not architect-reviewed or accepted; see `core/docs/STAGES_4_TO_8.md`.

## 8. Documentation cleanup completed before code conformance

The 2026-11-25 documentation-only pass established a single root index and canonical Genesis index, rewrote the handover as a concise current operational summary, corrected the PRD review-status metadata, corrected the UI/UX implementation-status/handoff text against `core/docs/UI_IMPLEMENTATION_MAP.md`, and added this conformance framework. The review ledger was refreshed. These edits reconcile navigation and status framing; they do not prove all detailed technical documents are free of contradictions.

The documentation-only cleanup commits are listed in `docs/genesis/HANDOVER.md`. The code/evidence baseline remains `83eec5378fff9f26f435492104c4efa2b30d18ca`; the captured checkpoint `80dbd8584201aafce3697f28e3ec35fb6d5f42af` was followed by additional docs-only commits; refresh the live branch head before resuming.

## 9. Completion criteria for this audit

The audit may be called complete only when:
- Every current canonical PRD requirement and every registered use case has a traceability row.
- Every integration and platform promise is classified, including unsupported/deferred cases.
- All high-impact security, privacy, approval, data-loss and external-side-effect paths have negative/adversarial tests or an explicit unverified gate.
- All user-visible screens and states are reconciled with the canonical UX specification.
- Every material documentation conflict is corrected at its canonical source and cross-links are consistent.
- Every changed PR path is classified as inspected, generated/vendor, historical, or not relevant—with rationale.
- All review threads are reconciled; no current material unresolved blocker is hidden.
- Exact-head CI is complete and results are recorded; manual/owner gates remain explicitly separate.
- A final summary states what is aligned, what drift was corrected, what is not implemented, what remains unverified, and why.

**Current audit status: DOCUMENTATION ENTRY-POINT CLEANUP COMPLETE; REQUIREMENT-BY-REQUIREMENT CONFORMANCE NOT COMPLETE.** The first documentation cleanup is committed. Detailed document-to-document consistency and code-to-document tracing remain. They do not claim that all implementation paths have been inspected or that the product is release-ready.


## 10. Latest live PR snapshot after documentation-only cleanup

At captured head `80dbd8584201aafce3697f28e3ec35fb6d5f42af`, PR #8 remained open, draft and unmerged; 282 changed paths were reported; 127 review threads remained (21 resolved, 106 unresolved: 36 outdated and 70 current). These counts are point-in-time values. No workflow run or combined status was returned for this exact documentation-only head; CI status must be checked separately before claiming green CI.

The subsequent technical-document corrections are recorded in `docs/genesis/HANDOVER.md`. The latest exact branch head must be refreshed live; the code/evidence baseline for this documentation pass remains `83eec5378fff9f26f435492104c4efa2b30d18ca`.

## Additional roadmap/decision consistency corrections — 2026-11-25

- `TARGET_ARCHITECTURE.md` §11 now distinguishes the ordered roadmap from actual authorisation/acceptance and records the owner's 2026-11-23 instruction placing Stage 4–8 work on PR #8.
- `DECISIONS.md` G-O09 now records the bounded Stage 2 acceptance at its exact historical SHA; later commits are not implicitly accepted.
- `DELIVERY_PROTOCOL.md` labels the original Stage 2 entry gates as historical rather than current blockers.
- Commits: `18002761b7190a8121639c0bc187ab5001422e87` (roadmap status), `7eb30dbac13d24f2ac8e5354c725c3683f6687f1` (decision register), `441c7b6df228c7378cc7105ef97eb1aa12e2fb00` (delivery protocol).

Additional documentation-only corrections in the final pass: `3706b95afd02b038d26134300c8ed568f91142c2` corrected the API 1.1 contract title/status; `6e463c714f963e3f42c3fabbc6d191d200353088` corrected the handover's API 1.1 status; `83051aea4269c4a178b371ef15fdca741cfc1a94` corrected Stage 3 handover egress/rollback wording and the PR description; `4ade8a8b526826e0d037876b113fa1220f17c818` removed the remaining Stage 3 egress-path wording conflict; `b230633b3b8d027576be42f6a6508c638e6e3a6f` aligned the handover with the criterion matrix. Review snapshot after those changes is recorded in `REVIEW_COVERAGE_RECONCILIATION.md`.

## Additional package-level documentation corrections — 2026-11-25

- `STAGE-3-EXECUTION-PLAN.md`: WP3.2 coverage limitation is labelled as true at the accepted WP3.2 commit; WP3.4 API 1.1 coverage is recorded as the later change. The plan no longer says API 1.1 is unserved.
- `STAGE-2-WORK-PACKAGE.md`: historical entry gate text now records the subsequent exact-scope Stage 2 acceptance and separate Stage 3 authorisation.
- `WP3_2_DOCUMENTS.md` and `WP3_3_MAIL.md`: historical package snapshots distinguish what was true at package acceptance from later API 1.1 coverage and the implemented-but-real-store-unverified EMLX reader. Mail attachments remain unread.
- `core/docs/TRACEABILITY.md`: explicitly historical Stage 2 baseline; later grants and stages are not implied by its old rows.
- `EGRESS_GATEWAY.md`: public research is documented as a separate API 1.1 operation, not ordinary answer generation.
- `TEST_PLAN.md` and `WP3_5_CLIENT.md`: older Linux/reference-client snapshots are no longer presented as the current app/CI state.
- `OWNER_ACCEPTANCE_CHECKLIST.md`: distinguishes native framework CI coverage from synthetic `.emlx` fixtures and the unverified real Mail store.
- Commits: `08b973d7d3e6213c2ec63ad14dd0e8780a73733a`, `bd4d0bd05a8b03f9d8454a1e396d8c0405301e07`, `cefb48de9a0177c8f5bd035330ab9fdc2bbfa020`, `30a665987e54c119f01ac5bfe8455125cf2b96de`, `35e16243b6a3ddc43bae2dbdb24984f9c9869d9a`, `7cf97cbf1574b81d0084c2d40c200743fa664a8b`, `58b7e2de4b203977e437338f33928856484fdda4`, `2418e38f958d8be1600bf16711bd6b1800c020b1`, `36a8379f253e321103148d88e8aaa46752fb04e5`, and `408add907fb0b5a33151c52c66a1e8a213ff51f3`.
## 11. Final granular documentation and initial conformance findings — 2026-11-25

### 11.1 Documentation corrections made in this pass

- Reconciled LOW_LEVEL_DESIGN.md with owner decision G-021. Its prior blanket prohibition on Finance records entering model context contradicted DECISIONS.md, TARGET_ARCHITECTURE.md, MEMORY_PRIVACY_KNOWLEDGE.md and the implemented policy tests. The LLD now records the same rule: Finance and Health may enter local model context only under an exact, current, purpose-bound owner grant; Finance arithmetic/balances remain deterministic and code-checked; private domain content is barred from public web, cloud inference, logs and unrelated tasks.
- Replaced the LLD's stale pre-implementation rule with a historical process note. The implementation exists, but this does not imply the full LLD or PR #9 was independently accepted.
- Corrected UI_IMPLEMENTATION_MAP.md: the Ask composer has microphone dictation and answers can be read aloud (not a full live voice conversation); phone pairing exists; in-app backup/restore controls remain absent.
- The corresponding source-of-truth decision remains G-021 in DECISIONS.md. The Stage 3 baseline audit and Stage 2 traceability documents remain historical snapshots and must not be read as current implementation inventories.
- No application source or tests were changed in this pass.

### 11.2 Confirmed implementation conformance observations

| Area | Classification | Evidence / exact current limitation |
|---|---|---|
| Product identity, local-first boundary and owner-controlled Core | PARTIALLY ALIGNED | The branch contains the native SwiftUI client, Python Core, local model worker, policy gates and a future iOS client. The iOS client and relay are implemented in code/tests, but secure remote use on the owner's phone and owner-selected VPN/channel are not owner-verified. |
| Stage 3 source-to-answer vertical slice | PARTIALLY ALIGNED | core/docs/STAGE3_ACCEPTANCE.md records 8 MET-L, 6 PARTIAL and 1 PENDING-M; Stage 3 is NOT ACCEPTED. Open findings: ATLAS-CORE-092 (P1), ATLAS-EXACT-106 (P1), ATLAS-CORE-083 (P1), ATLAS-CORE-084 (P2). |
| Revocation and read-surface freshness | PARTIALLY ALIGNED | Task pipeline revalidation is tested, but Finance/Health summary, Library Search and citation passage API reads lack a final grant-identity/expiry check immediately before response; concurrent revoke race ATLAS-CORE-092 remains open. |
| Exact arithmetic | PARTIALLY ALIGNED | Exact rational operations are implemented, but terminating values requiring more than 28 significant digits may be rounded by the default Decimal context while labelled exact; ATLAS-EXACT-106 remains open. |
| Shutdown and construction failure | PARTIALLY ALIGNED | Crash recovery/cancellation tests exist; Core.close() can close SQLite dependencies after a five-second join while a worker is still active, and partial construction can leak opened stores; ATLAS-CORE-083/084 remain open. |
| Local model isolation | PARTIALLY ALIGNED / UNVERIFIED | Linux seccomp and hosted macOS sandbox-exec tests, including a small real MLX model, are documented. The macOS profile is explicitly not least privilege; owner hardware/model performance, real-model injection resistance and target-Mac verification remain open. |
| Public Internet research | PARTIALLY ALIGNED / DEFERRED | Separate API 1.1 research operation is implemented behind two off-by-default gates; it is not part of ordinary answer generation and has not been exercised against the real Internet. Final gate F-11 remains unmet. |
| Finance and Health | PARTIALLY ALIGNED | G-021 policy and synthetic grant tests exist. Stage 5 report says real Finance/Health source adapters and owner-facing grant flow are not built; real Finance/Health data flow is not proven. Legacy Finance migration is limited to the transactions table and has not been run on a real database. |
| Connectors and home automation | PARTIALLY ALIGNED | Generic connector framework/profile and reversible-action policy are implemented/tested. No real vendor adapter has been selected or exercised; real home hub/device automation is not established by the generic connector tests. |
| App/browser automation | PARTIALLY ALIGNED / DEFERRED | Policy/orchestration and fake-browser tests exist. Production browser worker remains off until OS-enforced confinement is accepted; general browser interaction and native-app automation are not established as complete. |
| macOS/iOS UI | PARTIALLY ALIGNED / UNVERIFIED | UI implementation map records built screens and hosted CI evidence, but no owner visual walkthrough, screenshots, VoiceOver/keyboard/Dynamic Type/Reduce Motion acceptance. Approval sheet is not reachable through a live proposed-action flow; backup/restore remains CLI-only; activity is in-memory. |
| Real source/platform integration | UNVERIFIED | Hosted macOS tests exercise native frameworks and Keychain with throwaway data, but no owner TCC walkthrough, real Apple Mail store, owner data, owner Keychain prompts, FileVault/power-loss, signed/notarised install or owner Mac lifecycle test has been completed. |
| Stage 4–8 programme | UNVERIFIED / NOT ACCEPTED | Developer report lists substantial code and synthetic tests, but explicitly says these stages are not architect-reviewed or accepted. Do not infer acceptance from implementation presence. |

These findings are bounded to the current documents and evidence records. They are not a completed row-by-row audit of all PRD requirements, all use cases, all 282 changed paths or all 127 review threads.

### 11.3 Latest live repository snapshot

- PR #8 remains open, draft and unmerged.
- Latest observed documentation head at this update: refresh from GitHub before relying on it; this document avoids a self-referential hash.
- PR changed paths: 282.
- Review threads: 127 total; 21 resolved; 106 unresolved. Of the unresolved threads, 40 are outdated and 66 are current (52 threads outdated overall; 75 current overall).
- Exact-head CI at commit 1713785c432e6a967cd163964c3d69aa1c639788: run 45564148620 was queued; combined status returned no entries. No CI pass is claimed for that head or later documentation commits.
- The code/evidence snapshot remains 83eec5378fff9f26f435492104c4efa2b30d18ca; intervening commits recorded in the handover are documentation-only.

### 11.4 Audit completion status

**Documentation authority and known contradiction cleanup: substantially complete, not certified exhaustive. Implementation conformance: IN PROGRESS, NOT COMPLETE.** Remaining work is to finish the canonical PRD/use-case/screen traceability matrix, inspect every changed path and review thread, verify all claims against source/tests, and capture exact-head CI. No merge, release, stage acceptance or owner acceptance is implied.
## 12. Final technical-document pass checkpoint — 2026-11-25

- Additional documents reconciled: `PRD.md`, `DECISIONS.md`, `INTERNET_AND_NETWORK_POLICY.md`, `STAGE-3-EXECUTION-PLAN.md`, `DEFECT_REGISTER.md`, `REVIEW_COVERAGE_RECONCILIATION.md`, `core/docs/CONNECTOR_PROFILE.md`, `ADR_STORAGE_KEYS.md`, `ENROLMENT.md`, `G_O19_DESIGNATION.md`, `PLUG_IN_GUIDE.md`, `ROLLBACK.md`, `EGRESS_GATEWAY.md`, `STAGE3_ACCEPTANCE.md`, `STAGE3_TRACEABILITY.md`, `STAGE3_HANDOVER.md`, `CONTRACT_1_1.md`, `openapi-1.1.yaml`, `PROGRAMME_AUDIT.md`, `OWNER_ACCEPTANCE_CHECKLIST.md`, `MACOS_PROVIDERS.md`, `STAGES_4_TO_8.md`, and `app/README.md`.
- The OpenAPI 1.1 root security default is `SignedRequest`; `/v1/enrol` and `/v1/devices/pair` now explicitly override it with `security: []`, matching their one-time bootstrap/offer-code runtime semantics. CI/schema validation for this spec edit is pending.
- Final live snapshot at `d877a4ec3ce02244a070eb1dbbdaf021e6988de0`: 282 changed paths; 127 review threads (21 resolved, 106 unresolved; 73 unresolved outdated, 33 unresolved current). Exact-head workflow query returned no run and combined status had no entries.
- The current technical-document pass has corrected the known contradictions found in the current review threads. This does not mean all 282 changed paths, 33 current unresolved threads, all use cases, or every requirement have been reviewed/closed. Implementation conformance remains IN PROGRESS and NOT COMPLETE.
## 13. Code/test review reconciliation — 2026-11-25

### 13.1 Review findings verified as addressed in the current source snapshot

| Finding | Current evidence | Result |
|---|---|---|
| App-owned Core lifecycle | `AtlasApp.swift` calls `Launcher.shared.stop()` in `applicationWillTerminate`; `CoreLauncher.stop()` terminates, waits, escalates if needed and reaps. `EndToEndTests.swift` covers stop/reap, idempotent start, crash/relaunch, stale socket/PID and a live unidentified listener. | Addressed in code/tests; human owner quit walkthrough remains unverified. |
| Live socket preservation | `CoreLauncher.reapLeftovers()` probes the socket and refuses startup without unlinking if an unidentified listener still answers. | Addressed in code/tests; corresponding review thread resolved. |
| EMLX regular-file replacement | `EmlxMailbox._parse()` derives Message-ID from bytes read through the opened descriptor and refuses a changed identity; `test_a_regular_file_replaced_by_a_different_message_after_listing_is_never_returned_under_the_old_identity` covers the regular-file swap. | Addressed in code/tests; real Apple Mail store remains unverified. |
| Private-name egress fingerprints | `TaintSet` fingerprints non-stopwords of at least four letters and two-word runs from question and passages; `test_egress.py` covers `Alexandra`/`alexandra`, short phrases, URL host/path/query/fragment and encoding variants. | The exact one-word/short-phrase bypass in the review comments is addressed; broader 1–3-character and semantic-paraphrase limits remain. Research stays disabled by default. |

These review threads were replied to and resolved after checking the current source and regression tests. Resolution applies only to the specific finding in each thread; it does not close related broader defects or acceptance gates.

### 13.2 Remaining current code/test findings

| Finding | Classification | Why it remains open |
|---|---|---|
| ATLAS-EXACT-106 (`core/src/atlas_core/exact.py`) | P1 / NOT ALIGNED | `Number.exact_decimal` divides `Decimal` values using the default 28-digit context. The parser permits much larger values; a terminating decimal with more than 28 significant digits can be rounded and still labelled exact. No context-independent exact conversion is implemented. |
| Connector undo (`core/src/atlas_core/connectors.py`) | NOT ALIGNED | Reversible-action undo returns normally when `previous` is missing/invalid or credentials are unavailable; `ActionGateway.undo()` can then record success although no compensation occurred. `CONNECTOR_PROFILE.md` now discloses this. |
| API free-text schema boundary (`core/tests/test_contracts_v11.py`) | NOT ALIGNED / TEST GAP | `new_string_fields()` only discovers explicit string schemas. Open object maps such as action payload/result, sync operation payload and record fields have no `additionalProperties: false` or value schema, so arbitrary nested strings can pass while the test claims only approved free-text fields exist. |
| OpenAPI path-count test name (`core/tests/test_contracts_v11.py`) | DOCUMENTATION/TEST DRIFT | The test name says “three new paths” while `NEW_PATHS` contains 32 additive paths (39 total in 1.1 vs 7 in 1.0). The contract documentation now distinguishes the original three WP3.1 paths from the later 1.1 additions, but the test name itself remains misleading. |
| Native Keychain CI fixture (`core/tests/test_macos_native.py`) | TEST ISOLATION GAP | The real-Keychain production-Core test preflights/deletes only six fixed services plus the anchor, while `host.build_config()` provisions the complete `host.KEY_NAMES` set, including Finance/Health and native-domain indexes. A local run can reuse or leave production-named Keychain items. `MACOS_PROVIDERS.md` now warns to use an isolated throwaway Keychain until fixed. |
| Stage 3 source/read freshness (`ATLAS-CORE-092`) | P1 / PARTIALLY ALIGNED | Some read surfaces still lack a final grant identity/expiry recheck immediately before response; concurrent revocation can race a read. |
| Core shutdown/construction (`ATLAS-CORE-083/084`) | P1/P2 / PARTIALLY ALIGNED | `Core.close()` can close SQLite dependencies after a bounded join while a worker remains active; partial construction can leak opened stores. |

### 13.3 Current PR/review/CI checkpoint

- PR #8 head: `533a2460f3f013690a862d029488dc42d9611fb4`; open, draft and unmerged; 282 changed paths.
- Review threads: 127 total; 44 resolved; 83 unresolved. Of the unresolved, 78 are outdated and 5 are current. The five current threads concern exact arithmetic, API free-text schema coverage, connector undo semantics, the OpenAPI path-count test name, and native Keychain test cleanup. Outdated unresolved threads are not proof that a finding was fixed; they still need reconciliation against the current code.
- Exact-head CI run 45565642702 was queued; combined status returned no entries. No pass is claimed.
- No application/Core source or tests were changed during this documentation/conformance pass. The API 1.1 OpenAPI contract and documentation were updated. The code evidence baseline remains `83eec5378fff9f26f435492104c4efa2b30d18ca`.

### 13.4 Completion judgement

**Documentation corrections and current-document review-thread reconciliation: substantially complete. Full document inventory certification: not complete. Implementation conformance: NOT COMPLETE.** The current five review threads are all source/test findings; the 78 unresolved outdated threads still require a final stale-thread disposition. The 282 changed paths and all PRD/use-case requirements have not yet been traced row by row. Do not mark the implementation aligned, Stage 3 accepted, or PR ready to merge.

## 14. Final documentation inventory checkpoint — 2026-11-25

- Reconciled the remaining active historical-status contradictions in `core/docs/DESIGN.md`, `core/docs/THREAT_REVIEW.md`, `core/docs/WP3_6_RELIABILITY.md`, `docs/genesis/STAGE-2-WORK-PACKAGE.md`, `docs/genesis/STAGE-3-BASELINE-AUDIT.md` and `docs/genesis/STAGE-3-CONTRACT-DELTA.md`. This removes duplicate evidence notes, scopes Stage 2 hard-deny/Swift verification claims to their original snapshot, and makes the later API 1.1 serving status explicit.
- `UI_UX_SPECIFICATION.md` remains the target UX contract; `UI_IMPLEMENTATION_MAP.md` is the current implementation/evidence register. The specification itself correctly keeps architect and owner visual/accessibility acceptance open.
- Latest live snapshot at `d66cb24907d77746a96814f0865dead0448b363e`: PR #8 open/draft/unmerged; 282 changed paths; 127 review threads (44 resolved, 83 unresolved; 78 unresolved outdated, 5 unresolved current). Exact-head CI run 45566805549 is queued; combined status has no entries.
- The active canonical docs have been substantially reconciled. Historical conversation/branch archives are retained as records, not re-authored. This remains short of a certified exhaustive audit of every historical artifact, all 282 changed paths, all requirements and all review threads.


## 15. PR-description correction and final CI checkpoint — 2026-11-25

- The PR #8 description was corrected to remove the broad claim that private-name/short-phrase egress is fully fixed or that private-data egress is guaranteed. It now distinguishes the specific regression-tested bypass from the remaining 1–3-character, paraphrase, stale-passage, DNS, truncation and malformed-URL findings.
- Immediately before this note, the live head was `0c8f63118a1c286aa55da270afc30aebc4b20838`; CI run 45567148195 was queued; combined status had no entries. PR #8 remained open/draft/unmerged with 282 changed paths and 127 review threads (44 resolved, 83 unresolved; 78 unresolved outdated, 5 unresolved current).
- The note itself is documentation-only. Refresh the branch head and workflow state before further work. No CI pass is claimed.


## 16. Latest code/test and review reconciliation — 2026-11-25

### 16.1 Exact patch snapshot and CI

- Code/test patch snapshot: `5284191f013ff5f9b29a35ff237d19ead7e51ad3`. The later handover/ledger updates are documentation-only; check the live branch head before relying on this SHA.
- CI run `45574340059` (run 2027) was queued for that exact patch snapshot, with 16 jobs: macos, macos-mlx, app, mac-ui, ios, security, atlas, kit, core 3.11/3.13, images, library 3.11/3.13, web and check 3.11/3.13. No conclusion is claimed while queued.
- The branch head after the latest handover update is expected to be newer than the code/test snapshot; a completed run on `5284191...` is not automatically evidence for a later docs-only head. Obtain an exact-head run before closure.

### 16.2 Code/test patches added; validation pending

| Finding | Patch present | Regression coverage | Status |
|---|---|---|---|
| ATLAS-EXACT-106 | `Number.exact_decimal` uses integer arithmetic based on denominator factors 2 and 5; no ambient Decimal-context division. | Positive, negative and >28-significant-digit terminating-decimal tests. | OPEN/PARTIAL until exact-head Core CI passes. |
| Reversible connector action compensation | Reversible actions require object-valued `previous`; otherwise `outcome_unknown`. Undo fails on missing credentials, malformed state or unconfirmed provider restoration. | Missing/malformed prior state and disconnect-before-undo. | Patch/test present; exact-head Core CI pending. Does not prove vendor semantics. |
| API 1.1 arbitrary object maps | Five open maps explicitly marked and described with route-specific authority/no-log semantics; exact allowlist asserted. Generated merged schema regenerated from delta. | New schema-boundary test checks exact map paths, authority and no-log descriptions; existing route tests cover owner/member policy. | Patch/test/schema present; exact-head contract CI pending. |
| OpenAPI path-count test | Name now says declared additive paths, not three. | Existing 32-path assertion retained. | Name corrected; exact-head contract CI pending. |
| Native Keychain fixture | Preflight/cleanup derives from `host.KEY_NAMES` plus model-record and designation anchor. | Existing native production-Core/Keychain test now checks full inventory before running and removes only its test inventory. | Patch present; hosted macOS CI pending. |

### 16.3 Review-thread disposition

- 127 total threads: 120 resolved, 7 unresolved (6 outdated anchors, 1 current anchor).
- Three unresolved sandbox findings remain release-blocking: the macOS profile is allow-by-default and not least privilege. Hosted tests prove selected network/write/private-root/process/Mach denials but do not establish a least-privilege profile or owner-Mac acceptance. Do not close these as fixed or claim local-only security acceptance.
- Four unresolved code/test threads correspond to the patches in §16.2. They remain open until exact-head CI and independent source/test re-review.
- The other 120 threads were replied to and resolved after current source/test inspection or specific documentation correction. Thread resolution does not equal Stage acceptance.

### 16.4 Current overall conformance judgement

**Documentation reconciliation:** substantial and active canonical contradictions corrected; not a certification of every historical archive. **Implementation conformance:** still INCOMPLETE. A full row-by-row trace of every PRD requirement, all registered use cases, every integration/screen and all 283 changed paths has not been completed. Stage 3 remains NOT ACCEPTED; Stage 4–8 remains unreviewed/unaccepted. Outstanding findings include ATLAS-CORE-092, ATLAS-CORE-083/084, ATLAS-SEC-016, ATLAS-ACT-019, ATLAS-CONN-025, egress residuals, currency semantics, app cancellation/undo UI, accessibility test reliability, remote-phone defects and owner-Mac/final-stage gates. See `DEFECT_REGISTER.md` and `STAGE3_ACCEPTANCE.md`.


## 17. App cancellation, undo and accessibility audit fixes — 2026-11-25

- `AppModel.ask()` now clears the previous task ID at submission start and uses `SubmissionCancellation` to retain Stop intent if the Core has not yet returned the new task ID. When the ID arrives, the queued Stop is applied to that task. `SubmissionCancellationTests` cover pre-ID cancellation, post-ID cancellation and reset between submissions. A full AppModel-level integration test is still desirable.
- `AppModel.undoLast()` now clears its undo handle only after Core explicitly returns `status=done`. Failed/transport outcomes preserve the handle and show a plain-language error in RecordsView. `UndoConfirmation` helper tests cover done/failed/missing status.
- The macOS accessibility UI test no longer uses darkest/lightest screenshot pixel extrema to exempt contrast findings. It waits for the expected first-run Welcome or Home prompt instead of sleeping a fixed eight seconds. Only narrowly identified system-owned title-bar/Touch Bar structural exceptions remain.
- These source/test changes are present at `67c7ee475db4188b0460a48807a8f0210c78a7d9`. Exact-head CI run `45576209883` is queued; no test pass is claimed. AppModel integration and owner visual/VoiceOver walkthrough remain open.
