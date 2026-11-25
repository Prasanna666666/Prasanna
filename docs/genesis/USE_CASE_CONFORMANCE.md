# Atlas use-case conformance matrix

**Snapshot:** 2026-11-25. **Code/test evidence snapshot:** 35d41c800046ca3042991134f66bece7611191cc (latest implementation/contract/UI-test/backup/sandbox-comment patch); exact-snapshot CI run 45577911258 is queued; no test pass is claimed yet.

**Purpose:** reconcile every scenario in USE_CASE_REGISTER.md against implementation evidence and limitations. This is a first-pass, source/document-based matrix, not owner acceptance or proof that every test passed. “Implemented” means the named testable scope exists; “partial” means material requirements remain; “not implemented” means no adequate current implementation path was found; “deferred” means the canonical register explicitly places it later or outside scope.

## 1. Product-wide use cases UC-001–UC-016

| ID | Status | Current evidence | Material gap / acceptance boundary |
|---|---|---|---|
| UC-001 Cross-domain question | PARTIAL | policy.py, gate.py, intelligence.py; domain grant isolation in test_policy.py and test_domains.py | A focused end-to-end cross-domain reconciliation path is not demonstrated; only permitted-domain policy and selected workflows are covered. |
| UC-002 Insufficient evidence | PARTIAL | answer.py, coverage.py, reference client; test_evals.py, test_client.py | Core/reference-client truthful states exist; full SwiftUI visual states and every unsupported-source case need owner walkthrough. |
| UC-003 Current fact | PARTIAL / DISABLED | egress.py, api.py separate API 1.1 research operation; EGRESS_GATEWAY.md | Research is off by default, separate from ordinary answer generation, not connected to answer evidence, not exercised on real Internet; residual taint/DNS/truncation/URL findings remain. |
| UC-004 Broad goal → plan/execute | PARTIAL | orchestrator.py, actions.py, /v1/review; test_orchestrator.py | Only a fixed review workflow and stub-agent orchestration are demonstrated; no general plan/delegate/execute workflow through the everyday Ask path. |
| UC-005 What changed? | PARTIAL | versioned record edits, source hashes, task/activity events | No general cross-domain change-detection/summary experience with durable baseline and provenance. |
| UC-006 Correct remembered fact | NOT IMPLEMENTED | MEMORY_PRIVACY_KNOWLEDGE.md is specification | No dedicated governed-memory store, correction history or cross-session application found in Core source. |
| UC-007 Why Atlas believes it | PARTIAL | evidence.py, citation inspector, GET /v1/tasks/{id}/citations/{index} | Cited passage can be inspected; richer source location/version and reasoning summary are not consistently available across source types. |
| UC-008 Continue prior task | PARTIAL | durable task/checkpoint recovery in tasks.py, service.py; restart/fault tests | Swift conversation history is not persisted across restarts; durable task state is not equivalent to a user-facing conversation history/resume UX. |
| UC-009 Interrupt/cancel | PARTIAL | Core task cancellation and SubmissionGate; lifecycle tests | AppModel now clears the previous ID and queues Stop requests made before the new ID returns; helper regression tests are present, but exact-head CI and an AppModel-level integration test remain pending (ATLAS-APP-052). |
| UC-010 Conflicting sources | PARTIAL | record version conflict checks and citation/provenance | No general conflict resolver that ranks source authority/recency across unrelated domains. |
| UC-011 Revoked/unavailable source | PARTIAL | designation.py, access.py, purge/revalidation tests | Task path is covered; separate Finance/Health summary, Library Search and citation passage reads still have the ATLAS-CORE-092 post-read revocation race. |
| UC-012 Long background task | PARTIAL | task state machine, progress events, cancellation and Swift Lifecycle | No supportable ETA; no persistent conversation history; app cancellation issue remains. |
| UC-013 Voice/quick capture | PARTIAL | on-device speech dictation and read-aloud (Voice.swift, Speech.swift, Aloud.swift) | Dictation/read-aloud are not a continuous voice conversation; recogniser and accessibility require owner-device validation. |
| UC-014 Scheduled briefing | NOT IMPLEMENTED / PARTIAL FOUNDATION | watchers.py, review.py, notifications | No scheduled daily briefing service with source cadence, deduplication and owner controls; watcher library is not generally wired into Core routes. |
| UC-015 Change then undo | PARTIAL | actions.py, record_actions.py, ActionGateway; reversible record edits and connector fix patch | Action receipts/undo state are in-memory across restart (ATLAS-ACT-019); app now preserves the undo handle and shows an error unless Core confirms `done` (helper test present, exact-head CI pending; ATLAS-APP-053); connector fix awaits CI and vendor validation. |
| UC-016 Honest completion/failure | PARTIAL | closed error/coverage vocabularies, reference client, UX catalogue | Core contract is stronger than app presentation; visual validation and every edge-state rendering remain incomplete. |

