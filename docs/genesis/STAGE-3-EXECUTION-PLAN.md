# Atlas — Stage 3 Execution Plan

**Status:** Stage 3 authorised by owner (G-027); WP3.0 accepted; WP3.1 specification/schema/tests **ACCEPTED** for exact reviewed scope (review 6000401465); WP3.2 document-only vertical path **ACCEPTED** at exact commit `ad6e59bcb6fb5d6124ac56ea419f8330dc913e4c` (ChatGPT review 6000818496); WP3.3 Mail conditional on G-O19  
**Initiative:** Project Genesis  
**Baseline:** PR #8, `genesis-stage2-foundation`, Stage 2 accepted at `58210223398a5715b618d1163397104efd358d49`  
**Plan owner:** ChatGPT (architect/integrator)  
**Implementation owner:** Claude Code (developer/test engineer)  
**Product authority:** Owner

## 1. Executive decision

Stage 3 is the next roadmap stage: implement and verify the first useful Atlas workflow—an owner asks a question, Atlas searches only explicitly authorised local documents and Mail, reads the relevant evidence, and answers with exact citations.

This is a deliberately narrow vertical slice, not a general agent platform, broad integration programme or UI rewrite. It must prove that the Stage 2 Core foundation can safely mediate real source access, evidence retrieval, model use and task completion.

**Recommendation:** deliver the slice incrementally, beginning with contract and source-boundary design, then document retrieval, then Mail retrieval only after its separate gates are satisfied. Keep the current Python Core behind the versioned API during this stage. Do not rewrite Core in Swift or change the owner-selected Apple MLX direction without a separate evidence-backed ADR and owner decision.

The owner explicitly authorised all of Stage 3 on 2026-11-20 (G-027). Work proceeds in plan order, package by package, with exact-commit review. This plan does not waive the separate gates in section 7 or authorise Stage 4 onwards.

## 2. User outcome and scope

### In scope

- A coherent macOS-first Atlas workflow, using the accepted shared Swift/SwiftUI application boundary and the versioned Core API.
- A user can ask a natural-language question and receive a sourced answer over the local source types explicitly enabled for that task.
- Local document discovery, extraction/retrieval and exact file/page/section/block citations.
- Progressive tier-1, model-free full-text indexing, newest/recently-used first, so Atlas is useful before the entire corpus is processed; show searched/total/pending/unsupported coverage.
- Synthetic policy and integration tests for owner-authorised Finance and Health model access, with separate stores/labels and redacted diagnostics.
- Mail discovery and read-only retrieval, with citations to the exact message and stored header/span evidence, after onboarding and OS access are active.
- A separate supported-attachment package for all supported formats, delivered after Mail body and accepted only after provenance, OCR confidence, parser isolation and hostile-file tests.
- One first-run Get Started consent flow plus OS permissions; Core grants remain default-deny until consent and are revalidated before reads/model calls. No repeated prompts or per-folder toggles.
- Policy enforcement before retrieval and at every model boundary; owner-authorised Finance and Health data may enter local model context under G-021, with separate domain controls and redacted audit.
- Durable, cancellable task progress and honest partial/failure states, using Stage 2 task/event contracts.
- Evidence-grounded answers, deterministic checks for exact numbers/dates, redacted operational events, and synthetic adversarial tests.
- A minimal usable macOS interaction path: conversation, progress/cancellation, citations/source inspection, and clear unavailable/permission/partial states.
- Local model adapter integration consistent with Apple MLX direction, subject to target-Mac verification. Linux CI continues to use deterministic stubs.
- Public Internet research through the Core egress gateway when useful, using synthetic fixtures in CI and never sending private owner data to public search.
- Measurement of retrieval/answer quality and performance, with developer-machine, CI and target-Mac evidence kept distinct.

### Explicitly out of scope

