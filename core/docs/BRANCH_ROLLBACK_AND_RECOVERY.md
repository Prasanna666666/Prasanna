# Branch-wide rollback and recovery boundaries

**Status:** implementation inventory and operator warning only; **not an approved disaster-recovery runbook**. PR #8 contains application, Core, iOS, shared-kit, scripts, workflows, documentation, storage and update changes. Reverting Git commits is not a safe substitute for restoring data or device state. No complete owner-Mac restore/recovery drill has been accepted. Do not claim this branch is rollback-ready for production.

## 1. Separate the rollback domains

| Domain | Current mechanism/evidence | What it does not establish |
|---|---|---|
| Source code | Git history and PR #8 commits | Does not restore user databases, Keychain items, app installs, device state or queued operations |
| Installed Mac app | Signed updater can install a version and return to its previous installed version when configured; see `updater.py`, `UPDATER.md` and `ADR_STORAGE_KEYS.md` | Does not roll back Core databases, Keychain keys, connector credentials, iOS state or external side effects |
| Core persistent data | Backup/verify/drill/restore CLI; see `backup.py`, `backup.md` and `ADR_STORAGE_KEYS.md` | Not an in-app or scheduled backup; not an accepted owner-Mac recovery procedure |
| Keychain | Per-store keys, model-record key, designation anchor, app identity and connector credentials are Keychain-backed | Not all items are part of the backup inventory; owner-Mac access-control, FileVault and recovery behaviour remain unverified |
| Derived indexes and models | Documents/Mail/native indexes are rebuilt from designated sources; model files are installed separately | Rebuild requires the source/model to remain available and permissions to be re-established |
| Paired devices | Device directory and iOS client state are separate from the Core DB backup | Pairing/device state and iOS offline queues are not restored by the Core backup; remote-phone work remains blocked on open defects |
| External services | Connector actions and other outbound effects are mediated by the Action Gateway | A Git revert or database restore cannot unsend a message, reverse an external payment, or guarantee a vendor's compensation semantics |

## 2. Core backup inventory

The current backup implementation records:

- Database files: `tasks.db`, `edits.db`, `designation.db`, `finance-records.db`, `health-records.db`.
- Plain files: `clients.json` (public client keys only) and `actions-audit.jsonl` (content-free action audit chain).
- Encrypted recovery material: the backup manifest and `keys.enc` wrapping the store keys under the owner recovery passphrase, as described in `ADR_STORAGE_KEYS.md`.

The designation snapshot is not restored as active grants. Restore starts with a fresh designation store/anchor so the owner must explicitly re-enable sources. Tasks may be restored, but their answers remain withheld until current grants cover their sources. Documents, Mail and native indexes are derived and must be rebuilt; model files are installed separately. Device directory, app private identity, the separate model-record Keychain item and connector secrets are not part of the listed database/plain-file/key-bundle inventory. The model folder is re-imported from the signed manifest; the model-record key/metadata may need reinitialisation. The designation rollback anchor is also re-created rather than restored as authority.

**Important:** verify the exact current `backup.DB_FILES`, `LIVE_DBS` and `PLAIN_FILES` constants before any recovery. The table above is a documentation snapshot, not a substitute for checking the implementation at the recovery commit.

## 3. Safe operating principles

1. Stop the app and Core before copying or restoring Core state. Do not run two Core processes against one data directory; the Core holds an OS data-directory lock.
2. Preserve the original data directory and Keychain state. Restore only to a new or empty target accepted by the backup implementation; never overwrite a live store in place.
3. Verify the backup and recovery passphrase before relying on it. If verification fails, stop; do not guess, partially restore or delete the source backup.
4. Do not restore designation grants as authority. Re-enrol/re-authorise and re-enable each source deliberately after recovery.
5. Rebuild derived indexes from the owner's designated sources only after re-establishing OS permissions and grants.
6. Reinstall the signed app/model independently. Validate app identity and Keychain access; do not assume restoring Core DB files restores the app's private identity, model-record Keychain item, designation anchor or connector credentials.
7. Re-pair devices and inspect their offline queues only after the remote-device defects have been fixed and independently reviewed.
8. Reconcile external side effects manually with the relevant service. A local rollback is not a compensating action.

## 4. Known gaps and release gates

- No end-to-end restore drill has been performed on the owner's Mac.
- No complete backup policy/destination/retention decision has been accepted (G-O05).
- No in-app or scheduled backup/restore control exists; maintenance CLI is the current interface.
- Owner Keychain prompts/access controls, FileVault reboot behaviour and power-loss recovery are unverified.
- The app's private identity, connector secrets and paired-device state are not in the Core backup inventory; the recovery/re-enrolment path must be exercised and accepted.
- iOS offline queue, relay, pairing partial-failure and paired-device data-scope findings remain developer/security blockers (see `OWNER_ACCEPTANCE_CHECKLIST.md`).
- External sends, spending and physical-security actions cannot be rolled back by restoring local data.

## 5. Required acceptance before release

A release-grade recovery plan requires: an architect-reviewed inventory of every persistent state domain; an owner-approved backup destination and retention policy; a verified backup created from a stopped Core; a restore into a clean target Mac or equivalent test environment; proof that grants remain off; successful app/Core identity recovery, source re-designation, index rebuild, device re-pairing and audit continuity checks; and documented treatment of connector/external side effects. The owner and architect must accept the observed drill. Until then, backup and restore are implemented mechanisms, not a proven recovery guarantee.

## 6. Historical rollback notes

`ROLLBACK.md` remains the historical Stage 2 package-only rollback note. It is not a current branch-wide procedure. `STAGE3_HANDOVER.md` records a historical Stage 3 code rollback summary and must not be read as a complete user-data rollback instruction.