## 2. Domain and capability use cases UC-017–UC-030

| ID | Status | Current evidence | Material gap / acceptance boundary |
|---|---|---|---|
| UC-017 Finance understanding | PARTIAL | records.py, finance_calc.py, migration.py, Finance store and summary; deterministic exact calculations | Only legacy transactions import; no portfolio/holdings reconciliation, tax, loan, budget, statement reconciliation or anomaly analysis. Currency precision is limited to supported two-decimal values; no universal currency semantics. |
| UC-018 Health understanding | NOT IMPLEMENTED as ingestion / PARTIAL summary | health_calc.py, encrypted Health store, GET /v1/health/summary | No Health importer, HealthKit/native Health adapter or real owner-data ingestion; empty store/summary is not a working Health source. |
| UC-019 Home and energy | NOT IMPLEMENTED | Generic connector framework and home UI capability surfaces | No verified smart-home vendor adapter, meter integration, device-level energy source, heating schedule engine or measured usage pipeline. |
| UC-020 Travel planning | NOT IMPLEMENTED as planning | Travel record domain and API | No integrated route/lodging/entry-rule/cost research or booking-preview workflow. |
| UC-021 Work/projects | NOT IMPLEMENTED as integrated capability | Generic tasks/actions and review workflow | No connected project/work sources, dependency tracking or durable project-management space. |
| UC-022 Research/learning | PARTIAL / DISABLED | Separate public research API, egress gateway, provenance/untrusted result | Not integrated into normal answer evidence; real Internet off; no learning-plan or source-comparison experience. |
| UC-023 Shopping/ownership | NOT IMPLEMENTED | No purchase comparison/ownership workflow identified | No product comparison, warranty/repair/resale tracking or return-window capability. |
| UC-024 Family/social | NOT IMPLEMENTED | No dedicated capability found | No owner-approved family/social commitments or message preparation workflow. |
| UC-025 Legal/government | NOT IMPLEMENTED | No dedicated capability found | No official correspondence/deadline/renewal workflow. |
| UC-026 Photos/personal archive | PARTIAL FOUNDATION | macos_sources.py PhotoKit adapter and hosted framework tests | No complete media indexing/search/description/grouping and user-facing photo archive experience evidenced. |
| UC-027 Digital security/account hygiene | PARTIAL | enrolled clients, devices, connectors, consent and revocation | No full connected-app scope inventory, permission-change monitoring or account hygiene workflow; remote-phone security remains blocked. |
| UC-028 Governed memory | NOT IMPLEMENTED | PRD and MEMORY_PRIVACY_KNOWLEDGE.md specification only | No memory record store, provenance/confidence/correction/expiry/deletion implementation found. |
| UC-029 Proactive daily briefing | PARTIAL FOUNDATION | review.py, watchers.py, notification model; overlapping-calendar attention list | No scheduled briefing across messages, deadlines, weather and travel; no source watcher route; notifications not verified on owner Mac. |
| UC-030 Cross-app workflow automation | PARTIAL FOUNDATION | actions.py, orchestrator.py, connectors, browser workflow library | Orchestrator/browser/watchers are not generally wired to Core routes; browser is read-only and production web engine is off; native macOS app automation is not built; durable Action Gateway recovery is open. |

## 3. Additional use cases UC-031–UC-055

