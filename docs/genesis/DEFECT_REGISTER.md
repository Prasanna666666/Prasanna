# Atlas Defect Register

**Status:** Active audit ledger; not a release-acceptance record.  
**Snapshot reviewed:** `44756ee23a06f79510b59fa94941bb2bce16dbb7` (2026-11-23 review snapshot). Revalidate every finding against the current PR head before implementation or closure.  
**Rule:** A change is not a fix until its regression test passes on the fixing commit and the reviewer independently inspects the changed path. Outdated GitHub threads are not presumed fixed.

## Status vocabulary

- **OPEN — REVALIDATE:** observed in the stated snapshot; current-head status must be checked.
- **FIXED — PENDING REVIEW:** author reports a fix; reviewer has not verified it.
- **VERIFIED FIXED:** exact fixing commit and regression test independently inspected.
- **ACCEPTED RISK:** owner-approved, narrowly documented residual risk with expiry/review trigger.
- **BLOCKED:** cannot be accepted until a named dependency/evidence gate is met.

## Newly inspected code findings

| ID | Severity | Category | Location / symbol | Finding and required evidence | First observed |
|---|---|---|---|---|---|
| ATLAS-SEC-014 | P1 | Egress / privacy | `core/src/atlas_core/egress.py` — `TaintSet.add(question=True)`, `leaks()` | Short, lower-case private identifiers in a task objective are not word-fingerprinted; question mode stores four-word shingles and capitalised-name fingerprints only. Add privacy-preserving lower-case identifier handling and regression tests for one-word and 2–3-word objectives, URL path/query, encoding and redirects. Keep live egress disabled until independently reviewed. | `44756ee` |
| ATLAS-ACT-015 | P1 | Automation / action safety | `core/src/atlas_core/browser.py` — `run_browser_workflow()`; `core/src/atlas_core/browser_engine.py` — `PlaywrightBrowser.press()` | Workflow calls `fill` and `press` directly; real `press` clicks a button by accessible name and can submit/send/buy/book/pay/delete/publish without Action Gateway approval, receipt or verification. The documented `act` step is not implemented. Disable side-effect-capable paths until typed, payload-bound gateway actions and adversarial submit tests exist. | `44756ee` |
| ATLAS-SEC-016 | P1 | Worker isolation | `core/src/atlas_core/browser_engine.py` — `WorkerBrowser`, `PlaywrightBrowser`; `browser_worker.py` | Browser worker is a separate same-user process, inherits `HOME` and `PYTHONPATH`, and relies on application-level Playwright routing/allow-lists rather than OS-enforced confinement of the full browser/driver process tree. Prove filesystem, process, secret and network restrictions with adversarial macOS tests; otherwise keep general browser automation unavailable. | `44756ee` |
| ATLAS-SEC-017 | P1 | Connector authorization | `core/src/atlas_core/connectors.py` — `ConnectorHub.link()`, `check()` | `link()` stores credentials and calls `allow_connector()` for `unreachable` as well as `ok`; later `check()` records `unauthorised`/`unreachable` health but does not revoke gateway authority. Only authenticated `ok` may enable actions; every failed re-check must revoke. Add tests proving action handlers are not called. | `44756ee` |
| ATLAS-OPS-018 | P2 | Process identity / lifecycle | `app/Sources/AtlasKit/CoreLauncher.swift` — `reapLeftovers()` | PID is treated as owned Core when `ps` command merely contains `atlas_core.serve`; identity is not revalidated before SIGKILL. Bind PID to process start identity and exact executable/data-dir/socket or authenticated instance token; test PID reuse, other Core instances and identity change between TERM/KILL. | `44756ee` |

## Historical findings F-01–F-13 — preserve and disposition individually

These findings were previously recorded in review history. They are **not asserted to remain unfixed**; each must be mapped to current code, an exact fix commit, regression test and independent disposition.

| ID | Historical finding | Required disposition |
|---|---|---|
| F-01 | Finance private-data leakage into model context | Revalidate domain isolation and every model/context/log/egress boundary. |
| F-02 | Ordinary/due dates shown without adequate verification/provenance | Revalidate evidence requirements, date semantics and UI disclosure. |
| F-03 | Floating-point money arithmetic | Verify decimal/minor-unit exactness throughout storage, API, calculations and rendering. |
| F-04 | Plaintext `.unencrypted` database artefact | Verify no plaintext artefacts, crash remnants, backups or temp files. |
| F-05 | Hardcoded/inconsistent limits | Inventory limits; centralise, document and test boundary behaviour. |
| F-06 | Medical extraction stops after 12 windows | Verify complete pagination/window coverage and honest partial states. |
| F-07 | Fragile keyword-list classification | Verify robust typed/domain classification and adversarial multilingual tests. |
| F-08 | Ruff/lint enforcement gaps | Verify CI enforcement, configuration and changed-file coverage. |
| F-09 | Non-atomic database migrations | Verify transactional migration, interruption recovery and rollback tests. |
| F-10 | 500 MB response cap | Verify bounded streaming, memory use, truncation/error semantics and large payload tests. |
| F-11 | Atlas egress/privacy boundary gaps | Revalidate taint, URL/redirect handling, DNS pinning, worker boundaries and live-egress gates. |
| F-12 | Inconsistent model settings and seed handling | Verify one authoritative configuration path, deterministic seeds and UI/API consistency. |
| F-13 | Prompt-injection exposure | Verify untrusted-content boundaries across documents, Mail, web, browser, connectors and agent outputs. |

## PR #8 review-thread register

At the audit snapshot, PR #8 had **58 inline review threads: 21 resolved, 37 unresolved**. The 37 unresolved threads are the canonical detailed per-file records; preserve their full comment history and link each to a stable ID in this register. Do not duplicate their content unnecessarily. Re-anchor outdated threads to current code and close only after independent verification.

Known finding clusters in those threads:
- Model worker sandbox permits owner-file reads / allow-by-default and Mach/process boundary concerns; self-sandbox bypass.
- Source-consent defaults and empty-selection onboarding; onboarding state incorrectly tied to current grants.
- Core child process shutdown/reaping, duplicate starts, socket ownership and stale-socket cleanup.
- Duplicate request submission while busy.
- Mail EMLX identity replacement race, malformed/truncated length, attachment-byte read and MIME read-ahead boundaries.
- Egress private-name / short-phrase fingerprint bypasses.
- Stage 3 evidence/acceptance contradictions, Finance/Health scope and missing final-stage evidence.
- Stage 3 public research egress scope and integration mismatch.

**Thread rule:** outdated ≠ fixed. A thread is closed only when its finding is mapped to a current fix commit, regression test and reviewer verification.

## Acceptance gates (not code defects)

Keep these separate from defects. The Stage 3 acceptance record explicitly leaves final-stage requirements open, including real-model injection behaviour, target-Mac sandbox and real-Internet egress exercise/owner decision, target-hardware model quality/performance thresholds, and human UI/accessibility/TCC/real-Mail/signing/notarisation/install walkthrough. Stage 4–8 report also labels itself a developer report that is not architect-reviewed or accepted. These are **BLOCKED/PENDING evidence gates**, not passed by hosted CI.

## Review and closure fields required for every ID

For every entry, append: affected requirement ID; current file/symbol and line range; reproduction; impact; proposed fix; regression test; first-seen SHA; current-head SHA; status; fixing SHA; CI run and exact result; reviewer verification; linked PR thread(s); owner risk decision if applicable.

**No silent deletion, no closure by assertion, no stage acceptance by percentage, and no merge/release inference from green CI.**

## Historical PR and design-review inventory

This section preserves earlier findings and review obligations. Older PR findings refer to the legacy application/branch and must not be silently treated as current Atlas Core defects; establish code lineage before carrying them forward.

### PR #6 — legacy engineering and UI review history

The PR #6 discussion contains 41 timeline comments. The durable historical source files at legacy snapshot `c92f5bf471d78695e539e5676973adda048095cc` are:
- `docs/reviews.md` (114 lines): review rounds 1–7 and author's findings.
- `docs/defects.md` (88 lines): D-series defect register.
- `docs/comment-tracker.md` (224 lines): review rounds, F1–F15, P-series UI findings and open/partial/blocker status.
- `docs/coverage-matrix.md` (574 lines): historical coverage inventory.
- `docs/requirements.md` (54 lines): legacy requirement baseline.