- Any write, send, share, purchase, booking, financial transaction or other external side effect.
- Mail attachment content exposure until its separate technical package is implemented and accepted. Owner scope is already decided: all supported formats.
- Reading local sources before the one-time Get Started consent and required OS access are active.
- Consequential external actions, destructive migration, unrestricted agent delegation or cross-domain access that bypasses Core policy.
- Unrestricted or always-running agent swarms; specialists must be on-demand and task-bounded.
- Broad connector expansion, calendar writes, remote access or iOS implementation before their respective gates. Public Internet research is allowed only through the network policy.
- Destructive data migration, consolidation of legacy stores, deleting legacy apps/data, or making a new store the sole copy.
- A Core-language rewrite, runtime substitution, silent model downsize or cloud inference/fallback.
- Claiming target-Mac performance, MLX operation, macOS credential behaviour or production readiness without actual target evidence.

## 3. Architecture and implementation constraints

1. **One application.** The user sees Atlas, not separate Documents/Mail/Finance apps. Domain capabilities remain internal modules.
2. **Core is the policy authority.** UI, source adapters, models and specialist workers cannot bypass Core permission checks.
3. **Default deny.** A source is not searchable until its source type and applicable sensitivity scope are explicitly enabled. Documents and Mail are independent grants.
4. **Policy before data.** Authorisation must be evaluated before any source content is read or returned by full-text, semantic, graph, cache or summary retrieval. Revalidate grants at read and model boundaries.
5. **Untrusted content stays data.** Document and Mail text cannot alter system policy, task scope, permissions or approval state. Hostile instructions must not trigger actions.
6. **Finance and Health remain governed domains.** The local model may read owner-authorised data under G-021; retain separate stores/labels, provenance, revocation and redaction. Exact financial calculations are deterministic.
7. **Evidence is first-class.** Every material personal-data claim links to immutable source identity/version and exact location where available. Conflicts, stale evidence and missing support are explicit.
8. **No silent truncation or loss.** Resource limits must be explicit and visible. Incomplete extraction/retrieval is marked incomplete, never silently treated as complete.
9. **Local-only inference.** Apple MLX is the selected runtime direction. No cloud inference or silent remote fallback. A missing local model produces a clear unavailable state.
10. **Keep the Stage 2 contract stable.** Additive compatible API evolution only. Model identity/routing metadata is a planned minor-version contract addition; do not retrofit or misrepresent the frozen Stage 2 API 1.0.
11. **Keep Python Core for this stage.** G-O20 remains open. Do not rewrite before target-Mac MLX and signed/notarised Python-helper evidence plus a separate ADR and owner decision.
12. **No unapproved migration.** Preserve original source data, keys and historical behaviour. Any migration requires inventory, integrity verification, backup and rollback plan, and owner approval where material.

## 4. Work packages and order

Work is sequential where dependencies or trust boundaries require it. Independent tests and documentation may proceed in parallel. Each work package has its own completion evidence; a later package cannot bypass a closed gate.

### WP3.0 — Reconfirm baseline and implementation map

**Owner:** Claude implements the audit; ChatGPT verifies and reconciles.

- Reconfirm exact PR #8 accepted head and current `core/` contracts/tests.
- Map the Stage 1 audit and current repository components to reuse, reference-only or discard for this slice.
- Identify current document and Mail source locations, formats, permissions, lifecycle and test seams without reading or copying private content into CI.
- Map every Stage 3 requirement to a code path, test and evidence item.
- Report drift, missing source adapters, unverified assumptions and any data/key migration dependency before coding.

**Exit:** current-state map and requirement traceability accepted by ChatGPT; no unexplained baseline drift.

### WP3.1 — Contract delta and threat model

**Owner:** ChatGPT authors/owns target contract changes; Claude challenges and implements approved contract changes after Stage 3 authority.