| ID | Status | Current evidence | Material gap / acceptance boundary |
|---|---|---|---|
| UC-031 Conversation history | PARTIAL | in-memory Swift turns and Core durable tasks | No conversation list/search/pin/archive/delete or restart-persistent chat history. |
| UC-032 Capability discovery | PARTIAL | fixed connector catalogue and app destinations | No comprehensive capability registry that truthfully distinguishes available, connected, gated and future capabilities across all domains. |
| UC-033 Mac-to-iPhone handoff | PARTIAL / BLOCKED | iOS client, pairing, relay, sync and Core API; PhoneTests.swift | Open relay/iOS/device findings, cache repopulation after Unpair, no real VPN/network exercise and no owner-phone walkthrough. |
| UC-034 Accessibility | PARTIAL / UNVERIFIED | labels, hints, system fonts, contrast and UI automation tests | No owner VoiceOver/keyboard/Dynamic Type walkthrough; the unsafe screenshot-extrema contrast exemption was removed and the test now waits for a stable expected first-run/Home screen (ATLAS-TEST-054/055 patch present, exact-head CI pending). |
| UC-035 Bulk operation preview | NOT IMPLEMENTED | Action Gateway supports individual typed actions | No batch rename/organise preview, affected count or bulk undo flow. |
| UC-036 Ambient context | NOT IMPLEMENTED | No continuous capture path identified | Explicit “summarise what I am looking at” flow and capture/redaction controls absent. |
| UC-037 Location/arrival trigger | NOT IMPLEMENTED | No location trigger engine identified | No owner-configured location trigger or permission/battery controls. |
| UC-038 External-source watcher | PARTIAL FOUNDATION | watchers.py and notification policy | No general production watcher scheduler/API with visible cadence/budget and disconnect lifecycle. |
| UC-039 Folder-arrival watcher | NOT IMPLEMENTED | Documents indexing exists | No incremental file-event watcher with restart/replay evidence. |
| UC-040 Replace the Mac | PARTIAL | integrity-checked backup/verify/drill/restore CLI and new-store restoration tests | No owner-Mac recovery drill, accepted backup destination/retention policy or complete identity/device/connector recovery. See BRANCH_ROLLBACK_AND_RECOVERY.md. |
| UC-041 macOS permission reset | PARTIAL | permission reset/purge code and synthetic tests | Real TCC prompt/permission-reset behaviour and owner-Mac verification remain untested. |
| UC-042 Model/quantisation update | PARTIAL | signed manifest loading, updater and model registry | No complete frozen quality/safety/latency/resource regression gate for every model/quantisation change on target hardware. |
| UC-043 Apple ID/iCloud change | NOT IMPLEMENTED | no account identity change detector found | No explicit account-change detection or safe connector re-binding flow. |
| UC-044 Data growth/storage pressure | PARTIAL | storage.py, category accounting, pause/resume tests | No owner-visible storage dashboard/notification and no accepted target-Mac retention/pressure drill. |
| UC-045 Trusted-person/emergency access | DEFERRED / OUT OF SCOPE | single-owner boundary in PRD | Correctly not implemented in current single-user scope. |
| UC-046 Headless Mac mini reboot/Keychain | PARTIAL | Core child lifecycle, Keychain-locked exit state, launch-agent plist generator | LaunchAgent is not installed/loaded; owner must log in/unlock; FileVault/reboot/Keychain behaviour not verified on target Mac. |
| UC-047 Quoted/forwarded sender attribution | IMPLEMENTED for tested Mail headers/body | macos.EmlxMailbox, mail.py; sender/body adversarial tests | Real Apple Mail store/account/version validation remains absent. |
| UC-048 Attachment-borne injection | DEFERRED / NOT IMPLEMENTED | Mail reader deliberately never reads attachment bytes and reports attachments_not_searched | PDF/Office/image/OCR attachment ingestion and hostile attachment tests are a separate unbuilt package. |
| UC-049 Calendar invite injection | UNVERIFIED | Calendar framework adapter and records API | No dedicated adversarial invite-title/description/attendee/link injection test was found in the reviewed evidence. |
| UC-050 Sports/statistics query | NOT IMPLEMENTED | No sports data source or Statsguru query module found | No fixtures, scores, standings, player/team stats or historical statistics pipeline. |
| UC-051 Personal operating context | NOT IMPLEMENTED | PRD and MEMORY_PRIVACY_KNOWLEDGE.md specification | No persistent governed memory, context relevance, provenance, correction, expiry or cross-session retrieval implementation found. |
| UC-052 Home energy/usage | NOT IMPLEMENTED | Generic home connector seam only | No meter/device telemetry, energy-cost history, heating schedule integration or measured-vs-estimated trend validation. |
| UC-053 AI/technology/science news desk | NOT IMPLEMENTED | Separate public research gateway only | No curated multi-source news desk, deduplication, topic follows/mutes, briefing scheduler or materiality ranking. |
| UC-054 Personal investment cockpit | NOT IMPLEMENTED beyond basic Finance records | Finance summary and deterministic arithmetic | No holdings/portfolio feed, allocation/performance/contributions/cash/income/exposure, price freshness, FX, overlap/fee/risk analysis or scenario comparison. |
| UC-055 Sports centre / Stats query | NOT IMPLEMENTED | No sports feed or structured query capability found | No sports workspace, filters, live/final/scheduled state or source freshness/citation golden tests. |

