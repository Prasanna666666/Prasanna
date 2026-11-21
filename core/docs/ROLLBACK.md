# Migration and rollback plan

This package is additive and reversible. It does not migrate or move anything.
- **Changed paths:** new directory `core/`; one new CI job `core` in `.github/workflows/ci.yml`. No file under `kit/`, `library/`, `finance/`, `images/`, `atlas/`, `scripts/` or `docs/` (outside `core/docs/`) was changed.
- **Data:** the only data it creates is the new task store file, in a folder the caller chooses, with its own key. No existing database, schema, key, index or user file is read or written.
- **Rollback:** (1) revert the branch/commit (removes `core/` and the CI job); (2) delete the task store file and its key (nothing else depends on them): on a Mac `security delete-generic-password -s atlas-task-key` removes the Keychain item that `provision()` created. No downtime and no data restore are involved.
- **Schema versioning:** `PRAGMA user_version = 1`; a store written by a newer version is refused, not guessed at. A real migration for this store would need its own approved package.
- **If a change to existing stores or keys ever becomes necessary** (for example stored page offsets for citations, Stage 1 G-2): stop and submit a separate migration proposal; this package does not contain one.