- Specify additive API minor-version changes needed for safe model identity/routing descriptor (model ID and routing role; runtime/version only where safe), plus a redacted route event. Never expose prompts, retrieved text or personal context in the event.
- Specify source designation/grant contracts for Documents and Mail independently: scope, sensitivity, purpose, revocation, current-grant revalidation and user-visible state.
- Specify citation/evidence objects for document and Mail source spans, including source version/hash, exact locator and integrity/validity semantics.
- Define task response states: complete, partial, denied, unavailable, needs-attention, cancelled and failed; no ambiguous success.
- Threat-model parser/extractor boundaries, malicious files and Mail prompt injection, source confusion, stale grants, cross-domain leakage, cache/index leakage, logs and denial-of-service/resource exhaustion.
- Specify how the UI displays the exact source types in scope, citations, model identity, unsupported attachment status and partial processing.

**Exit:** reviewed contract delta, threat model and test matrix; no unresolved high/critical security design issue. G-O18 scope and the G-O19 low-friction onboarding direction are already owner-set; implement and verify them rather than re-asking.

### WP3.2 — Document-only vertical path

**Status: ACCEPTED** for exact commit `ad6e59bcb6fb5d6124ac56ea419f8330dc913e4c` (ChatGPT review 6000818496). Scope: UTF-8 text/Markdown only; encrypted index; exact block locators and content-version checks; explicit unsupported/failed coverage; descriptor-relative no-follow traversal; no model call when no usable passages; synthetic tests for policy, citations, hostile content, restart/idempotency and failure handling. Limits: coverage is not yet in the answer envelope, lexical ranking only, no PDF/Office/HTML/Mail, and no target-Mac/OS-level parser isolation evidence. This acceptance is not production or Stage 3 release approval.

**Owner:** Claude implementation; ChatGPT independent review.

- Implement or adapt the local document source adapter and extraction/retrieval path for the supported, audited formats.
- Preserve source identity, version/integrity metadata and exact page/section/block locations through extraction and retrieval.
- Enforce source designation and sensitivity policy before any content reaches retrieval results or model context.
- Handle unsupported, encrypted, corrupt, oversized and partially extracted files as explicit needs-attention states. Do not silently skip or truncate.
- Keep extraction/indexing asynchronous and restart-safe; preserve checkpoints and idempotency.
- Return citations that resolve to the exact source and span; reject invalid, stale or mismatched citations.
- Use synthetic fixtures for CI. Real owner documents are used only in a separately authorised owner-controlled test, never copied into CI or external services.

**Exit:** automated tests prove default-deny, correct grant/revocation behaviour, exact citations, hostile-document isolation, redaction, idempotent restart and honest partial states. No Mail access is implied by Document enablement.

### WP3.3 — Mail read-only path (conditional)

**Owner:** Claude implementation after gates; ChatGPT reviews.

- Do not begin Mail content retrieval until G-O19 has an accepted Mail designation mechanism and explicit owner enablement.
- Treat Mail body, stored headers/metadata, thread context and attachment content as distinct source types with distinct provenance and policy.
- Keep attachment content unavailable until the separate attachment package passes technical acceptance. The owner has already set scope to all supported formats; answers must disclose attachment coverage and unsupported/partial extraction.
- Cite exact message identity, stored sender/date fields and exact body span; do not infer sender/date from message text.
- Treat all message content as untrusted. Test hostile instructions requesting broader search, secret disclosure, outbound sending or policy changes.
- Ensure no Mail retrieval happens when Mail is not enabled, even if a message is already present in local storage.

**Exit:** source-isolation, citation, injection, revocation, redaction and restart tests pass under the single Get Started consent and OS grant. Attachment content remains separately gated until its technical package is accepted; G-O18 is not an unanswered owner preference.

### WP3.4 — Intelligence Gateway and answer quality

**Owner:** Claude implements the approved adapter/route; ChatGPT owns evaluation criteria and independent review.