## 4. Lifecycle and cross-cutting use cases UC-L01–UC-L30

| ID | Status | Current evidence | Material gap / acceptance boundary |
|---|---|---|---|
| UC-L01 First run | PARTIAL | Get Started defaults off; completion independent of grants; Swift tests and hosted app launch | Human UI/accessibility walkthrough and real TCC states remain pending. |
| UC-L02 Source onboarding | PARTIAL | owner-only consent API, default-deny policy, Get Started for Documents/Mail | Real TCC/permission prompts; Finance/Health enablement is in Settings, not Get Started. |
| UC-L03 Large import | PARTIAL | incremental document/Mail indexing, coverage states and bounded background work | Tiered/newest-first UX and progress/queue evidence across every source not complete. |
| UC-L04 Unsupported format | PARTIAL | explicit document parser outcomes and coverage | PDF/Office/encrypted/attachment formats not implemented; no complete per-file user-facing triage. |
| UC-L05 OCR uncertainty | NOT IMPLEMENTED | no OCR pipeline identified | No page/location/confidence-preserving OCR flow. |
| UC-L06 Corrupt/malicious file | PARTIAL | document parser limits, symlink/path-race tests and worker isolation | PDF/Office parsers and full OS-level parser isolation not built; macOS model sandbox is not least privilege. |
| UC-L07 Internet unavailable | PARTIAL | local Core and research-off-by-default design | Real network outage and recovery behaviour not exercised; browser reading is off in production host. |
| UC-L08 Model unavailable | IMPLEMENTED for bounded deterministic fallback | local model absence is a typed state; deterministic compute and local search remain | Owner-model installation/performance not verified; no cloud fallback is correctly present. |
| UC-L09 Model switch | PARTIAL | Intelligence Gateway, explicit model mode, model descriptor/routing events | Real selected-model switching and quality-preserving context on owner hardware not validated. |
| UC-L10 Agent disagreement | NOT IMPLEMENTED generally | fixed review workflow with agents/stubs | No general coordinator conflict resolution exposing incompatible evidence/claims. |
| UC-L11 Agent timeout/crash | PARTIAL | task crash recovery, orchestrator tests | General production agent orchestration is not wired to the Core task path; retry/idempotency across all side effects remains open. |
| UC-L12 Approval changed after preview | IMPLEMENTED for Action Gateway contract | exact-payload approval, single-use/expiry/material-change tests | App cannot yet initiate a live proposed-action flow; connector/side-effect durability remains open. |
| UC-L13 External side effect | PARTIAL | Action Gateway, approval categories, content-free audit and connector profile | Durable intent/receipt/idempotency across restart is open (ATLAS-ACT-019); no chosen real vendor integration. |
| UC-L14 Undo | PARTIAL | record undo and connector compensation patch | App now preserves failed undo state and displays a message (ATLAS-APP-053; helper test and exact-head CI pending); action receipts are not durable across restart; exact-head CI pending for connector fix. |
| UC-L15 Backup/restore | PARTIAL | backup/verify/drill/restore CLI with integrity tests | G-O05 destination/retention and owner-Mac restore drill not accepted; no in-app/scheduled controls. |
| UC-L16 Device loss | PARTIAL / BLOCKED | immediate durable Core revocation and device sync model | In-flight read can repopulate iOS cache after Unpair; remote-phone defects/review remain blockers. |
| UC-L17 Update/rollback | PARTIAL | signed updater, atomic install and rollback tests | No complete schema compatibility check at rollback, pre-update backup policy or owner install/reboot exercise. |
| UC-L18 Data migration | PARTIAL | exact legacy transactions import with reconciliation and non-destructive tests | Other legacy Finance tables, Library, Images and Aperture data are not migrated; no real owner DB run. |
| UC-L19 Permission revocation | PARTIAL | task/source revalidation and purge tests | API read-after-check race ATLAS-CORE-092 remains open. |
| UC-L20 Privacy request | NOT IMPLEMENTED for governed memory | source purge/revocation exists | No memory search/correction/deletion/expiry workflow because governed memory is not implemented. |
| UC-L21 Timezone/travel | PARTIAL | deterministic date functions and timezone-aware timestamps | No full travel/scheduling ambiguity workflow or owner-confirmed timezone display for consequential scheduling. |
| UC-L22 Language mix | PARTIAL | evaluation sets and multilingual pipeline tests | Japanese/unspaced-script retrieval is documented as a gap; target-model multilingual quality unmeasured. |
| UC-L23 Duplicate/conflicting records | PARTIAL | version conflicts and record identity/version checks | No comprehensive duplicate identity/reconciliation across all source domains. |
| UC-L24 Resource pressure | PARTIAL | storage.py, bounded scheduler, pause/resume tests | No owner-visible storage/resource dashboard and target-Mac thermal/memory validation. |
| UC-L25 Notifications | PARTIAL | content-free payloads, quiet-hours and deduplication logic | OS notification delivery not owner-verified; in-app notification categories and persistence are limited. |
| UC-L26 Search coverage | IMPLEMENTED for supported indexed sources | API coverage/index status and honest partial-state tests | newest_indexed is always null; source breadth is limited and Japanese/unspaced retrieval is incomplete. |
| UC-L27 Sensitive context | PARTIAL | G-021 purpose-bound Finance/Health grants and policy tests | Synthetic only; no Health ingestion; API read race and real-model behaviour remain open. |
| UC-L28 External page injection | PARTIAL / DISABLED | untrusted-page text, GET/HEAD-only browser engine and injection tests | Production web reading is off until browser worker OS confinement is accepted; real Internet untested. |
| UC-L29 Purchase/booking/payment | NOT IMPLEMENTED | approval categories and generic Action Gateway | No real purchase/booking/payment integration or exact vendor/terms/cancellation preview. |
| UC-L30 Software-development action | DEFERRED / NOT IMPLEMENTED | no self-modification/deployment workflow found | No autonomous self-update/deploy capability; maintain the separation between personal task authority and app self-modification. |