Preserve all historical IDs: **D-01 through D-45**, **O-01 through O-17**, **F1 through F15**, **P-1 through P-16**, **R1–R11**, **NEW-01/NEW-02**, and **C-1**. Their disposition varies across the timeline; author-reported FIXED is not independent verification. The legacy tracker explicitly recorded remaining items including:
- O-1: currency precision/import coverage for zero-, two- and three-decimal currencies (KWD/BHD third decimal); import/calculation tests still required.
- O-2: inventory/handling of old `.unencrypted` copies on real user data; cleanup must not destroy the only recoverable copy.
- O-4: large-response memory and streaming; 500 MB configured ceiling, no streaming, measured memory amplification and written input bounds.
- O-5: real ingestion/model performance and benchmark evidence.
- O-6: invoice/date/due-date role ambiguity requiring model/human evidence; do not silently assign date roles.
- O-7/O-8/O-9/O-10: workflow/undo, owner-rule exception, consent/prompt-injection and real-model verification items as described in the legacy tracker.
- O-12: older-release upgrade fixtures and actual user-database upgrade/rollback coverage.
- O-14: real reports/extraction completeness and range-end evidence.
- O-15: pre-upgrade copy/rollback gap for Images.
- O-16: sealed hand-over / key handling; author and owner-Mac evidence was partial and reviewer verification remained requested.
- O-17: date-source provenance not surfaced consistently in the UI.
- P-8: disconnected Photos retry/last-indexed experience remained open in the legacy tracker.
- P-12: mobile Ask overlap/card density remained partial.
- P-14: provenance on every fact remained partial.
- P-15: connected Photos evidence was blocked by the absent real drive.
- F1–F15 include finance dashboard baseline/empty states, freshness/reconciliation, Photos retry, calendar empty states, Overview density, visual treatment, mobile layout and provenance items; statuses vary and must be read from the tracker, not inferred from this abbreviated index.

PR #6 explicitly recorded that the earlier request to audit every 496/508 entries, every screenshot and every deployment path was **not completed** at that historical point. Do not represent the legacy audit as exhaustive. Use the original comment timeline and files above for full descriptions and status history.

### PR #7 — architecture and governance review

PR #7 has no inline review threads, but its conversation contains the architecture review and Stage 1 acceptance record. Important preserved outcomes:
- The initial Genesis docs received an **approve-with-changes** review; Finance raw-data isolation, hardware/benchmark evidence, storage/key recovery gates, thin vertical slice, untrusted content/action boundary and single roadmap were reconciled.
- The owner established the one-Atlas-app boundary, local-only inference, future native iOS/global access direction and explicit privacy/approval constraints.
- Stage 1 was formally accepted with stated evidence limitations; this was not acceptance of later stages.
- The owner accepted G-O17 and authorised Stage 2 on 2026-11-20, and waived the package-review gate. Stage 2 implementation acceptance remains separate.
- PR #7 is a documentation/decision record, not evidence that the entire legacy application migration or current implementation has passed a full audit.

Key timeline references include comments 7021286229, 7021348042, 7021610637, 7022008986, 7022436618, 7022456916, 7022637251, 7022810935, 7022990234, 7035425400, 7037200323, 7037299974 and 7037841488. PR #7 was closed at the owner's request so work could continue in the single shared PR #8; its history was retained.

### PR #9 — low-level design

PR #9 was closed at the owner's request and its design copied into `docs/genesis/LOW_LEVEL_DESIGN.md` (623 lines, blob SHA `04dc576c52ce3a45d8824c8d9f03e76187d376ac` at reviewed snapshot). The file itself says **architecture proposal — NOT implementation authorisation**. Its coverage includes product boundary, requirements traceability, trust zones, UI/navigation, modules, API contracts, data/encryption, connectors/ingestion, memory/retrieval, model runtime, agent workflows/approvals, threat model, benchmarks, tests, packaging, iOS and implementation readiness.

PR #9 has no inline review threads and no review submission in the fetched review history; its only timeline comment says it was closed at the owner's request. Therefore the 623-line LLD has **not been independently accepted as a complete design** by that PR history. Review every section against the PRD, target architecture, current code and ADRs; resolve contradictions before treating it as authoritative implementation specification.

### PR #10 — Stage 3 preparation package

PR #10 has no inline review threads or review submission in the fetched history. Its timeline contains the request to challenge the exact Stage 3 baseline audit, contract delta, execution plan, PRD, target architecture, Internet/network policy and relevant source/contracts/tests (comment 7050900372). The PR was closed at the owner's request; no completed independent challenge response was present in the retrieved timeline. Treat the Stage 3 preparation package as **not independently accepted** until its factual and contract traceability review is completed on exact SHAs.

## Additional documentation/traceability issue found in the reviewed snapshot

| ID | Severity | Category | Location | Finding / required correction | First observed |
|---|---|---|---|---|---|
| ATLAS-DOC-019 | P2 | Evidence integrity / documentation | `core/docs/STAGE3_ACCEPTANCE.md` opening evidence-class definition and criterion 11 | The opening legend defines L as Linux CI and M as target Mac/real model, but criterion 11 later cites **R (hosted macOS runner)** without defining R in the evidence-class legend. Reconcile the evidence taxonomy and every row so Linux CI, hosted macOS runner, owner-Mac and human walkthrough are distinct. Also reconcile the criterion-11 statement that egress is not wired into the answer flow with PR description wording that calls it wired: the inspected code has a separate `TaskService.research()` API operation and tests explicitly state research results do not change the task answer. Describe the actual capability precisely; do not call a separate untrusted research result an integrated answer-flow feature. | `44756ee` |



## UI/UX requirements audit — implementation gaps recorded in the map

The canonical specification is `docs/genesis/UI_UX_SPECIFICATION.md` (421 lines; specification commit `379e730` / original `ef8ea18`). It explicitly separates documentation completion from implementation, architect review and owner visual acceptance. The implementation map `core/docs/UI_IMPLEMENTATION_MAP.md` (25 lines) says no screen has been seen running by a person, screenshotted or checked with VoiceOver. The following are map-reported implementation gaps at snapshot `44756ee`; independently re-check source and exact current head before closure.

| ID | Severity | Category | Location / requirement | Gap and required evidence | First observed |
|---|---|---|---|---|---|
| ATLAS-UX-021 | P2 | Conversation UX | UI spec §4.2; `UI_IMPLEMENTATION_MAP.md` Ask Atlas row | No conversation list/history across restarts, despite the spec requiring accessible conversation history. Implement durable conversation history/navigation or explicitly record a scope change; test restart persistence and selection. | `44756ee` |
| ATLAS-UX-022 | P1 | Action UX / reachability | UI spec §4.8; map Approval row | Approval sheet is implemented but no app workflow proposes an action, so an owner cannot reach or exercise the approval flow. Wire a safe typed proposal path and test exact payload, approval, expiry, cancellation and receipt end-to-end; no unmediated side effects. | `44756ee` |
| ATLAS-UX-023 | P2 | Activity durability | UI spec §4.7; map Activity row | Activity is in memory and lost on restart. Persist the required activity/task outcomes or state the accepted retention boundary; test restart and deduplication. | `44756ee` |
| ATLAS-UX-024 | P2 | Notification controls | UI spec §4.7; map Activity row | Only one notification switch; category/quiet-behaviour controls specified for Settings are absent. Implement or explicitly defer with truthful UI and acceptance mapping. | `44756ee` |
| ATLAS-UX-025 | P2 | Evidence navigation | UI spec §4.4; map Evidence row | “Open in source” is not offered because Core has no such action. Define and implement safe source-opening capability with stale/revoked-source checks, or revise the spec with owner approval. | `44756ee` |
| ATLAS-UX-026 | P2 | Shared components | UI spec §5; map Components row | Global search field, toast and inline help beyond basic `.help` are missing. Implement reusable components and verify keyboard, focus, loading and error states, or mark them explicitly deferred. | `44756ee` |
| ATLAS-UX-027 | P1 | Accessibility | UI spec §7; map Accessibility row | Only automated contrast tests are recorded; VoiceOver, keyboard, Dynamic Type and Reduce Motion walkthrough on a real running Mac remain pending. This is a release/owner acceptance gate, not passed by unit tests. | `44756ee` |
| ATLAS-UX-028 | P1 | Visual acceptance gate | UI spec §§12–13; map Screenshots row | No real-app screenshots, human visual review or owner visual acceptance. Capture documented window sizes in light/dark, key states and failure/empty states; architect review and explicit owner acceptance remain required. | `44756ee` |
| ATLAS-UX-029 | P2 | Settings / operations | UI spec §4.9; map Settings row | No in-app backup control; backup/restore exists only via CLI maintenance commands. Verify the exact spec requirement and either provide the intended Settings flow or document an owner-approved deferral with a usable, safe alternative. | `44756ee` |

### Low-level design conflict

| ID | Severity | Category | Location | Finding / required correction | First observed |
|---|---|---|---|---|---|
| ATLAS-DES-020 | P2 | Requirements/design consistency | `docs/genesis/LOW_LEVEL_DESIGN.md` §11.5 versus `docs/genesis/PRD.md` §4.4 and UI spec §4.8 | LLD Tier 2 says calendar changes and file deletion require explicit per-action approval without the PRD's distinctions. The PRD's closed list requires approval for external communication, spending/purchases/paid bookings, deletion/overwrite only when reliable undo is unavailable or destructive migration, and unlocking physical access/safety systems; ordinary calendar changes and reversible local deletion do not prompt. Align the LLD to the owner-approved closed list and add a policy matrix/test trace. | `44756ee` |

### Design-review gate

The 623-line LLD and 421-line UI/UX specification are present and have clear review/acceptance gates. Their presence is not acceptance. PR #9 has no review submission in the fetched history; the UI spec itself marks implementation, architect review and owner visual acceptance NOT COMPLETE. The architect must review the design against the PRD/target architecture and current code; owner-only visual/accessibility gates remain separate. Do not mark any of these as complete from the document alone.


## PR #8 — complete unresolved inline-thread index (retrieved 2026-11-23)

