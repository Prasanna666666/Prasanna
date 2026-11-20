# Atlas — Handover

**Status:** Updated for single-application direction, owner MLX/model decisions, Claude's documentation review, and consolidated PR #8 delivery  
**Repository:** `Prasanna666666/Prasanna`  
**Documentation branch:** `genesis-stage2-foundation` (documentation now consolidated into PR #8)  
**Implementation baseline:** `atlas`

## Authoritative entry point

Start with [README.md](README.md), then read the canonical documents it indexes. The [Delivery Protocol](DELIVERY_PROTOCOL.md) is the sole authority for role ownership, collaboration, handshakes, issue resolution, change control and acceptance. Do not duplicate those rules here.

## Owner-confirmed product boundary

There is exactly **one Atlas application**. Standalone Finance, Documents, Images and other legacy application shells are obsolete. Their useful features and data must be integrated into Atlas as internal capabilities. Hidden helper processes are allowed only when technically justified; they do not constitute separate apps. macOS is first, followed by an iOS client usable worldwide wherever secure connectivity is available. Android is out of scope. Atlas Core and AI inference remain under owner control; worldwide access must not introduce cloud inference.

## Basic facts — current owner-approved baseline

| Area | Current fact | Status / boundary |
|---|---|---|
| Product | One Atlas application; personal operating system / intelligent chief of staff | Owner decision |
| Platforms | macOS first, iOS later; worldwide iOS access through secure connectivity; Android out of scope | Owner decision; remote-access ADR and threat model still required |
| Hardware profile | 32 GB Apple-silicon Mac mini | Planning profile, not proof of a purchased/tested machine or verified minimum |
| Inference locality | Local-only; no cloud inference or silent remote fallback | Owner decision |
| Inference runtime | Apple MLX | Owner-selected direction; target-Mac integration still unverified |
| Main model | Approximately 27B-parameter class, exact model selected by benchmark | Owner direction; exact family, quantisation, context and fallback remain open |
| Model routing | Automatic task-based model switching; show which model answered | Owner decision; routing policy and measurements remain to be implemented |
| Core boundary | Versioned, language-neutral API behind the shared Swift/SwiftUI macOS+iOS app | G-O17 accepted; Core implementation language is separate G-O20 decision |
| Core language | Not yet decided for long-term production | Stage 2 Python reference implementation does not decide this; compare Python and Swift with MLX, packaging, security, reuse and migration evidence |
| Mac distribution | Direct download; Developer ID signed and notarised | Owner-approved direction; packaging/update/rollback implementation remains G-O12 |
| First workflow | Read-only questions over explicitly enabled local documents and Mail, with exact citations | Source designation and attachment gates remain closed until G-O19/G-O18 are resolved |
| Sensitive domains | Finance raw records excluded from model/general-agent context; Health locked by default | Owner decisions; deterministic Finance boundary |

ChatGPT owns this table and must update it whenever the owner establishes a durable product or technical fact. Distinguish owner decisions, recommendations, implementation status and verified evidence; never promote a target into a claim that it is already built or tested.

## Repository handling

- `atlas` is the implementation baseline for gap analysis.
- `genesis-architecture` contains this target documentation and handover.
- `aperture` is the repository default/legacy Photos branch, not the Atlas product target.
- `orbit` is historical reference material, not the active implementation baseline.

Do not delete branches, historical evidence, user data, databases or indexes as part of documentation cleanup. Retire obsolete app shells only through an approved, tested migration with data preservation and rollback.

## Historical PR #7 audit trail and current PR #8 gate

**Stage 0 — documentation review and reconciliation: COMPLETE.** Claude's full-document consistency confirmation is recorded in PR #7 comment 7023445432.

**Stage 1 — implementation audit / gap analysis: ACCEPTED AND CLOSED.** Claude's audit reports are recorded in PR #7 comments 7022436618, 7022456916 and 7022810935, with the superseding final note in 7022967306. ChatGPT's formal acceptance is recorded in comment 7022990234. The audit was documentation/evidence work only; its stated limitations and unverified Mac-dependent behaviour remain in force.

The completed sequence is retained in the PR discussion as the audit trail. It does not grant implementation authority.

**Architecture decision and Stage 2 authority — COMPLETE.** Claude's technical challenge is recorded in PR #7 comment 7035425400 and its focused document verification in 7037231906. The owner accepted G-O17 and explicitly authorised Stage 2 on 2026-11-20; the owner waived the ChatGPT package-acceptance gate so implementation could proceed (decision recorded in PR #7 comment 7037299974 and subsequent owner instructions). These decisions are final; do not ask the owner to repeat them.

**Current Stage 2 implementation gate — PR #8 exact-head review.** The only open PR is [PR #8](https://github.com/Prasanna666666/Prasanna/pull/8), branch `genesis-stage2-foundation`. Claude's fix commit `1aa8aef` is byte-identical in `core/` at current review head `5cd8817`; Claude's summary is comment 7045588310. ChatGPT re-reviewed the three findings from review 5996187506 against that code: per-item sensitivity is filtered at retrieval, context construction and model boundary; current grants are revalidated before each source read and at the model door; task state/checkpoint/reason and associated stream events are committed in one transaction, including cancel, expiry and recovery. Exact-head CI for `5cd8817` completed successfully. The three previously identified code blockers are accepted. Claude's documentation review 7045420044 (old PR #7, head `a2a53ba`) has been reconciled into this branch: G-O01 benchmark criteria, G-O20 recommendation, MLX transparency/routing requirements and ADR wording are updated. Model identity in answer/safe-event contracts is an additive Stage 3 gate, not a Stage 2 blocker. PR #9 is closed/unmerged; its low-level design is being carried into this branch as a review-baseline document rather than merging a second PR. Real macOS Keychain, macOS `LOCAL_PEERCRED`, Swift/Xcode integration, target-Mac MLX performance and packaging/notarisation remain unverified. Do not claim production readiness. Stage 2 code blockers are cleared; remaining platform verification and release acceptance are still pending. PR #8 stays draft and unmerged.

**Stage 3 is NOT AUTHORISED.** No Stage 3 implementation, real source ingestion/search, Mail attachment processing, remote exposure, data migration or destructive action is authorised by the Stage 2 decision. G-O18, G-O19, G-O14 and other feature-specific gates remain in force.

The Stage 1 audit included the iOS target in its assessment. Mobile implementation and worldwide secure access remain separately gated by the remote-access threat model, device identity, offline/sync and mobile release decisions.

## Evidence status

This handover is a target/documentation instruction, not proof that legacy apps have already been retired or that the implementation has been consolidated. Current behaviour must be established from code, tests and CI. Target-Mac and local-model checks must be explicitly reported as owner-verified or pending.
