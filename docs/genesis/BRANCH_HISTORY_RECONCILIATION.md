# Repository branch inventory and cross-branch reconciliation — 2026-11-23

## Source and scope

Branch inventory was fetched from GitHub's repository branches endpoint (12 branches returned). Commit-history pagination was exhausted for all 12 returned branch heads using the commits endpoint. At capture, this produced 6,897 branch-reachable commit entries across the 12 branches; this is not a unique-commit count because branches share ancestry. The full 6,897 commit messages/diffs have not been exported or reviewed; recent subjects were sampled for audit leads. Unique-SHA deduplication, full message extraction and substantive commit review remain open.

## All returned branches and heads

| Branch | Head SHA | Notes |
|---|---|---|
| `aperture` | `5d3ddb54fabbb4d11a17cabff96d2f65cc2d1385` | Legacy Lumo/Photos/Aperture application lineage |
| `aperture-hardening` | `ec98d053abaaa94066acf9194fdcb1abaf6b90c2` | Earlier performance, model gateway and security hardening |
| `atlas` | `7a3b4479bcbb27fb2bab570759ad14851c78e945` | Legacy Atlas audit/fixes branch; PR #6 snapshot ancestry |
| `atlas-low-level-design-review` | `5c34d574416940e87c96e9c96aee2697f7b4f871` | PR #9 LLD branch |
| `dependabot/github_actions/actions/checkout-7` | `1bb25c2fe966fbf8ce578a1c8526efea20789a7e` | Closed/unmerged PR #3 work branch |
| `dependabot/github_actions/actions/setup-node-7` | `d5cc48fab6e5fd70178a99b7d3c95fe16a3fda74` | Closed/unmerged PR #5 work branch |
| `genesis-architecture` | `fac21308a481fef92a79f6ca4fbf17df805b030a` | Genesis/Stage 2 architecture review branch |
| `genesis-stage2-foundation` | `4269f6340af1d5c75ca132cab33500fd130db945` | PR #8 head at capture |
| `genesis-stage3-prep` | `6cdba6caf83bab6b67d8a57af57969b85aca4de1` | PR #10 preparation branch |
| `genesis-stage4-6` | `106abe0050903993fe101b0a9683b0237dd520fc` | Separate Stage 4–8 implementation branch; not PR #8 head |
| `orbit` | `624d21c816b734c8867c448d4970bbba9ac73a0b` | Earlier app/product lineage |
| `wip/health-freshness` | `3b45c715576acdfc4440512ff8a56783bebd77da` | Explicit WIP/untested Health freshness change |

No additional branches were returned by the endpoint at capture time. This list does not imply every branch's full history has been reviewed.

## Critical branch divergence

PR #8 metadata confirms:
- Base branch: `atlas`
- Head branch: `genesis-stage2-foundation`
- PR #8 head SHA at latest verification: `ec8d760bb6d16e40de932e5270e712386042545f`
- GitHub's paginated PR #8 changed-file endpoint: 278 paths (rechecked after adding source archives).

However, the PR #8 body states that Stages 4–8 are also on this branch. The actual branch inventory and compare endpoint show `genesis-stage4-6` is a distinct branch, not the PR #8 head.

Compare `genesis-stage2-foundation...genesis-stage4-6` at capture:
- Diverged histories: 8 commits ahead on `genesis-stage4-6`, 82 commits behind relative to `genesis-stage2-foundation`.
- 61 changed paths in the comparison.
- The branch contains new Stage 4–8 modules and tests, including backup/restore, storage, migration, finance/health records, Action Gateway, orchestrator, browser workflows/watchers, device pairing/sync, updater/signing and LaunchAgent support.
- Latest Stage 4–8 branch commits include:
  - `fdb737ae51` Stage 4 backup/restore/key recovery, storage pressure, LaunchAgent.
  - `fec48242ed` Stage 5 Finance/Health/Calendar/Contacts/Notes records, deterministic finance calculations, legacy Finance import and undo.
  - `8a933fa6f8` Stage 6 Action Gateway, record actions, agent orchestrator, browser workflows and watchers.
  - `1182be7a3e` testable portions of Stages 7–8: signed update/rollback, signing, diagnostics, pairing/revocation, offline sync and push privacy.
  - `88d02d26c9` wiring of Stages 5–6.
  - `106abe0050` latest report update: pause under disk pressure, restore-drill gate, persisted action audit, device pairing routes and production host keys.
These are author commit subjects, not independent verification. The full branch diff and tests must be independently reviewed before any of these capabilities are described as accepted.

