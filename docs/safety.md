# Safety model

1. Drive check: mounted, writable, not on the internal disk (`drive_problem`).
2. `WriteGuard`: every write is checked to be inside `Aperture/` or the export root; the photo folder is never a write target.
3. Export folder must be on the drive, outside the photo folder and Aperture data.
4. Offline guard: `socket.connect/getaddrinfo/...` refuse non-loopback hosts; HF/transformers offline env is forced. Only `aperture fetch-models` lifts it.
5. Export copies with verification and never overwrites different files.
6. No deletion API exists for originals.
7. Moves (`organize.py`) are the only change to the library: off by default (`allow_moves`), refused while indexing runs, same-volume `os.rename` only, destination inside the photo folder, never overwrite, write-ahead journal in the `moves` table, per-batch undo.
8. **OS-level sandbox (macOS).** `scripts/aperture-sandboxed.sh PHOTO_DIR [EXPORT_DIR] -- aperture ui` runs Aperture under a
   Seatbelt profile (`scripts/aperture-sandbox.sb`): the kernel denies every non-loopback connection and every write to the
   photo folder (unless `ALLOW_MOVES=yes`), even if a native library or dependency ignores the Python-level guard. Prove it
   on your Mac with `scripts/aperture-sandboxed.sh --selftest PHOTO_DIR` (expects three PASS lines). Not used for
   `aperture fetch-models`, which needs the internet once. `sandbox-exec` is deprecated by Apple but still works; this profile
   was written without access to a Mac, so run the self-test before relying on it.
9. **Encryption at rest.** Aperture's index (including face data) is not encrypted by Aperture. Encrypt the external drive:
   Finder > right-click the drive > *Encrypt* (APFS), or erase it as *APFS (Encrypted)* in Disk Utility. Keep FileVault on.
10. **Install-time exposure.** `scripts/install.sh` downloads packages from PyPI. Run it once on a trusted network, then use
    the sandbox for daily use. Hash-pinned requirements are a possible later step.
