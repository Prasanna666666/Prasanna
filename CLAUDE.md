# Instructions for Claude Code in this repository (Atlas / Project Genesis)

## Source of truth
- `docs/genesis/` is the canonical source for product requirements, decisions and plans. Read the relevant current documents before stating, restating or changing any requirement: `DECISIONS.md`, `PRD.md`, `TARGET_ARCHITECTURE.md`, `HANDOVER.md`, `USE_CASE_REGISTER.md`, `PRD_CONFORMANCE.md`, `USE_CASE_CONFORMANCE.md`, `INTERNET_AND_NETWORK_POLICY.md` and the current stage plan.
- Cite the document and section when referring to a requirement. Do not present a documented requirement as a new decision.
- The current restart point is `docs/genesis/HANDOVER.md`; current requirement/code evidence is in `IMPLEMENTATION_CONFORMANCE.md`, `PRD_CONFORMANCE.md`, `USE_CASE_CONFORMANCE.md`, `DEFECT_REGISTER.md` and `REVIEW_COVERAGE_RECONCILIATION.md`.
- Historical conversation, branch and package snapshots are records, not current implementation instructions. Follow their historical/superseded notices.

## How we work
- **One PR only:** PR #8 on branch `genesis-stage2-foundation`. Do not open another PR.
- The owner is the product authority. ChatGPT is architect/integrator/documentation owner/independent reviewer by default; Claude remains the routine implementation owner. The owner's explicit 2026-11-25 direction to finish pending review/conformance work authorises narrowly scoped source/test fixes directly tied to reviewed findings. This does not transfer broad feature ownership or authorise merge, acceptance or release.
- Keep changes scoped to one review finding or coherent batch. Reply to review threads with exact source/test evidence. Do not resolve a finding merely because its anchor is outdated; recheck the current source and tests first.
- Report evidence honestly: distinguish code present, tests added, CI run, architect-reviewed/accepted and owner-verified-on-Mac. Never claim a test pass or Mac-only behaviour without the exact run/environment.
- Run the complete repository CI suite before treating source/test changes as validated. If local execution is unavailable, say so and use an exact-head CI run. A run on an earlier code snapshot is not exact-head evidence for a later source/test change.
- Do not push a new source/test change while a named exact-head CI run is still pending unless it is required to fix a verified failure. Documentation-only changes must still be logged and the live head refreshed.
- Keep PR #8 draft and unmerged. Do not waive acceptance gates or claim Stage 3/Stages 4–8 acceptance.

## Product principles and security boundaries
- One Atlas app, one owner initially, local-first inference and no cloud inference/fallback. The macOS MLX worker currently has tested direct network/write/private-root denials, but its profile is allow-by-default and not least privilege; the complete Mach-service proxy surface is not audited. **Do not claim an accepted local-only sandbox guarantee.** Stage 3 F-11 remains release-blocking.
- Public web research is a separate API 1.1 operation behind two off-by-default gates, not ordinary answer generation. The taint filter has documented 1–3-character, paraphrase and stale-passage gaps; DNS deadline, truncation-flag and malformed-URL findings remain open. The real Internet has not been exercised.
- The local model may read owner-authorised Finance and Health data under G-021, with purpose-bound grants, deterministic financial calculations and redacted logs. Finance ingestion is limited to the legacy transactions table; Health ingestion/HealthKit is not implemented.
- Exact numbers and dates are computed and checked by deterministic code, never by the model. The exact-decimal >28-digit patch is pending exact-head CI.
- One first-run Get Started consent flow plus OS permission prompts; no repeated or per-folder prompts.
- Approval is limited to the closed list in PRD §4.4; everything else is prompt-free. Approval must bind the exact payload and be single-use. Live app proposal flow and durable Action Gateway receipts remain incomplete.
- Tests/CI use synthetic data only; no real personal data in artifacts. Hosted macOS CI is not owner-Mac verification.
- The current app is not owner-tryable. Owner visual/accessibility walkthrough, real TCC, real Apple Mail, signing/notarisation, self-contained installation, target-model performance and restore drill remain open.

## Current known review gates (2026-11-25)
- PR #8: 285 changed paths; 127 review threads, 120 resolved and 7 unresolved.
- Three sandbox least-privilege threads remain open/release-blocking.
- Four source/test findings have patches and regression coverage but await CI: exact decimal precision, API 1.1 open-object-map boundary, reversible connector prior-state/undo, and complete Keychain test inventory.
- Additional open findings include ATLAS-CORE-092, ATLAS-CORE-083/084, ATLAS-SEC-016, ATLAS-ACT-019, ATLAS-CONN-025, egress residuals, app cancellation/undo integration, accessibility audit validation and mobile/relay security.
- Exact-head CI run 45577911258 was queued for source/doc snapshot 35d41c800046ca3042991134f66bece7611191cc; refresh the live PR head and workflow state before resuming. No pass is claimed while queued.