## 5. Overall use-case conclusion

- No use-case family is fully complete across product promise, production wiring, owner-visible UX, failure/restart/revocation behaviour and owner acceptance.
- Strongest implemented testable foundations: source designation/revocation (with API read race residual), task/evidence pipeline, exact compute (precision patch awaiting CI), Mail body-only boundary, typed action/approval core, deterministic Finance/Health summaries over available records, backup/restore CLI, Core/device protocol and Swift client foundations.
- Major product gaps: governed memory, home energy/device integration, sports/Statsguru, personalised news desk, investment cockpit, general research in ordinary answers, general agentic workflows, app automation, conversation history, bulk operations, location triggers, folder/source watchers, OCR/attachments, and real owner data ingestion for Health.
- Major verification blockers: exact-head CI, least-privilege macOS sandbox, API read revocation race, Core shutdown/construction defects, durable Action Gateway recovery, browser worker confinement, remote-phone security, app cancel/undo behaviour, accessibility audit reliability, real owner-Mac/TCC/Mail/Keychain/FileVault/restore and selected-model performance/safety.
- This matrix must be updated when an implementation fix lands. A feature moving from NOT IMPLEMENTED to PARTIAL requires a named source path and test; moving to IMPLEMENTED requires exact-head CI plus full runtime/UX evidence appropriate to the requirement. Stage 3 and Stages 4–8 acceptance remain separate architect/owner decisions.
