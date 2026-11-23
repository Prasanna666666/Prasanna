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