- Integrate the local MLX path behind the model adapter without coupling domain capabilities to a specific model.
- Enforce the same Core policy gate on every model call, including route/model switches.
- Expose safe model identity in the answer and redacted route metadata, consistent with WP3.1.
- Use deterministic code for exact arithmetic, dates, units, schema checks and citation validation.
- Build a versioned synthetic evaluation set for English, Dutch and at least one non-Latin-script document/question set; report retrieval quality separately from answer quality.
- Include missing/contradictory/stale evidence, abstention, hallucination, citation correctness, prompt injection, cross-domain leakage and tool-selection cases.
- Compare direct/single-model execution with delegated execution only if delegation is proposed; do not introduce multi-agent overhead without measurable quality benefit.

**Exit:** evaluation report shows source attribution, exactness, abstention and policy-boundary results; no personal content is present in CI/evaluation artefacts. Actual MLX quality/performance claims require target-Mac evidence.

### WP3.5 — Minimal macOS experience and workflow integration

**Owner:** Claude implementation; ChatGPT UX/architecture review.

- Deliver one coherent Atlas conversation path for the approved workflow.
- Show acknowledgement/progress for accepted background work; allow cancellation and preserve durable task state.
- Show source citations with a usable source-inspection interaction, source enablement state, model identity and clear failure/partial/unavailable messages.
- Do not surface raw stack traces, prompts, source text in logs or internal implementation detail.
- Maintain keyboard/accessibility basics and responsive UI while indexing runs.
- No separate Documents or Mail application or settings surface.

**Exit:** end-to-end synthetic workflow passes through the actual client/Core contract; failure, cancellation, denied-source and unavailable-model states are understandable and recoverable.

### WP3.6 — Reliability, security and performance verification

**Owner:** Claude supplies reproducible evidence; ChatGPT independently reviews.

- Fault-inject process termination at task, extraction, index, retrieval and answer boundaries; prove restart recovery or explicit needs-attention.
- Test idempotent retries, cancellation, stale/revoked grants, cache invalidation, corrupt/unsupported inputs, disk pressure and concurrent interactive/background load.
- Run redaction sentinel tests across normal, error and debug paths.
- Benchmark representative inventory after inventory verification (initial planning estimate: ~26,000 Mail items and ~1,400 documents). Measure first-pass/incremental ingestion, time-to-searchable, retrieval quality, disk growth, CPU/GPU, peak/steady RAM, thermal/energy impact, queue delay and interactive p50/p95/p99.
- Record actual machine/chip/RAM/OS, power/thermal state, model/quantisation/context, concurrency and workload. Separate CI, developer-machine and target-Mac results.
- Do not claim target performance from Linux or another machine. Linux CI uses deterministic model stubs.

**Exit:** automated CI gates pass; no unresolved critical/high security or data-integrity issue; performance results and deviations are documented. Target-Mac-specific gates remain explicitly pending until performed on the intended Mac.

### WP3.7 — Integration acceptance and handover

**Owner:** ChatGPT reviews; owner retains product acceptance.

- Review exact final commit, changed paths, requirement traceability, tests and CI.
- Verify docs match implemented behaviour and distinguish developer-reported, CI-verified, architect-inspected and owner-verified evidence.
- Record known limitations, rollback/recovery instructions and deferred gates.
- Present a concise owner acceptance brief with any real product trade-off, not routine technical questions.

**Exit:** ChatGPT recommends accept/request changes/defer with evidence; owner decides product acceptance. No merge/release is implied.

## 5. Acceptance criteria (release-blocking for this slice)

