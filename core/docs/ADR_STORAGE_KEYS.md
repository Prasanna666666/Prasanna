# ADR: storage, encryption and key boundary (Stage 4, G-O02)

Status: **proposed by the developer for architect review and owner acceptance.** It describes what is built (`backup.py`, `storage.py`, `launchagent.py`, `recordstore.py`) and decides nothing that G-O05 reserves to the owner.

## Context
The production host provisions separate Keychain-backed store/index keys from `host.KEY_NAMES`: `task-store`, `designation-store`, `documents-index`, `mail-index`, `edits-store`, `finance-records`, `finance-index`, `health-records`, `health-index`, plus one `{domain}-index` key for each native domain (Calendar, Contacts, Notes and Photos). The model registry's `model-record` key and the designation rollback anchor are additional Keychain items. The client registry (`clients.json`) contains public keys only and is mode 0600. `launchagent.py` only generates a LaunchAgent plist; it does not install or load it. The current app starts the Core as a child through Swift `CoreLauncher` and stops/reaps it on app termination. FileVault and owner-Mac reboot behaviour remain unverified.

## Decisions
1. **Separate stores, separate keys.** A store is opened only by the module that owns it, with the key it was given. No module opens another's file, and none opens a legacy application's database (a test enforces
   this; `backup.py` is the one reader of other stores, and only to snapshot them into a new file).
2. **Backup inventory (current implementation).** `backup.DB_FILES` contains `tasks.db`, `edits.db`, `designation.db`, `finance-records.db` and `health-records.db`. `LIVE_DBS` restores tasks, edits, Finance records and Health records as live stores; designation is restored as read-only history only (decision 4). `PLAIN_FILES` contains `clients.json` and `actions-audit.jsonl`. The document/Mail/native indexes and model folder are derived/reimported and are not backed up. The Core identity key and paired-device list are not backed up; devices pair again after restore.
3. **A backup is a folder with a manifest.** Per-file size and SHA-256, per-table row counts, and an HMAC over the manifest made with a key derived (scrypt) from an owner-held recovery passphrase. The store keys travel
   in `keys.enc`, wrapped with AES-256-GCM under the same derivation. Verification without the passphrase detects corruption; with it, tampering and unreadable databases.
4. **Grants are never restored.** Restoring a designation snapshot is a rollback, which the external anchor exists to refuse; a revoked permission must not come back. The new Core starts with an empty, freshly
   anchored designation store: every source is off until the owner turns it on again (the one Get Started step). Tasks come back, and their answers are withheld until a current grant covers their sources.
5. **No silent deletion or overwrite.** Backups are written to a temporary folder and renamed when complete; a restore goes only into a place that does not exist or is empty and removes only what it created if it
   fails. Disk pressure may pause derived work and warn; it may never delete an original, a task, a grant or a backup (`storage.NEVER`).
6. **Keychain availability.** Before the owner signs in after a restart the Keychain gives no keys; the Core then exits with its own code (6) and the app says "Mac needs owner sign-in". No key is kept anywhere a
   headless boot could read it, and auto-login stays off.

## Not decided here (owner, G-O05)
Where backups go (external volume, another Mac, a cloud store the owner controls), how often, whether the recovery passphrase is a memorised phrase or printed, and how the owner is reminded. The mechanism does not
depend on the answer. Until G-O05 is decided and a restore drill has been run on the target Mac, **no release may rely on backup**.

## Consequences and limits
Backup/verify/drill/restore are implemented as maintenance CLI operations and have tests; there is still no in-app backup/restore control or scheduled backup. The recovery-to-Keychain provisioning seam is injectable; its complete owner-Mac recovery flow and restore drill remain unverified. Real FileVault and power-loss behaviour remain unverified. The current Core lifecycle is child-process-based, not LaunchAgent-installed.
