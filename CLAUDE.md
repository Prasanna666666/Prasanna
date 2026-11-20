# Instructions for Claude Code in this repository (Atlas / Project Genesis)

## Source of truth
- `docs/genesis/` is the source of truth for requirements, decisions and plans. **Read the relevant documents before stating, restating or changing any requirement** (`DECISIONS.md`, `PRD.md`, `TARGET_ARCHITECTURE.md`, the current plan, `HANDOVER.md`, `USE_CASE_REGISTER.md`, `INTERNET_AND_NETWORK_POLICY.md`). Do not work from memory or from a summary of an earlier conversation.
- Cite the document and section when you refer to a requirement. Post to ChatGPT only what is **new** compared with the documents; never present a documented requirement as a new decision.
- ChatGPT owns the canonical documents. Do not edit `docs/genesis/` unless asked; report findings on the PR instead.

## How we work
- **One PR only** (currently #8, branch `genesis-stage2-foundation`). All discussion and review happens there. Do not open another PR.
- The owner is the product authority, not a messenger. ChatGPT is accountable architect/integrator; Claude owns implementation, developer challenge and reproducible evidence. Never ask the owner to relay messages or repeat settled decisions. Resolve technical choices within delegated authority and record them on PR #8; ask the owner only for genuinely reserved product decisions.
- One commit per review round; name the exact commit in every post; do not push while a named commit awaits review.
- Report evidence honestly: say what was run and what was not; label developer-reported, CI-verified, architect-inspected and owner-verified-on-Mac separately. Never claim a Mac-only behaviour verified without the Mac.
- Run the whole repo test suites, including `kit/tests/test_architecture.py`, before pushing, not only `core/`.

## Product principles the owner has stated
- One Atlas app, one user, fully local (no cloud inference). The local model may read all the owner's data, including Finance and Health.
- Exact numbers and dates are computed and checked by code, never by the model.
- Approval is needed only for extreme actions (sending or sharing out of the Mac, deleting or overwriting, spending money). No incidental friction or repeated prompts.
- Synthetic data only in tests and CI; no real personal data in artifacts.
