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