Other branch comparisons:
- `atlas...genesis-stage2-foundation`: PR #8 branch is 410 commits ahead, 0 behind; compare reports 276 files at the then-current compare snapshot (this compare count differs from the paginated PR changed-file endpoint's 275 and must be reconciled by exact base/head snapshots).
- `atlas...genesis-stage4-6`: 337 commits ahead, 0 behind; 191 files.
- `atlas...genesis-stage3-prep`: 195 commits ahead, 0 behind; 60 files.
- `genesis-stage2-foundation...genesis-stage3-prep`: diverged, 4 commits ahead on Stage 3 prep, 232 behind; 4 changed paths, including the Stage 3 baseline audit and contract delta docs.
- `genesis-stage2-foundation...atlas-low-level-design-review`: diverged, 1 commit ahead on LLD branch, 323 behind; one changed path, `docs/genesis/LOW_LEVEL_DESIGN.md` (609 lines).
- `genesis-stage2-foundation...genesis-architecture`: Genesis architecture branch is 322 commits behind with no unique ahead commit in that comparison.
- `atlas...orbit`: diverged, 1 commit ahead on Orbit, 304 behind; one added path, `docs/README.md`.
- `aperture` is 450 commits behind Atlas; `aperture-hardening` is 471 behind Atlas; neither is ahead in that comparison.
- `wip/health-freshness` is 52 commits behind Atlas; its WIP commit is in Atlas ancestry, but its original WIP/untested claim and later superseding evidence need tracing.

## Additional historical signals surfaced from branch commit subjects

These are audit leads, not automatically current defects or accepted facts:

### Aperture / Photos / Lumo lineage
- Local-only/cloud removal and gateway behaviour; cloud switch initially local and enabled only after successful request; no cloud call when disabled; provider refusal/error explanation; certificate handling; no temperature sent to provider.
- Performance constraints: do not wait for picture model; 10-second budget for listing readings; trace timeout location; label index in Apple Vision; in-memory library tables and startup priming; query should not wait on external drive.
- Search and answer correctness: named place required in results; place/time grounding; multi-condition request should produce one clear answer; Trip tab only for places.
- UI and architecture: one chat button; menu and page layout; photos naming and routing; tool choice must cover all data sources touched by a question; model cannot answer data questions without required tool use.
- Security/operations: Docker binds inside container only when sandboxed; key entry via stdin; no cloud-era secret/settings migration assumptions.

### Orbit lineage
- Read-only-by-default ingestion, inbox mounted read-only unless explicitly enabled; Pause/Resume/Stop controls; concurrent document readers in sealed children; duplicate-content deduplication.
- Progressive indexing during document reads; question uses available index without waiting for full build; 60k-document performance claim (2.8s initial, 0.1s incremental) needs exact benchmark hardware/dataset and current relevance.
- Health locked until explicitly unlocked and re-authorised each start; Health idle timeout 15 minutes; container limits; local platform key required.
- Renames of Orbit/Atlas and data folders/volumes/Keychain/database names require preservation/no-loss verification.

### WIP Health freshness / legacy Atlas audit
- Explicitly marked WIP/untested Health freshness behaviour: stale reports (>3 months) neutral, show age.
- False code comment claiming undo where no undo existed; later prepared-write and owner-confirmation constraints.
- Review evidence gaps: coverage matrix count reconciliation; screenshots; mutation checks caught hard-coded validation limit; security/deployment inspection and changed-file coverage; exact money decimal handling (no float), currency precision refusal, European numeric/date parsing, Health range endpoint vs actual result, source-line provenance.
- Encryption conversion crash-point testing; old plaintext copy cleanup; backup and key-recovery assumptions; file/path and symlink safety; reader handover cleanup.
- UI regression: CSS cleanup hid every card/tile; screenshot and tests required to catch it.
- Full-answer refusal instead of partial truncation; email no arbitrary 600-character cut; all limits in limits.json and cut-state recorded.
- Finance amount arithmetic exact decimal and round-once semantics; no float conversion; all inputs use shared money parser.

## Required Claude work

1. Read this branch inventory and compare each branch's full unique commit history against the current PR #8 head and base. Do not rely only on branch names or commit subjects.
2. Explain why the PR #8 body says Stages 4–8 are on its branch when the branch compare shows a separate divergent `genesis-stage4-6` branch. Correct the PR body/docs or reconcile the branch pointer; do not silently merge code.
3. Review all 61 paths in the Stage 4–8 branch diff separately from the PR #8 275-path inventory. Record code/test/docs evidence and current acceptance state.
4. Reconcile Stage 3 prep and LLD branches' unique commits and docs against PR #8; retain their review state.
5. Inspect the legacy Aperture/Orbit/WIP histories for product decisions and defects not in the current register; map each relevant finding to the existing or a new stable ID.
6. Identify whether any old WIP or closed PR branch contains changes not merged into the current baseline, especially Health freshness, data migration/rename, security fixes, UI fixes, or performance work.
7. Maintain docs/review-only scope for this audit. No code/test/build/config changes or thread resolution without owner authorisation.

**Important:** Commit pagination is now exhausted for all 12 branches. Reachable commit-entry counts at the capture snapshot: aperture 210; aperture-hardening 189; atlas 660; atlas-low-level-design-review 761; dependabot checkout 204; dependabot setup-node 210; genesis-architecture 761; genesis-stage2-foundation 1,085 (latest branch snapshot after audit commits); genesis-stage3-prep 855; genesis-stage4-6 997; orbit 357; wip/health-freshness 608. Total 6,897 branch-reachable entries, with shared ancestry duplicated. This does **not** mean 6,897 unique commits were read. Full commit-message extraction, unique-SHA reconciliation, and review of commit diffs remain open.