1. **Source designation:** Documents and Mail are independently default-deny. No source content is read, retrieved, cached into model context or searched before a current grant.
2. **Revocation:** Revocation is enforced before each source read and each model boundary; stale grants/caches cannot return protected content.
3. **Citation integrity:** Every personal-source claim has a resolvable source/version and exact location; invalid, stale or unsupported citations fail closed.
4. **Injection resistance:** Hostile document/Mail instructions cannot change policy, widen retrieval, cause action execution or reveal unrelated data.
5. **Domain governance:** owner-authorised Finance and Health data may enter local model context; unrelated-domain retrieval remains policy-controlled. No private content enters logs, public web queries or evaluation artefacts.
6. **Mail attachment boundary:** all supported formats are in scope, but attachment contents remain unavailable until the separately specified and tested attachment package is accepted; UI/answers disclose coverage and limitations.
7. **Exactness:** Numeric/date/unit claims use deterministic validation; unsupported claims are withheld or labelled uncertain.
8. **Durability:** Jobs survive restart safely; retries are idempotent; cancellation is honoured; partial work is never marked complete.
9. **Redaction:** Automated sentinel scans find no personal content, source names, message subjects/addresses, prompts or secrets in logs and CI artefacts.
10. **Honest failure:** Denied, unavailable, unsupported, corrupt, partial, stale and failed states are explicit and user-safe.
11. **Local-only:** No cloud inference or silent remote fallback; each model route re-enters Core policy.
12. **Performance:** Quality and latency are measured together; no accuracy reduction is hidden to meet speed targets.
13. **Usability:** One Atlas experience supports question, progress, cancellation, citations and clear outcomes.
14. **Traceability:** Every requirement maps to implementation, automated test, CI evidence and known limitation.
15. **No destructive migration:** No irreversible source/store migration or retirement of legacy components occurs in this stage.

## 6. Measurement and quality gates

The existing latency objectives remain provisional until measured on the intended target Mac:

- Simple request first useful output: target <2 seconds.
- Typical conversational completion: target <5 seconds.
- Complex reasoning: aim <30 seconds, with actual distribution reported.
- Accepted background task acknowledgement: target <1 second.
- No interactive starvation during background ingestion.

For every benchmark report p50/p95/p99 and cold/warm results. Report answer quality alongside speed, including retrieval precision/recall where the evaluation set permits, citation correctness, unsupported-claim rate, abstention correctness, prompt-injection pass rate, and cross-domain leakage count. A target is not a verified result. Numeric pass thresholds must be proposed from the baseline and accepted before they become release gates; do not invent them after seeing results.

## 7. Dependencies and owner-reserved gates

| Gate | Dependency | Required before |
|---|---|---|
| G-O18 | Owner scope is all supported formats; technical package must define format matrix, provenance, OCR confidence/limits, parser isolation and hostile-file tests | Any attachment extraction/indexing/retrieval |
| G-O19 | Implement one first-run Get Started consent plus macOS permissions; Core enforces source grants and revocation without per-folder prompts | Any real local source read |
| G-O01 | Actual target-Mac MLX model/quantisation/context and resource benchmark; fallback decision if no candidate passes | Production model selection and target performance sign-off |
| G-O20 | Evidence-backed Core language/runtime assessment; current recommendation is keep Python during Stage 3 | Any long-term Core language decision or rewrite |
| G-O02/G-O05 | Storage/key-boundary ADR and accepted backup/restore/key-recovery experience with tested restore | Store consolidation, single-copy dependency or release relying on recovery |
| G-O12 | Native packaging/update/signing/notarisation and rollback design | Production Mac distribution |
| G-O14/G-O15 | Remote-access threat model/ADR and mobile offline/cache/sync policy | iOS/remote access; not a dependency for Stages 0–7 |

**Owner decisions are requested only when a genuinely reserved choice is reached.** G-O18 scope and G-O19 consent direction are already settled. G-O05 backup/key-recovery experience remains open before a release relies on backup or store consolidation. Other gates remain governed by the Decision Register.

## 8. Delivery sequence, ownership and reporting

| Responsibility | Accountable party |
|---|---|
| Product direction, priority, reserved decisions and final product acceptance | Owner |
| Architecture, canonical requirements, work packages, cross-cutting integration and independent review | ChatGPT |
| Code, developer tests, debugging, implementation docs, CI and reproducible evidence | Claude Code |
| Automated regression/security/quality checks | GitHub Actions |
| Target-Mac verification | Claude/owner when the hardware is available; evidence explicitly labelled |

