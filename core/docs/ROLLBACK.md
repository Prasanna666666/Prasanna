# Historical Stage 2 package rollback note

**Historical scope notice:** This describes the initial Stage 2 `core/`-only package snapshot. It is not the current PR #8 rollback procedure and must not be used to roll back the present branch or live user data. The current branch also changes `app/`, `ios/`, `kit/`, `scripts/`, workflows and multiple Core stores/keys; use verified backups and the signed updater's own rollback semantics where applicable. No complete owner-data rollback/restore run has been accepted.

At the original Stage 2 package snapshot, the Core foundation was additive and did not migrate existing stores. Later stages added multiple stores, data imports, app/iOS clients, device state, backups and update/rollback functionality.
- **Changed paths at that snapshot:** new directory `core/` and one CI job. This is not the current PR #8 changed-path inventory.
- **Data at that snapshot:** a new task store only. Current Stage 4–8 code creates and uses additional stores, keys, imported records, action audit and device state; consult `ADR_STORAGE_KEYS.md`, `STAGES_4_TO_8.md` and the current acceptance records.
- **Rollback at that snapshot:** revert the package commit and remove its isolated task store/key. This is not a safe or complete rollback instruction for current PR #8; do not delete current Keychain items or data stores based on this historical note.
- **Schema versioning:** `PRAGMA user_version = 1`; a store written by a newer version is refused, not guessed at. A real migration for this store would need its own approved package.
- **If a change to existing stores or keys ever becomes necessary** (for example stored page offsets for citations, Stage 1 G-2): stop and submit a separate migration proposal; this package does not contain one.

- **Stage 3 additions:** `core/client/`, `core/evals/`, `core/bench/ingest.py` and the modules listed in `STAGE3_HANDOVER.md` live under `core/` only; reverting the commits removes them. The one behaviour change to existing Core data handling is that a finished task's checkpoint no longer keeps passage text, draft or quotes; there is nothing to restore.
