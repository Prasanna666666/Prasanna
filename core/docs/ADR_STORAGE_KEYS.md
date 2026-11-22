# ADR: storage, encryption and key boundary (Stage 4, G-O02)

Status: **proposed by the developer for architect review and owner acceptance.** It describes what is built (`backup.py`, `storage.py`, `launchagent.py`, `recordstore.py`) and decides nothing that G-O05 reserves to the owner.

## Context
The Core keeps its own state in SQLite files, each encrypted with SQLCipher under its own 256-bit key, one file and one key per concern: tasks, designation (grants and audit chain), the document index, the Mail
index, one index per Stage 5 domain, the owner's own edits and the client registry (public keys only, a JSON file, mode 0600). Keys live in the Keychain on the Mac (items `atlas-task-store`,
`atlas-designation-store`, `atlas-documents-index`, `atlas-mail-index`, `atlas-model-record`, plus the designation anchor). FileVault stays on; the Core starts as a user LaunchAgent after the owner signs in.

## Decisions
1. **Separate stores, separate keys.** A store is opened only by the module that owns it, with the key it was given. No module opens another's file, and none opens a legacy application's database (a test enforces
   this; `backup.py` is the one reader of other stores, and only to snapshot them into a new file).
2. **Derived versus non-derivable.** The document, Mail and domain indexes are derived from the owner's own sources and are rebuilt by the progressive indexer; they are NOT backed up. Tasks, the client registry and
   the owner's own edits are not derivable and ARE backed up. The designation store is backed up as read-only history only (decision 4).
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
Nothing yet calls `create_backup` from the app, a schedule or an API route; there is no owner-facing restore flow; the Keychain provisioning seam (`provision_keys`) has a fake only. Real FileVault, reboot and
Keychain behaviour are unverified. The Core makes no promise of access after a reboot until the owner signs in.