Claude's implementation brief for each work package must include exact objective, paths, interfaces, requirements, non-goals, test commands, security/privacy, performance, rollback and stop conditions. Completion reports must include exact branch/commit, changed paths, test commands/results, CI links, benchmark environment, deviations, limitations and rollback.

ChatGPT reviews the exact commit rather than relying on summaries. Any critical/high security, privacy, data-loss or external-side-effect issue stops the affected work and is escalated. The owner is not asked to relay messages or coordinate the two engineering roles.

## 9. Stage 3 stop conditions

Stop the affected work and report with evidence if:
- a required source grant is absent, ambiguous, revoked or cannot be enforced before retrieval;
- a model or client path can bypass Core policy;
- Finance/Health data can enter a task/model context without the owner's current grant, or leave the Mac through an unauthorised egress path;
- untrusted content can trigger an action or widen permissions;
- source integrity, citation provenance, deletion or recovery cannot be guaranteed;
- implementation requires an unapproved destructive migration, external exposure, cloud inference or owner-reserved scope change;
- target-Mac claims are being made without target-Mac tests;
- no acceptable MLX model meets the agreed quality/resource envelope (return options to owner; do not silently downsize or switch runtime).

## 10. What happens after this plan

1. ChatGPT maintains the canonical plan, scenario register, network policy and requirement-to-test traceability.
2. Claude independently challenges the reconciled product baseline and execution plan for omissions, contradictions, feasibility and security; do not code during that challenge.
3. ChatGPT reconciles the findings, updates the canonical baseline and issues a bounded implementation brief.
4. Stage 3 is authorised by G-027. Implementation proceeds only through bounded packages with ChatGPT's exact-commit review; this does not imply release, destructive-migration, or separately gated platform authority.
5. After authorisation, work proceeds in dependency order, with exact-commit review and evidence at each package.

## 11. Approval record

- Stage 2 review: **ACCEPTED by ChatGPT** for exact head `58210223398a5715b618d1163397104efd358d49`; 22/22 exact-head CI checks successful. This is not production/release sign-off.
- Stage 3 plan: **reconciled after technical challenge; owner authorisation granted in full under G-027 on 2026-11-20**.
- Stage 3 implementation: **authorised; WP3.0 accepted; WP3.1 accepted (specification-only); WP3.2 accepted for exact commit `ad6e59bcb6fb5d6124ac56ea419f8330dc913e4c` (review 6000818496). WP3.3 Mail is conditional on G-O19 designation/consent and explicit owner enablement. API 1.1 is not served by Core.**
- Target-Mac verification: **pending hardware availability**.

## 12. Superseding owner direction and product-wide planning addendum (2026-11-20)

This section is authoritative wherever earlier sections conflict. It does not mark features implemented or verified.

### 12.1 Product boundary and consent
Atlas is single-user. Remove requirements that exist only for multiple users, shared devices or bystanders. Routine read/search/summarise/analyse/draft/compute operations do not require approval. Use one first-run Get Started consent flow plus macOS system permission prompts; no repeated prompts or per-folder selection. Core still enforces current grants and immediate revocation internally.

Approval is limited to the exhaustive categories in PRD §4.4: sending/publishing/sharing/uploading outside the Mac; spending/purchases/payments/trades/bookings; deletion/overwrite without reliable undo or destructive migration; and unlocking external physical access or disabling safety/security systems. Nothing else prompts. Preview the exact action, payload, destination/recipient, attachments, amount and terms. Any material change invalidates approval.