All **37 currently unresolved** threads are indexed below. This is a pointer/index only; the complete finding, reproduction and requested correction remain in the original GitHub thread. Outdated threads are still open until current-head verification; do not close them solely because their diff anchor is outdated.

| Thread ID | Path | Original/current line | Anchor state | Finding summary |
|---|---|---:|---|---|
| `PRRT_kwDOBqaHsM66l7B7` | `core/src/atlas_core/sandbox.py` | 33 | Outdated — re-anchor | **Blocking privacy boundary.** `(allow default)` plus network/write denials leaves all file reads, process execution and Mach lookups allowed. The worker can read arbitrary user-re |
| `PRRT_kwDOBqaHsM66l7B-` | `app/Sources/AtlasApp/AtlasApp.swift` | 165 | Outdated — re-anchor | **Blocking consent defect.** Both source toggles default to `true`, so the owner is presented with Documents and Mail already selected. This is opt-out rather than the required def |
| `PRRT_kwDOBqaHsM66l7CA` | `app/Sources/AtlasApp/AtlasApp.swift` | 221 | Current anchor | **Blocking lifecycle defect.** This starts a child Core, but no app-termination handler calls `Launcher.shared.stop()` (and `CoreLauncher.stop()` itself only sends terminate withou |
| `PRRT_kwDOBqaHsM66l7eP` | `core/src/atlas_core/macos.py` | 336 | Outdated — re-anchor | **P1 — Attachment bytes are read by the EMLX adapter.** This reads the entire `.emlx` file, including raw MIME attachment octets, into memory; `message_from_bytes()` then parses th |
| `PRRT_kwDOBqaHsM66l7eQ` | `core/src/atlas_core/macos.py` | 346 | Outdated — re-anchor | **P2 — Malformed/truncated EMLX length is not rejected safely.** `isdigit()` accepts an arbitrarily long digit string; `int()` can raise `ValueError` for values beyond Python's dig |
| `PRRT_kwDOBqaHsM66l7eV` | `app/Sources/AtlasKit/CoreLauncher.swift` | 55 | Outdated — re-anchor | **P1 — Core child lifecycle is not tied to the app lifecycle.** The app starts this child from `ConversationModel.init()` but no app-termination hook calls `Launcher.shared.stop()` |
| `PRRT_kwDOBqaHsM66l7eY` | `app/Sources/AtlasApp/AtlasApp.swift` | 121 | Outdated — re-anchor | **P2 — Onboarding state is incorrectly derived from active grants.** Withdrawing the final grant makes this expression return to Get Started. The view then defaults both sources to |
| `PRRT_kwDOBqaHsM66l7ea` | `core/docs/STAGE3_ACCEPTANCE.md` | 17 | Outdated — re-anchor | **P2 — Acceptance evidence is stale and contradicts the new macOS CI evidence.** This row says real MLX, the macOS sandbox profile and macOS network tests have never run, while the |
| `PRRT_kwDOBqaHsM66l7ec` | `core/docs/MACOS_PROVIDERS.md` | 3 | Outdated — re-anchor | **P2 — This sentence is factually inconsistent with the native test evidence.** The paragraph says nothing reads a real Keychain in CI, but `tests/test_macos_native.py` exercises t |
| `PRRT_kwDOBqaHsM66l7ed` | `core/docs/STAGE3_HANDOVER.md` | 5 | Outdated — re-anchor | **P2 — Handover evidence classification is obsolete.** “All synthetic-data, Linux-verified” is no longer accurate: the exact head has macOS CI evidence for the real Keychain, Swift |
| `PRRT_kwDOBqaHsM66l9zY` | `core/src/atlas_core/worker.py` | 105 | Outdated — re-anchor | **P1 — The worker can opt out of its own security boundary.** `--skip-self-sandbox` is caller-controlled; direct invocation with this flag skips `install_network_deny()` and still  |
| `PRRT_kwDOBqaHsM66l9zZ` | `core/src/atlas_core/sandbox.py` | 33 | Outdated — re-anchor | **P1 — The macOS profile does not yet establish the stated local-only guarantee.** This is allow-by-default and denies `network*`/writes, but leaves Mach lookups and process execut |
| `PRRT_kwDOBqaHsM66l9za` | `app/Sources/AtlasApp/AtlasApp.swift` | 165 | Outdated — re-anchor | **P1 — First-run consent is preselected rather than default-deny.** Both Documents and Mail start enabled. A user who simply presses Continue without making a source choice grants  |
| `PRRT_kwDOBqaHsM66l9zc` | `app/Sources/AtlasApp/AtlasApp.swift` | 175 | Outdated — re-anchor | **P1 — The owner cannot complete Get Started with no sources selected.** Disabling Continue when both toggles are false contradicts the explicit requirement that choosing nothing e |
| `PRRT_kwDOBqaHsM66l9zd` | `app/Sources/AtlasApp/AtlasApp.swift` | 134 | Outdated — re-anchor | **P1 — Guard duplicate submissions in the model, not only the button.** The TextField's `onSubmit` remains active while `busy`; `ask()` itself does not reject a second call. Pressi |
| `PRRT_kwDOBqaHsM66l9ze` | `app/Sources/AtlasKit/CoreLauncher.swift` | 55 | Outdated — re-anchor | **P1 — `stop()` is never wired to application termination.** Atlas starts Core as a child, but the app has no termination hook that calls this method. Core's `_work` loop therefore |
| `PRRT_kwDOBqaHsM66l9zg` | `core/src/atlas_core/transport.py` | 183 | Outdated — re-anchor | **P1 — Do not unlink a socket without proving no live Core owns it.** Because the app currently leaves its child Core running on quit, the next launch can reach this branch, unlink |
| `PRRT_kwDOBqaHsM66l9zj` | `core/docs/STAGE3_ACCEPTANCE.md` | 11 | Outdated — re-anchor | **P1 — Criterion 5 is explicitly PARTIAL and conflicts with G-021.** The canonical Stage 3 plan calls for synthetic tests of owner-authorised Finance/Health access to the local mod |
| `PRRT_kwDOBqaHsM66l9zm` | `docs/genesis/STAGE-3-EXECUTION-PLAN.md` | 37 | Current anchor | **P1 — An in-scope Stage 3 capability is missing.** This plan explicitly includes public Internet research through a Core egress gateway with synthetic privacy/injection tests. The |
| `PRRT_kwDOBqaHsM66l9zo` | `core/docs/STAGE3_ACCEPTANCE.md` | 33 | Outdated — re-anchor | **P1 — The evidence record contradicts itself.** The macOS-runner evidence above says real Keychain, real sandboxed MLX and the production Core were exercised; this consolidated li |
| `PRRT_kwDOBqaHsM66l-vn` | `core/src/atlas_core/macos.py` | 496 | Current anchor | **P1 — Regular-file replacement race remains after the symlink fix.** `_scan()` opens the candidate, derives its identity, closes the descriptor, and caches only `parts`. This late |
| `PRRT_kwDOBqaHsM66l-vp` | `core/src/atlas_core/macos.py` | 336 | Outdated — re-anchor | **P1 — The adapter reads attachment octets despite the stated never-read boundary.** `handle.read(MAX_EMLX_BYTES + 1)` materialises the entire `.emlx` payload, including MIME attac |
| `PRRT_kwDOBqaHsM66l-vs` | `core/src/atlas_core/macos.py` | 346 | Outdated — re-anchor | **P2 — Malformed/truncated EMLX length can escape as an exception or be accepted partially.** `line.strip().isdigit()` is followed by an unbounded `int(...)`; a sufficiently long d |
| `PRRT_kwDOBqaHsM66l-vw` | `core/src/atlas_core/sandbox.py` | 33 | Outdated — re-anchor | **P1 — The worker still has unrestricted read access to the owner's files.** `(allow default)` denies network and writes but leaves file reads and process execution open. The worke |
| `PRRT_kwDOBqaHsM66nKrK` | `core/src/atlas_core/macos.py` | 272 | Outdated — re-anchor | P1: This 4 KiB fill can cross the next MIME delimiter and consume bytes from the following attachment before the scanner notices the delimiter in the buffer. A short text body foll |
| `PRRT_kwDOBqaHsM66nKrP` | `core/docs/STAGE3_ACCEPTANCE.md` | 12 | Outdated — re-anchor | Criterion 6 cannot be MET-L while this row admits that the literal 'never read' requirement is not met and says an owner decision is still needed. Keep it unresolved/not accepted u |
| `PRRT_kwDOBqaHsM66nKrS` | `core/docs/STAGE3_ACCEPTANCE.md` | 19 | Outdated — re-anchor | Please reconcile this row with the new exact-head `app` CI job: run 45058722203 builds and launches Atlas.app and checks Core startup/shutdown. The app has now been launched in hos |
| `PRRT_kwDOBqaHsM66nK8s` | `core/src/atlas_core/macos.py` | 272 | Outdated — re-anchor | P1: This 4 KiB fill can cross the next MIME delimiter and consume bytes from the following attachment before the scanner notices the delimiter in the buffer. A short text body foll |
| `PRRT_kwDOBqaHsM66nK8v` | `core/docs/STAGE3_ACCEPTANCE.md` | 12 | Outdated — re-anchor | Criterion 6 cannot be MET-L while this row admits that the literal 'never read' requirement is not met and says an owner decision is still needed. Keep it unresolved/not accepted u |
| `PRRT_kwDOBqaHsM66nK8y` | `core/docs/STAGE3_ACCEPTANCE.md` | 19 | Outdated — re-anchor | Please reconcile this row with the new exact-head `app` CI job: run 45058722203 builds and launches Atlas.app and checks Core startup/shutdown. The app has now been launched in hos |
| `PRRT_kwDOBqaHsM66nLgG` | `core/src/atlas_core/egress.py` | 201 | Current anchor | P1 before this gateway is wired into answer flow: the taint set does not fingerprint ordinary private names or short private phrases. `_candidates()` includes tokens of 8+ characte |
| `PRRT_kwDOBqaHsM66nZ_v` | `core/src/atlas_core/egress.py` | 202 | Current anchor | P1: Candidate tokens of 8+ characters are only fingerprinted if they contain a digit or `@`. A private one-word name such as `Alexandra` is therefore not stored as an identifier; a |
| `PRRT_kwDOBqaHsM66nZ_y` | `core/docs/STAGE3_ACCEPTANCE.md` | 7 | Outdated — re-anchor | P2 documentation contradiction: this says the Get Started screen has never been launched, but criterion 13 now correctly says the app was built/launched in hosted CI and Core lifec |
| `PRRT_kwDOBqaHsM66nZ_0` | `core/docs/STAGE3_ACCEPTANCE.md` | 17 | Outdated — re-anchor | Criterion 11 remains PARTIAL and release-blocking under the canonical plan. In addition to the documented allow-by-default sandbox, no owner-Mac/model verification and unconnected  |
| `PRRT_kwDOBqaHsM66nZ_3` | `core/docs/STAGE3_ACCEPTANCE.md` | 18 | Outdated — re-anchor | Criterion 12 remains PARTIAL: no target-Mac real-model latency, memory, quality or thermal results and no accepted pass thresholds. Hosted CI or the developer-container ingestion n |
| `PRRT_kwDOBqaHsM66nZ_6` | `core/docs/STAGE3_ACCEPTANCE.md` | 19 | Outdated — re-anchor | Criterion 13 remains PENDING-M. Hosted CI packaging/launch/Core lifecycle is valuable, but it does not demonstrate a human owner walkthrough, accessibility, real TCC prompts, real  |
| `PRRT_kwDOBqaHsM66oTDU` | `app/Sources/AtlasKit/CoreLauncher.swift` | 98 | Current anchor | **P1 — Do not unlink a socket unless it has been proven stale.** This executes even when the PID file is absent/invalid or the process identity check fails. A still-live Core can t |



## Current-head revalidation and design findings

**Revalidation target:** PR #8 head observed during this review: `d9dcb0b2f87ec6904165ac238ff4fff66154a0b9`. The exact-head CI run `45259305300` was **QUEUED** when checked; therefore the fixes below are source/test-inspected but not yet exact-head CI-verified. A new register commit will itself move the head and require a fresh CI run.

### UI/UX and LLD gaps

| ID | Severity | Category | Current status | Location / requirement / required disposition |
|---|---|---|---|---|
| ATLAS-UX-021 | P1 | Action safety / UX | OPEN | `core/docs/UI_IMPLEMENTATION_MAP.md`: approval sheet exists but no app flow proposes an action, so an owner cannot reach it. Wire only typed, payload-bound Action Gateway proposals and demonstrate preview, approval, expiry, execution receipt and verification end-to-end. No generic browser side effects. |
| ATLAS-UX-022 | P2 | Conversation durability | OPEN | UI spec §4.2 requires accessible conversation history; implementation map says there is no conversation list/history across restarts. Add durable conversation/session state or explicitly defer with owner approval and correct UI claims. |
| ATLAS-UX-023 | P2 | Activity durability | OPEN | UI spec §4.7 expects activity/outcomes; implementation map says activity is in memory and lost on restart. Persist the required activity history or narrow the documented promise. |
| ATLAS-UX-024 | P2 | Notification controls | OPEN | UI spec §4.7/§4.9 requires notification categories and quiet behaviour; current Settings has one switch only. Implement controls or explicitly defer and keep unsupported controls absent. |
| ATLAS-UX-025 | P2 | Evidence navigation | OPEN | UI spec §4.4 requires source inspection; implementation map says “open in source” is unavailable because Core has no such action. Add a safe, permission-rechecked source-opening contract or explicitly defer. |
| ATLAS-UX-026 | P2 | Shared UI components | OPEN | UI spec §3/§5 calls for global search/command entry, toast and inline help; implementation map records missing global search/command field, toast and inline help. Reconcile spec and implementation; do not imply available UI. |
| ATLAS-UX-027 | P1 | Accessibility | BLOCKED — OWNER WALKTHROUGH | UI spec §7/§12 requires keyboard, VoiceOver, Dynamic Type and Reduce Motion. Unit/contrast tests are not a manual real-app accessibility audit. Complete a real Mac walkthrough and record evidence. |
| ATLAS-UX-028 | P1 | Visual acceptance | BLOCKED — OWNER + ARCHITECT | UI spec §12/§13 requires real running app review, screenshots and explicit owner visual acceptance. No person has run through the UI; CI launch is not visual acceptance. |
| ATLAS-UX-029 | P2 | Backup UX | OPEN / SCOPE DECISION | UI spec §4.9 expects understandable backup/restore controls; current backup/verify/restore exists only through CLI maintenance. Either implement safe in-app controls or document an owner-approved deferral. |
| ATLAS-DES-020 | P2 | Design-policy contradiction | OPEN | `docs/genesis/LOW_LEVEL_DESIGN.md` §11.5 Tier 2 requires approval for calendar changes and file deletion more broadly than owner-approved PRD §4.4. Reconcile to the closed approval list: external communication, spending/purchases/paid bookings, deletion/overwrite only without reliable undo or destructive migration, and physical-access/safety unlocking. Add a policy matrix traceable to tests. |
| ATLAS-DOC-019 | P2 | Evidence taxonomy / claim precision | OPEN — RECONCILE | `core/docs/STAGE3_ACCEPTANCE.md`: legend must define L, M and hosted macOS runner class R consistently. Distinguish separate `TaskService.research()`/API research operation from an answer-flow integrated tool: tests state the research result is untrusted and does not change the task answer. Align PR body, acceptance matrix and implementation. |

### Stage 3 acceptance gates that remain open

The current acceptance document itself records:
- Criterion 4: real-model prompt-injection resistance is deferred and not met.
- Criterion 11: macOS sandbox is allow-by-default, not least privilege; owner model/Mac verification and real-Internet egress exercise remain outstanding; public search remains disabled pending owner decision.
- Criterion 12: target-Mac/real-model latency, memory, thermal and quality results against accepted thresholds do not exist.
- Criterion 13: hosted CI app build/launch is evidenced, but no human UI walkthrough, real TCC prompts, real Mail store, Developer ID signing/notarisation or self-contained Python/model install; app is not owner-tryable.
- Mail attachment parsing is deliberately not built; messages with a non-text first part remain unreadable under the strict no-attachment-byte-read rule.

### Stage 4–8 review boundary

`core/docs/STAGES_4_TO_8.md` explicitly says the work is not architect-reviewed or accepted, and lists outstanding architecture review, owner decisions G-O02/G-O05/G-O14 and deferred-final owner hardware/account evidence. It also says browser worker is not OS-confined and web reading is OFF in production; automation orchestrator/browser workflows/watchers are not yet wired to Core routes. Do not equate tests of libraries/fakes with complete agentic workflows.



## Historical cross-chat reconciliation — findings recovered from prior Atlas audits

**Source snapshots:** the following findings were explicitly reported in earlier Atlas audit conversations on 2026-11-23 against historical head `fb3f775120bc95676dc5c5cd49bb6395a04cc3eb` (morning audit), plus architecture/discovery reviews on 2026-11-19 and follow-up reviews later on 2026-11-23. They were absent as individually identified entries in this register at the time of reconciliation. They are recorded now as **HISTORICAL — REVALIDATE**, not as claims that they still reproduce at the present head. The original prior audit noted that tests had not reproduced these findings; therefore none is labelled test-confirmed or verified fixed.

### A-series findings from the 2026-11-23 earlier code audit

| ID | Severity | Historical location / subsystem | Historical finding | Required revalidation / regression evidence |
|---|---|---|---|---|
| ATLAS-HIST-030 (A-01) | P1 | Action Gateway / persistence / undo | Action receipts, approvals, undo records and idempotency state were in-memory rather than durably persisted. A restart could lose the audit trail and recovery/undo state. | Trace proposal → approval → execution → receipt → undo across forced termination/restart; prove durable, tamper-evident records and idempotency after restart. |
| ATLAS-HIST-031 (A-02) | P1 | Action replay / nonce cache | Restart replay protection depended on an in-memory nonce cache; restart could reset replay history and permit replay of a previously accepted request. | Persist replay/idempotency state atomically; test duplicate/replayed requests before and after restart, concurrent requests and crash between commit/execution. |
| ATLAS-HIST-032 (A-03) | P1 | Production updater / health reporting | Production updater supplied an always-healthy callback, so update readiness/health could be reported without checking actual required conditions. | Trace production wiring (not only unit fakes); make health derived from real checks and fail closed; test unavailable, stale, corrupt and partially applied update states. |
| ATLAS-HIST-033 (A-04) | P1 | Native-source ingestion / index integrity | Native-provider failure could erase already indexed records rather than preserve last-known-good data and expose a source error. | Inject provider permission, timeout, malformed response and transient failures; prove no destructive replacement on failed/partial sync and explicit stale/error state. |
| ATLAS-HIST-034 (A-05) | P1 | Finance data correctness | Finance currency and date handling had correctness defects (including currency precision/date semantics); the earlier audit did not claim tests reproduced them. | Verify ISO-4217 zero-, two- and three-decimal currencies, exact decimal/minor-unit arithmetic, locale parsing, transaction/invoice/due-date role and timezone boundaries. |
| ATLAS-HIST-035 (A-06) | P2 | Records API / pagination | Records API truncated results at 500 records without a complete pagination/continuation contract. | Test >500 records, stable pagination under concurrent updates, explicit truncation/continuation metadata and UI completeness. |
| ATLAS-HIST-036 (A-07) | P1 | iPhone Ask / source scope | iPhone Ask hardcoded Documents and Mail rather than deriving its source scope from the owner's actual authorised grants and platform capabilities. | Verify source grants are explicit, default-deny and platform-independent; test Photos/Calendar/Contacts/Files/Mail scopes, revoke/regrant and empty-source onboarding. |
| ATLAS-HIST-037 (A-08) | P1 | iPhone erasure / offline persistence | iPhone erasure and offline persistence paths suppressed errors, making failed deletion or failed queue persistence appear successful. | Inject filesystem/database/network failures; prove errors surface, deletion is verifiable and recoverable, offline queue is durable and user-visible; test restart and retry. |

### Additional historical code findings reported in the same audit window

| ID | Severity | Subsystem | Historical finding | Required revalidation / regression evidence |
|---|---|---|---|---|
| ATLAS-HIST-038 | P1 | Mail ingestion identity | Mail message with no Message-ID used a path-identity fallback vulnerable to file replacement/path swap; a replacement could be confused with the originally scanned message. | Verify file identity (device/inode/size/mtime or stable content identity) across scan and parse; replace file between stages and prove no stale identity is accepted. |
| ATLAS-HIST-039 | P1 | iOS source scope / erasure | A separate follow-up explicitly elevated iPhone source-scope and erasure behaviour as P1; preserve as a cross-check on A-07/A-08 rather than silently deduplicating. | Link this cross-check to ATLAS-HIST-036/037 and document whether the later code path is the same or distinct. |
| ATLAS-HIST-040 | P1 | Egress boundary | Earlier audit required re-verification of outbound privacy/egress boundary, including whether private context could be disclosed through research/search requests. | Re-run the complete egress threat suite: names, lower-case identifiers, short phrases, URLs/query/path, encoding, redirects, DNS/host changes, prompt injection and error paths. Cross-link ATLAS-SEC-014 and F-11. |
| ATLAS-HIST-041 | P1 | Core lifecycle / socket ownership | Earlier audit required verification of Core lifecycle and socket protections, including duplicate starts, stale/live socket cleanup and owner process identity. | Cross-link PR #8 unresolved lifecycle threads; test concurrent launch, crash, PID reuse, live socket with missing PID, shutdown/relaunch and multiple data directories. |
| ATLAS-HIST-042 | P1 | Stage 3 evidence / Mail privacy | Acceptance documentation needed reconciliation across egress status, attachment-byte-read boundary, macOS CI evidence and owner-machine gates. | Cross-link ATLAS-DOC-019 and Stage 3 gates below; reconcile exact source behaviour, test evidence and owner acceptance. |

### Historical product/architecture and delivery gaps recovered from 2026-11-19 and 2026-11-23 reviews

These are requirements/acceptance gaps rather than necessarily implementation bugs. Preserve them as individual audit obligations so they cannot disappear inside broad statements such as “platform incomplete.”

| ID | Severity | Category | Historical gap / risk | Required evidence or disposition |
|---|---|---|---|---|
| ATLAS-HIST-043 | P1 | Finance privacy boundary | Finance raw/private records must not leak into general model context, prompts, logs, telemetry, retrieval or outbound research. Earlier architecture review called this a critical privacy boundary. | Prove domain-separated retrieval/context construction and deny-by-default cross-domain access; adversarial canary tests across every model and egress path. Cross-link F-01. |
| ATLAS-HIST-044 | P1 | Health privacy boundary | Health records require the same explicit, purpose-limited isolation and authorised context path; Stage 3 scope and implementation were previously inconsistent. | Trace consent, retrieval, model invocation, logs, exports and deletion; test unauthorised cross-domain access and revoke. |
| ATLAS-HIST-045 | P1 | Storage encryption / recovery | Storage, encryption-at-rest, backup/restore and key-recovery design were identified as critical risks; plaintext remnants and recoverability after key loss must be handled deliberately. | Threat model and verify key lifecycle, encrypted DB/WAL/temp/backup, restore, key rotation/recovery, crash remnants and safe migration with real fixtures. Cross-link F-04 and O-02/O-15/O-16. |
| ATLAS-HIST-046 | P1 | Performance / hardware acceptance | Performance targets were unproven; target-device latency, memory, thermal behaviour, model quality and benchmark thresholds were not supported by owner-hardware evidence. | Define measurable acceptance thresholds, benchmark representative workloads on target Mac with actual local models; record raw results, thermal/memory profiles and repeatability. Cross-link Stage 3 criterion 12. |
| ATLAS-HIST-047 | P1 | Scope / architecture integrity | First-release scope was considered excessive; reuse-before-redesign and unclear one-app/one-process boundaries risked coupling and incomplete delivery. | Reconcile PRD, ADRs, target architecture and LLD; establish explicit release boundary, module ownership, process boundaries and deferred features; architect sign-off. |
| ATLAS-HIST-048 | P1 | Agentic workflow integration | General agents, browser automation, macOS automation, watchers, connectors and research host wiring were incomplete or only library/fake-tested; this is not proof of production end-to-end capability. | For every workflow, trace trigger → planner → policy → approval → executor → receipt → recovery; demonstrate real app routes, permissions, retries, cancellation and audit. Cross-link ATLAS-ACT-015, ATLAS-SEC-016 and Stage 4–8 boundary. |
| ATLAS-HIST-049 | P2 | Finance/Health migration and ingestion | Finance/Health migration and ingestion remained incomplete in the earlier implementation review. | Inventory each supported provider/source, incremental sync, deletion/revocation, pagination, malformed data and migration/rollback; publish a coverage matrix. |
| ATLAS-HIST-050 | P2 | Connectors | Connector breadth and lifecycle were incomplete; a connector's UI presence or stored credentials did not prove usable, authorised operation. | Per-connector contract and end-to-end tests for link, auth refresh, revoke, offline, expiry, scope changes and action denial. Cross-link ATLAS-SEC-017. |
| ATLAS-HIST-051 | P2 | Backup / export workflow | Backup UI/export workflow was incomplete; CLI-only maintenance is not equivalent to user-facing backup/restore. | Cross-link ATLAS-UX-029; verify backup integrity, restore, export, encryption, retention and owner-facing status/error paths. |
| ATLAS-HIST-052 | P2 | Device acceptance | iOS/iPhone and cross-device validation remained incomplete despite platform-specific scope and erasure paths. | Real-device build, permission/TCC flows, offline/restart, sync, deletion, accessibility and privacy walkthrough; record device/OS/build evidence. |
| ATLAS-HIST-053 | P2 | Conversation/activity/search | Earlier review identified missing persistent conversation/activity history and global search/command entry. | Cross-link ATLAS-UX-022, ATLAS-UX-023 and ATLAS-UX-026; prove persistence, search semantics, privacy scoping and deletion. |
| ATLAS-HIST-054 | P1 | Approval reachability | Approval UI existed but no production workflow proposed actions; the approval control was therefore unreachable in a real user journey. | Cross-link ATLAS-UX-021 and ATLAS-ACT-015; end-to-end action proposal and approval test. |
| ATLAS-HIST-055 | P1 | Stage acceptance | Stages 3–8 and acceptance gates F-4/F-11/F-12/F-13 were previously described as outstanding/unaccepted; a green subset of CI must not be treated as stage acceptance. | Maintain per-stage criteria, exact evidence SHAs, owner decisions, architect review and explicit acceptance record. |
| ATLAS-HIST-056 | P2 | Native automation / watchers | Native macOS automation and watchers were not fully wired into production routes; a component or test fake is not an integrated capability. | Trace launch, permissions, event delivery, backpressure, deduplication, stop/restart, error recovery and user-visible status end-to-end. |
| ATLAS-HIST-057 | P1 | Local AI privacy / model runtime | Local-only inference is a product constraint; ensure no silent cloud fallback, remote telemetry leakage or external model invocation when local runtime is unavailable. | Instrument and adversarially test every inference path under offline conditions; fail closed and disclose model availability. |
| ATLAS-HIST-058 | P2 | Memory governance | Persistent memory requires source traceability, domain/sensitivity isolation, explicit controls, deletion/expiry and correction semantics. | Test provenance, access scopes, correction, deletion propagation, expiry and recovery across indexes, caches, backups and model context. |

### Cross-chat reconciliation disposition

- These 29 entries (ATLAS-HIST-030 through ATLAS-HIST-058) are now preserved as separate historical audit records. Some deliberately cross-reference existing F-series or ATLAS entries; cross-links are not a reason to delete the historical record.
- No historical item is marked VERIFIED FIXED. The source conversations report earlier observations and, for A-01–A-08, explicitly note that tests had not reproduced the defects.
- The morning audit's exact code snapshot `fb3f775120bc95676dc5c5cd49bb6395a04cc3eb` differs from the later PR #8 audit snapshot. Verify ancestry and current code before carrying line numbers or claiming present reproduction.
- This reconciliation uses the prior Atlas audit conversations surfaced for this request. It does **not** establish that every message ever exchanged has been exhaustively searched; continue reconciliation as additional historical records are recovered.


## Further historical reconciliation — PR #6 review and coverage records

The 29 entries above were **not** the complete historical inventory. A further retrieval of the original PR #6 files at legacy snapshot `c92f5bf471d78695e539e5676973adda048095cc` surfaced the following omitted records and important scope corrections.

| ID | Severity | Category | Historical finding / status | Required disposition |
|---|---|---|---|---|
| ATLAS-HIST-059 (NEW-03) | P1 | Real-model safety verification | PR #6 historical audit explicitly recorded real-AI/real-model behaviour as unverified. Code-level prompt-injection and confirmation tests were not proof that a real model could not be steered into unsafe tool use. | Preserve as an independent acceptance gate; run adversarial tests with the actual supported local model(s), record model/version, prompts, tool traces and results. Cross-link F-13, O-10 and ATLAS-HIST-048/057. |
| ATLAS-HIST-060 (NEW-04) | P2 | Visual/screenshot verification | PR #6 historical audit explicitly recorded screenshot verification as incomplete. Generated screenshots were not all individually opened and inspected; the coverage matrix identified only 15 screenshot files as ROUND + VIEWED at the 541-entry snapshot. | Inventory every required screen/state/theme/viewport; distinguish generated from individually inspected images; record reviewer, exact image/build SHA and visual findings. Cross-link current ATLAS-UX-028. |
| ATLAS-HIST-061 | P1 | Historical audit completeness | PR #6's earlier coverage record counted 499 baseline / 502 changed files, with only 96 inspected and 403 not inspected. A later authoritative legacy coverage matrix counted 541 changed entries (D 100, A 364, M 5, R 72): 105 ROUND, 15 ROUND + VIEWED, 397 NOT INSPECTED and 24 AUTHORED. The matrix explicitly states this is not exhaustive inspection. | Keep this as a historical audit limitation, not a present Atlas file count. Do not claim PR #6 was comprehensively reviewed. Reconcile legacy file lineage before applying findings to the current Atlas repository. |
| ATLAS-HIST-062 | P2 | Review-comment traceability | PR #6 had a larger review-comment history than the abbreviated defect-ID inventory: Review 1 (R1-1–R1-13), Gemini Review 2 (R2-1–R2-5), Gemini R3-1–R3-11, author R4, ChatGPT R5, ChatGPT R6-1–R6-4 (called R3-1..R3-4 in source text), R7, R8, and R9 (product/screenshot/functionality review, not yet posted in the historical tracker). The tracker maps these to D/O/UI findings and includes rebutted or conditional points, not all confirmed defects. | Preserve the review rounds and their original dispositions; retrieve and map every source comment individually. Do not convert refuted, conditional, roadmap or unverified claims into confirmed defects. The full historical source is `docs/comment-tracker.md` at the cited legacy snapshot. |

### PR #6 inventory precision and outstanding historical distinctions

- The source files preserve **D-01–D-45**, **O-01–O-17**, **F1–F15**, **P-1–P-16**, **R1–R11**, **NEW-01–NEW-04** and **C-1**. The current register's abbreviated inventory names many of these ranges but does not yet reproduce every row, source comment, status transition and proof level individually.
- The historical comment tracker defines proof levels P0–P5 and requires independent reviewer reproduction (P4) before closure; owner-Mac/real-model evidence (P5) is separately required where flagged. An author-reported fix or passing author-run tests alone did not satisfy closure.
- Historical R1 findings included: local model endpoint; float money; plaintext after encryption; invoice/due-date ambiguity; medical extraction truncation; migration atomicity; library limits; CI failures; prompt injection/tool permissions; model configuration; large upstream responses; benchmarks; and regression tests including Mac/Docker. Several were closed, several partial, and some required Mac/model evidence.
- Historical O-series items included currency precision, plaintext remnants on real user data, large-response streaming/memory, real ingestion/model performance, date-role ambiguity, workflow/undo, owner-rule exceptions, consent/prompt-injection, real-model verification, older-release migration/rollback, report/extraction completeness, announced truncation, pre-upgrade Images copy, sealed handover/key handling and date-source provenance. Their statuses varied; the legacy tracker must be used for exact status.
- The original `docs/defects.md` and `docs/comment-tracker.md` contain the detailed D/O rows and review mapping. The original `docs/coverage-matrix.md` contains the 541-entry file-by-file coverage status. These source documents are the authority for legacy details; this new register is an index and does not replace their full history.
- The historical legacy coverage matrix's 541 entries are **not** the current Atlas 266-file audit scope. They are a separate legacy branch/change-set count and must never be merged into or substituted for the current repository's file inventory.


## Third historical recovery — PR #6 open issues and unverified deployment/security gates

Source: original `docs/defects.md`, `docs/security-deployment-review.md`, `docs/ui-review.md`, `docs/testing.md`, `docs/design.md` and `docs/reconciliation.md` at legacy snapshot `c92f5bf471d78695e539e5676973adda048095cc`. These are individually recorded because the prior short inventory did not preserve the actual open/partial status. The original source files remain authoritative for historical dispositions.

### O-series: unresolved or conditional items

| ID | Severity | Category | Historical state and exact gap | Required evidence / disposition |
|---|---|---|---|---|
| ATLAS-HIST-063 (O-1) | P2 | Finance currency support | Storage in hundredths does not support currencies requiring three decimal places (KWD/BHD etc.). Typed amounts needing a third decimal are refused; statement imports with non-zero third decimal are held back and cannot be proven. JPY zero-decimal is exact. | Decide whether supported account currencies require per-currency exponents; test statement ingestion and exact reconciliation. Preserve as a documented product limitation until resolved. |
| ATLAS-HIST-064 (O-4) | P2 | Memory / large responses | Historical 66 MB JSON response peaked at 329 MB (~5× response size); default limit was reduced from 500 MB to 100 MB, but streaming/bounded parsing was not implemented. | Benchmark realistic and adversarial payloads on target hardware; test bounded memory, cancellation and explicit oversize response. |
| ATLAS-HIST-065 (O-5) | P1 | Real-device performance / OCR / model quality | Reading speed, OCR accuracy and 3B local-model sorting quality had not been measured on owner's actual library/Mac; Finance categorisation had no corrections dataset for measurement. | Record owner-Mac workload, model/version, corpus size, OCR error rates, throughput, categorisation quality and memory/thermal results. |
| ATLAS-HIST-066 (O-6) | P2 | Document date semantics | Code cannot reliably distinguish invoice date, issue date, due date and payment date without semantic evidence; source line makes it reviewable but does not resolve role ambiguity. | Preserve unknown/ambiguous roles, display source evidence, test multi-date invoices and never infer a date role from proximity alone. |
| ATLAS-HIST-067 (O-7) | P2 | Undo / recovery | Routine additions had a journal and undo path, but a whole statement import had no single atomic undo; its payments had to be deleted individually. Real-model flow had not been run. | Design and test transaction-level import rollback/undo with durable audit trail; test partial import, restart and real model. |
| ATLAS-HIST-068 (O-8) | P2 | Consent language governance | English and Dutch yes/delete/undo word lists lived in code, conflicting with the no-hardcoding rule and limiting language extensibility. | Move policy vocabulary to versioned data/configuration with locale tests; retain strict whole-message confirmation semantics. |
| ATLAS-HIST-069 (O-9) | P2 | UI review completeness | UI review recorded a set of screenshot findings; some were fixed, some partly fixed, some intentional by design. The floating Ask-button fix had no scrolled phone screenshot verification. | Reconcile every UI-A through UI-L item to current implementation and screenshot evidence; keep intentional design decisions explicitly accepted. |
| ATLAS-HIST-070 (O-10) | P1 | Real-model prompt injection | Real-model resistance to malicious documents/tool-output prompt injection was explicitly not demonstrated; code-level tests and fake model tests were not equivalent to real-model red teaming. | Run a documented adversarial corpus on each supported local model; capture prompts, model version, tool calls, approvals and outcomes. |
| ATLAS-HIST-071 (O-12) | P1 | Upgrade / rollback | Upgrade tests used historical text dumps; Finance and Documents snapshots were development commits, not releases. Owner's actual older databases and rollback after a failed upgrade were not covered. | Obtain anonymised real-version fixtures, test every supported upgrade path, interrupted migration, backup restore and rollback. |
| ATLAS-HIST-072 (O-14) | P1 | Health extraction correctness | A model could return the upper/lower endpoint of a printed reference range as the measured result; substring presence was insufficient to prove the value was the result. | Parse test/result/reference-range structure; test boundary values, units, multiple rows and ambiguous layouts; preserve uncertain values as requiring review. |
| ATLAS-HIST-073 (O-16) | P1 | Plaintext hand-over / Docker | Sealed X25519 + ChaCha20-Poly1305 hand-over existed but was OFF by default and not built/run in Docker. Until enabled and verified, whole-text JSON hand-over remained plaintext in a shared Docker volume (mode 0600, deleted after ingestion). | Build and run both images on target Mac; prove volume contains only sealed files, key isolation, failure retention, ingestion and deletion behaviour. |
| ATLAS-HIST-074 (O-7 follow-up) | P2 | Routine write undo verification | The journal/undo path had not been exercised with the real model; the statement-import undo gap remained separate. | Cross-link HIST-067; do not treat fake-model/unit tests as end-to-end acceptance. |

### Security, deployment and operational gaps explicitly listed as not inspected or not run

| ID | Severity | Category | Historical gap | Required evidence |
|---|---|---|---|---|
| ATLAS-HIST-075 | P1 | Authentication / signed-call lifecycle | Token generation, expiry and reuse in `kit/sign.py` and Atlas token fetch were not inspected end-to-end. | Trace token minting, scope, expiry, rotation, replay and revocation across app boundaries; test tampering and clock skew. |
| ATLAS-HIST-076 | P1 | Web request security | CSRF and Origin/Host checks beyond Atlas tests, request-size limits and malformed JSON handling across every endpoint were not inspected. | Endpoint inventory plus adversarial tests for CSRF, Host/Origin spoofing, oversized bodies, malformed/deep JSON and error disclosure. |
| ATLAS-HIST-077 | P1 | Filesystem boundary | Path traversal, symlink handling and file-serving paths were not fully inspected beyond existing tests. | Threat-model every read/write/delete/serve path; test symlink swaps, traversal, hard links, TOCTOU and permission boundaries. |
| ATLAS-HIST-078 | P1 | Supply-chain / container security | Docker images and dependencies were not scanned as built images; pip-audit in CI did not substitute for image/OS package scanning. Finance and Atlas Dockerfiles were not read in the historical review. | Scan final images, OS packages, Python dependencies and SBOM; inspect every Dockerfile and pin/rebuild policy. |
| ATLAS-HIST-079 | P1 | Database key lifecycle | Database key creation, Keychain storage and rotation were only partly read; key recovery/rotation remained a critical architecture risk. | Prove key generation, Keychain ACLs, rotation, backup compatibility, loss recovery and no key leakage in env/log/process arguments. Cross-link HIST-045. |
| ATLAS-HIST-080 | P1 | Backup and restore | Backup/restore scripts were not inspected or run. | Test encrypted backups, integrity verification, restore to clean machine, interrupted backup, retention, key loss and disaster recovery. |
| ATLAS-HIST-081 | P1 | macOS integration security | Apple Mail integration and Apple Vision sandbox behaviour were not verified on target Mac. | Real macOS permission/TCC tests, least privilege, denied/revoked access, sandbox and file-scope verification. |
| ATLAS-HIST-082 | P1 | Local model configuration | Ollama configuration and host/network boundary were not fully verified on target Mac. | Verify bind address, firewall, authentication assumptions, no public endpoint, model download/update and offline operation. |
| ATLAS-HIST-083 | P1 | Operational failure recovery | Disk-full, Docker-unavailable, missing-model and interrupted-startup behaviour had no tests. | Fault-injection for each condition; prove fail-closed behaviour, no corruption/orphans, clear recovery instructions and safe retry. |
| ATLAS-HIST-084 | P1 | Installer / updater deployment | `up.sh`, `down.sh` and autostart install/removal were not run; the existing up.sh test was a weak source-string check. First install, repeat install, upgrade and rollback of Docker deployment were untested. | Execute full lifecycle on clean macOS machine and recover from interrupted install/update; verify autostart removal and no destructive branch/data changes. |
| ATLAS-HIST-085 | P2 | Container volume at-rest protection | Named Docker volume lived inside Docker Desktop's disk image; the historical review noted FileVault was the only at-rest protection. | Document and test host-disk encryption assumptions, backup/export handling and residual data on uninstall. |
| ATLAS-HIST-086 | P2 | Security verification coverage | Historical security review was static or fake-tested in several areas; no claim of end-to-end Mac/Docker verification was justified. | Map every security control to static review, unit test, integration test, real deployment test and owner acceptance separately. |

### Additional historical UI observations retained as traceability obligations

These were documented as UI-A through UI-L in `docs/ui-review.md`; some were later fixed or intentionally accepted. Do not reopen as current defects without checking current UI, but preserve their evidence trail.

- UI-A: Travel hero gradient and Finance sparkline fade conflicted with the one-accent/no-gradient rule.
- UI-B: Health values used decimal commas while chart axes used decimal points.
- UI-C: pluralisation error (“1 reports”) and misleading “0 medicines”.
- UI-D: floating Ask button covered content on phone; the 120 px padding fix was not visually checked with a scrolled phone screenshot.
- UI-E: “142% monthly vs before” lacked a clear comparison period.
- UI-F: empty “Due in 3 weeks €0 / 0 payments” cards consumed dashboard space.
- UI-G: six status pills plus Update wrapped on narrow widths.
- UI-H: standalone app stubs/empty Finance shell could confuse first-run users; later accepted by design with Open Atlas link.
- UI-I: Photos showed green connected status while no photo drive was connected.
- UI-J: pending changes were presented as typed “yes” note, inconsistent with Photos' Confirm button; later Yes/No controls added.
- UI-K: empty calendar month used large blank grid and pushed “Coming up” below fold.
- UI-L: empty first-run Finance dashboard did not make the first step sufficiently obvious; later checklist added.

### Register completeness warning

The historical source register contains D-01–D-45 with detailed descriptions, evidence, fixes and tests; O-1–O-17 with explicit open/resolved/partial states; the review tracker includes rejected/conditional claims as well as confirmed findings. The earlier Genesis register only indexed these ID ranges and did not reproduce their individual records. This omission is now explicitly acknowledged. The original legacy files at `c92f5bf471d78695e539e5676973adda048095cc` must remain linked as primary historical evidence. Do not treat the legacy statuses as current Atlas status or assume fixes carried over to the present repository.


## HIST-087 — Complete source-history archive and reconciliation obligation (2026-11-23)

**Status: ARCHIVED — ITEM-BY-ITEM RECONCILIATION STILL OPEN.** The previous register was not a complete record of the GitHub history. Full source material has now been preserved on this branch in the following files:

- `docs/genesis/HISTORICAL_PR6_SOURCE_ARCHIVE.md` — verbatim legacy PR #6 `docs/defects.md`, `docs/comment-tracker.md`, `docs/reviews.md`, `docs/coverage-matrix.md`, and `docs/requirements.md` from snapshot `c92f5bf471d78695e539e5676973adda048095cc` (5 files; 1,054+ source lines; 112,770 characters).
- `docs/genesis/HISTORICAL_PR6_CONVERSATION.md` — all 41 PR #6 conversation comments (119,327 characters).
- `docs/genesis/HISTORICAL_PR7_CONVERSATION.md` — all 64 PR #7 conversation comments (223,374 characters), including architecture review, owner decisions, collaboration protocol, delivery planning, hardware/model/runtime decisions, privacy and recovery constraints.
- `docs/genesis/HISTORICAL_PR8_CONVERSATION.md` — all 192 PR #8 conversation comments (662,256 characters), including successive developer status claims, review responses, owner instructions and acceptance decisions.
- `docs/genesis/HISTORICAL_PR8_REVIEW_THREADS.md` — all 53 submitted PR #8 reviews and all 58 inline threads / 63 inline comments (233,209 characters), with path, line, resolved/outdated metadata and full comment text.
- `docs/genesis/HISTORICAL_PR9_CONVERSATION.md` — the PR #9 closure record.
- `docs/genesis/HISTORICAL_PR10_CONVERSATION.md` — the Stage 3 independent challenge handoff and closure record.

### Retrieval counts and important correction

- PR #6: 41 top-level conversation comments; no inline review threads returned by the GitHub thread endpoint.
- PR #7: 64 top-level conversation comments; no inline review threads returned by the GitHub thread endpoint.
- PR #8: 192 top-level conversation comments (refreshed after the audit handoff comments), 53 submitted reviews, 58 inline threads, and 63 inline comments. At fetch time 21 threads were resolved and 37 unresolved. Earlier register entries indexed the 37 unresolved threads, but the 21 resolved threads and complete review/comment bodies were not all represented there.
- PR #9: 1 conversation comment. PR #10: 1 conversation comment. No inline threads/reviews returned for either.
- The 541-entry legacy coverage matrix belongs to the PR #6 historical snapshot. It must not be presented as the current Atlas 266-file inventory.

### Mandatory reconciliation work

1. Parse every legacy D-01–D-45 and O-series entry, each R1–R9 / Gemini review item, every comment-tracker P/R/NEW/C entry, and all UI-A–UI-L items into stable canonical IDs. Preserve original IDs and exact historical disposition.
2. Reconcile every PR #8 review submission and all 58 inline threads against current HEAD. Do not equate resolved/outdated with verified fixed; preserve the fix claim, exact fixing SHA, test evidence, and independent verification status separately.
3. Reconcile PR #7 architecture review findings and all owner decisions, including single-app boundary, Finance/Health isolation, no cloud inference, MLX and ~27B benchmark direction, task-based model switching, platform/Core-language decision boundaries, backup/key recovery, scope, performance evidence, approval/undo/audit, migration and owner acceptance constraints.
4. Cross-reference PR #9 LLD challenge and PR #10 Stage 3 preparation challenge, including every design contradiction, missing acceptance gate and unverified owner-Mac/real-model condition.
5. Produce a traceability table: source record → canonical ID → affected requirement/design/API/code path → first-seen commit → current-head status → fix commit → regression test → independent review → owner acceptance if required.
6. Keep historical records even when superseded or fixed. Mark duplicate/related items as cross-links; never delete or silently merge away their history.

**Scope limitation:** This archive is exhaustive for the fetched GitHub PR discussion/review endpoints and the five named PR #6 source documents. It is not proof that every conversation across every ChatGPT/Claude session has been recovered, nor that all code files have been reviewed. Continue searching available prior context and repository branches/commits for additional sources.


## HIST-088 — Prior-conversation owner instructions and product decisions recovered (2026-11-23)

**Status: RECOVERED SUMMARY — FULL HISTORICAL CHAT COVERAGE NOT PROVEN.** A focused prior-conversation retrieval surfaced additional owner instructions and product/design decisions not fully represented by the PR archives. They are recorded in `docs/genesis/PRIOR_CONVERSATION_RECOVERY.md`.

Important records include:
- Collaboration contract: user is project manager; ChatGPT is planner/architect/integrator/reviewer; Claude is developer/tester/debugger/maintainer; exchanges should be PR-based and auditable.
- Explicit no-code constraint on 2026-11-19: documentation/architecture/reviews only; Claude owns coding/testing/debugging/maintenance.
- One Atlas app; consolidation/migration/retirement are developer actions; no destructive cleanup before architecture review/approval.
- Product direction: unified, local-first personal AI/chief-of-staff; macOS first, cross-platform-ready; Atlas Core plus specialist agents; broad life-domain coverage.
- High autonomy remains bounded by approval, permissions, auditability and recovery.
- UI direction from 2026-11-22: immersive, premium, futuristic, expressive, never cluttered; user rejected boring/crowded direction and required Documents/design cleanup.
- Historical architecture risks: Finance/Health privacy isolation, backup/restore and key recovery, target-hardware performance evidence, excessive first-release scope, reuse of consent/undo/audit/ingestion, local model runtime verification, connector and automation workflow safety.
- Proposed latency targets and other assistant-authored proposals are not owner-approved acceptance criteria unless confirmed in PR history.

**Limit:** Personal-context retrieval returned selected prior records, not a complete transcript export. Do not claim all historical ChatGPT conversations have been recovered. Continue reconciliation against PR #6–#10 archives, current Genesis documents, repository branches/commits and any additional available prior context. Preserve source/date and distinguish owner decisions from assistant proposals and Claude claims.


## HIST-089 — Complete repository PR inventory and current-scope correction (2026-11-23)

**Status: INVENTORY RECOVERED — ITEM-BY-ITEM AUDIT STILL OPEN.**

A repository-wide PR search found **10 pull requests**, not only Atlas/Genesis PRs #6–#10:

- PRs #1–#5 are Dependabot workflow-update PRs (setup-python, gitleaks-action, checkout, upload-artifact, setup-node). All five are closed and unmerged; each changes only `.github/workflows/ci.yml`. Their comments and dispositions are preserved in `docs/genesis/DEPENDABOT_PR1-5_ARCHIVE.md`. They are CI/supply-chain maintenance history and must be checked against the current workflow, but are not automatically Atlas feature defects.
- PRs #6–#10 are the Atlas/Genesis audit, architecture, foundation, LLD and Stage 3 preparation records archived in the existing files listed under HIST-087.

**PR #8 current discussion counts (rechecked 2026-11-23):** 192 top-level issue comments, 53 submitted reviews, 58 inline review threads, and 63 inline comments. Of the 58 inline threads, 21 are resolved and 37 unresolved at the time of capture. The archive files `HISTORICAL_PR8_CONVERSATION.md` and `HISTORICAL_PR8_REVIEW_THREADS.md` contain these sources; archive IDs were checked against the current 192 top-level comments and all 192 were present. Do not add 53 reviews to the issue-comment count or confuse the 63 inline comments with thread count.

**Current PR #8 changed-file inventory: 275 paths** returned by GitHub's paginated changed-filename endpoint. This supersedes the earlier informal 266-file figure for the current PR snapshot. The 541-entry legacy coverage matrix is still the distinct historical PR #6 inventory. These are three different counts and must not be conflated:
1. PR #6 legacy coverage matrix: 541 entries.
2. Previously referenced current review scope: 266 files (historical count, exact snapshot must be identified).
3. Current PR #8 changed-file list: 275 paths (rechecked 2026-11-23; includes newly added documentation/archive paths).

Claude must establish the exact base/head SHA for each inventory and classify all 275 paths. Separate application source, tests, docs, generated/source archives, build/workflow/configuration, and assets. Preserve the original 266-scope list if it exists; do not silently replace it with 275 or assume the nine-path delta is only documentation without a path-level diff.

**PR inventory limitation:** the search endpoint returned PRs #1–#10; this is the complete returned result set for this repository at capture time, not proof that no branches, tags, commits, discussions, Actions runs, security alerts, or other repository artifacts contain additional evidence. Continue inspecting those sources.


## HIST-090 — Consolidated reviewer history and current coverage baseline (2026-11-23)

**Status:** OPEN — audit coverage not yet established.

The live PR #8 API at head `4269f6340af1d5c75ca132cab33500fd130db945` reports 276 changed paths, 53 review submissions (48 non-empty, five empty), 58 inline threads (21 resolved, 37 unresolved), 63 inline comments, and 43 outdated threads. All review submissions and inline comments are attributed to the repository owner's GitHub login; some developer replies carry Claude Code attribution. Do not describe these as 53 independent reviewers. Historical prior-chat context records Claude's review of nine Genesis documents and parts of Atlas, followed by a reported Stage 0/Stage 1 documentation acceptance. Those bounded approvals do not accept the current full implementation audit.

The 37 unresolved threads affect: `app/Sources/AtlasApp/AtlasApp.swift` (6), `core/src/atlas_core/macos.py` (7), `core/src/atlas_core/sandbox.py` (3), `app/Sources/AtlasKit/CoreLauncher.swift` (3), `core/docs/STAGE3_ACCEPTANCE.md` (11), `core/docs/MACOS_PROVIDERS.md` (1), `core/docs/STAGE3_HANDOVER.md` (1), `core/src/atlas_core/worker.py` (1), `core/src/atlas_core/transport.py` (1), `docs/genesis/STAGE-3-EXECUTION-PLAN.md` (1), and `core/src/atlas_core/egress.py` (2).

The 276-path inventory is not proof of review. The earlier 266 figure refers to a historical scope whose exact snapshot still needs path-level reconciliation. The 541-entry PR #6 legacy matrix is a separate inventory. See `REVIEW_COVERAGE_RECONCILIATION.md` for the detailed reviewer-role history, per-path unresolved-thread breakdown, remaining work and coverage statement. No exhaustive 276-file line-by-line review is claimed.


## HIST-090 — Repository branch inventory exposes unreviewed divergent work (2026-11-23)

**Status: BRANCH INVENTORY CAPTURED — FULL HISTORY AND DIFF REVIEW OPEN.** The repository has 12 branches at capture, including legacy Aperture/Orbit/Atlas, WIP Health, Genesis review branches, Stage 2, Stage 3 prep and Stage 4–6. Full branch heads, comparisons, audit leads and Claude actions are in `docs/genesis/BRANCH_HISTORY_RECONCILIATION.md`.

**Critical discrepancy:** PR #8's actual head is `genesis-stage2-foundation` at `4269f6340af1d5c75ca132cab33500fd130db945`; `genesis-stage4-6` is a separate divergent branch. Compare at capture: Stage 4–6 is 8 commits ahead / 82 behind the PR #8 branch, with 61 changed paths. It contains substantive new application/Core modules and tests for backup, storage, migration, Finance/Health records, action gateway, orchestration, browser automation, device sync, updater/signing and LaunchAgent. PR #8 body nevertheless says Stages 4–8 are on its branch. This branch/PR description inconsistency must be resolved explicitly; no silent merge or acceptance.

Other comparisons show separate Stage 3 prep and LLD branches with unique commits/docs. The legacy Aperture/Orbit/WIP branches contain additional design and audit signals (local-only/cloud gating, ingestion and indexing, Health freshness, undo/consent, exact-money handling, encryption migration, answer truncation, UI regressions, performance and deployment assumptions). These must be reconciled with existing historical records; commit subjects are leads, not proof of current behaviour.

**History limitation:** branch inventory is complete for the 12 branches returned by the endpoint at capture, but commit pagination is not yet complete for all branches. Several branches return 100+ commit pages. Do not claim all branch history has been recovered until pagination is exhausted and unique commits are reconciled.
