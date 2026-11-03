# Safety model

1. Drive check: mounted, writable, not on the internal disk (`drive_problem`).
2. `WriteGuard`: every write is checked to be inside `Aperture/` or the export root; the photo folder is never a write target.
3. Export folder must be on the drive, outside the photo folder and Aperture data.
4. Offline guard: `socket.connect/getaddrinfo/...` refuse non-loopback hosts; HF/transformers offline env is forced. Only `aperture fetch-models` lifts it, and only when `APERTURE_NEVER_ONLINE` is not set (the container and sandbox set it).
5. Export copies with verification and never overwrites different files.
6. No deletion API exists for originals.
7. Moves (`organize.py`) are the only change to the library: off by default (`allow_moves`), refused while indexing runs, same-volume `os.rename` only, destination inside the photo folder, never overwrite, write-ahead journal in the `moves` table, per-batch undo.
8. **OS-level sandbox (macOS).** `scripts/aperture-sandboxed.sh PHOTO_DIR [EXPORT_DIR] -- aperture ui` runs Aperture under a
   Seatbelt profile (`scripts/aperture-sandbox.sb`): the kernel denies every non-loopback connection and every write to the
   photo folder (unless `ALLOW_MOVES=yes`), even if a native library or dependency ignores the Python-level guard. Prove it
   on your Mac with `scripts/aperture-sandboxed.sh --selftest PHOTO_DIR` (expects three PASS lines). The wrapper also sets
   `APERTURE_NEVER_ONLINE=1`, which refuses to enable the network at all (`aperture fetch-models` is refused inside it). `sandbox-exec` is deprecated by Apple but still works; this profile
   was written without access to a Mac, so run the self-test before relying on it.
9. **Encryption at rest.** Aperture's index (dates, GPS, places, faces, text, labels, full metadata), thumbnails and previews are
   private data. Keep them in the encrypted vault: `scripts/aperture-vault.sh create`, then `open`, then run with
   `APERTURE_DRIVE=/Volumes/ApertureVault`. The vault is an AES-256 APFS image; its password is generated and kept only in your
   login Keychain (never printed, never in a file or in this repository). `close` makes everything unreadable. Aperture also sets
   folders to owner-only (0700) and the index and settings to 0600. Without the vault, at least use an encrypted APFS drive
   (Disk Utility, *APFS (Encrypted)*) and keep FileVault on. None of this data is ever in git, and the assistant that wrote the
   code has no access to your Mac or drive.
10. **Install-time exposure.** `scripts/install.sh` downloads packages from PyPI. Run it once on a trusted network, then use
    the sandbox for daily use. Hash-pinned requirements are a possible later step.
11. **Secure by default.** `ui`, `app`, `scan`, `ask`, `caption`, `export-job`, `install-service` and `install-launcher` refuse to run unless
    `APERTURE_SANDBOXED=1` (set by `scripts/aperture-sandboxed.sh` and by the Docker image). `aperture secure-ui` is the one-command way;
    `aperture --insecure <command>` is the deliberate override. Existing background services started before this change keep running the
    old, unsandboxed code until you stop them.