### 12.2 Finance and Health
The owner explicitly permits the local model to read owner-authorised Finance and Health data (PR #8 comment 7049796870). This supersedes the former Finance model exclusion and Health lock. Keep separately labelled/keyed stores, grants, provenance, redacted logs, cache invalidation and revocation. Use deterministic code for exact financial arithmetic. Never send these records to public web search, third-party services or cloud inference.

### 12.3 Attachments and progressive usefulness
The owner decided all supported Mail attachment formats are in scope. G-O18 is a technical design/acceptance gate, not an unanswered product preference. Keep attachment processing separate from Mail body processing. Define supported formats, parser isolation, provenance, exact locators, OCR confidence/limitations, malformed/encrypted/oversized behaviour, hostile-file tests and partial-coverage disclosure before exposure.

Progressive usefulness is mandatory: tier-1 model-free full-text indexing begins with newest/recently-used content and expands in the background. Atlas must answer from the indexed subset without waiting for the entire corpus, while displaying items searched/total, pending categories and unsupported/failed items. Never represent partial coverage as complete.

### 12.4 Internet and connected apps
Public Internet search and retrieval are allowed when useful. INTERNET_AND_NETWORK_POLICY.md defines egress rules: no cloud inference, no raw private content in public queries, no secrets or Finance/Health data sent externally, Core-mediated network access, Keychain-held connector credentials, untrusted-page handling and exact approval for uploads/sends/purchases. Local-only work continues offline.

### 12.5 Full capability coverage and agents
USE_CASE_REGISTER.md is the canonical cross-domain scenario register and connector catalogue. It covers daily assistance, communication, calendar, files, Finance, Health, home, travel, work, research, shopping, family/social, legal/admin, media, security, memory, proactive work, lifecycle failures and recovery. It is an extensible coverage method, not a claim that every scenario is in the first release.

Use Atlas Core as the single coordinator with on-demand specialists and a Guardian/verifier role. Do not deploy always-running or unrestricted agent swarms. Parallelise independent work, require structured evidence/limitations from specialists, and measure quality improvement against the simpler single-model path before adding orchestration overhead.

### 12.6 Roadmap reference and Stage 3 scenario boundary

There is exactly one delivery roadmap: TARGET_ARCHITECTURE.md §11. Do not create a second numbered stage sequence or wave-based roadmap in this plan. Scenario-to-stage mapping and first-tryable outcomes are defined in that canonical table. Stage 3 is the first owner-tryable Mac application; Stages 4–8 extend it in the order and with the gates recorded there.

### 12.7 Updated work ownership
ChatGPT is accountable architect/integrator: canonical requirements, scenario-to-test traceability, cross-cutting design, exact-commit independent review and release recommendation. Claude Code owns implementation, developer challenge, tests, CI diagnosis, reproducible evidence and implementation documentation. GitHub Actions provides automated checks. The owner retains product direction, reserved decisions and final acceptance and is not a messenger between engineering roles.

### 12.8 Current gate
Stage 3 is authorised under G-027 and proceeds package by package after a written implementation brief and exact-commit review. WP3.0 and WP3.1 are accepted; WP3.2 is accepted at `ad6e59bcb6fb5d6124ac56ea419f8330dc913e4c`. WP3.3 is next but Mail content retrieval remains blocked until G-O19's designation/consent mechanism and explicit owner enablement are active. The accepted WP3.2 work is a Mac-independent Core vertical path, not an installable or owner-tryable Mac application. Target-Mac-only claims remain pending hardware access.

### 12.9 First-useful-answer and indexing acceptance

- Define “newest” per source: Mail by stored received timestamp for inbox chronology; files by filesystem modification time, with content-created dates retained as separate metadata and never substituted silently. Missing timestamps use a deterministic stable fallback and are counted in coverage.
- Freeze the first-useful-answer threshold before the first baseline benchmark: warm local query p50 ≤2 seconds and p95 ≤5 seconds after the first tier is searchable. Report cold start separately and report retrieval/answer quality alongside latency.
- The first tier must be useful before full import completes. Every answer reports source coverage: searched/total, pending categories and unsupported/failed items. A partial index must never be labelled complete.
