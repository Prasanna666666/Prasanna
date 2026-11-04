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
9. **Private storage.** With Docker (`docker-compose.aperture.yml`) everything Aperture learns about your photos lives in the named volume
   `aperture-data`, inside Docker's own disk image: no folder on the Mac, so no program or assistant on the Mac can browse it. Move an
   existing index in with `scripts/aperture-docker-migrate.sh`. `.claude/settings.json` additionally denies the coding assistant
   any read of `/Volumes`, the vault and docker cp/exec/volume/run commands. Without Docker, use the encrypted vault below.
   **Encryption at rest.** Aperture's index (dates, GPS, places, faces, text, labels, full metadata), thumbnails and previews are
   private data. Keep them in the encrypted vault: `scripts/aperture-vault.sh create`, then `open`, then run with
   `APERTURE_DRIVE=/Volumes/ApertureVault`. The vault is an AES-256 APFS image; its password is generated and kept only in your
   login Keychain (never printed, never in a file or in this repository). `close` makes everything unreadable. Aperture also sets
   folders to owner-only (0700) and the index and settings to 0600. Without the vault, at least use an encrypted APFS drive
   (Disk Utility, *APFS (Encrypted)*) and keep FileVault on. None of this data is ever in git, and the assistant that wrote the
   code has no access to your Mac or drive.
10. **Install-time exposure.** `scripts/install.sh` downloads packages from PyPI. Run it once on a trusted network, then use
    the sandbox for daily use. Hash-pinned requirements are a possible later step.
11. **Secure by default.** `ui`, `app`, `scan`, `ask`, `caption` and `export-job` refuse to run unless
    `APERTURE_SANDBOXED=1` (set by `scripts/aperture-sandboxed.sh` and by the Docker image). `aperture secure-ui` is the one-command way;
    `aperture --insecure <command>` is the deliberate override. Existing background services started before this change keep running the
    old, unsandboxed code until you stop them.
12. **Optional cloud understanding (off by default).** `aperture cloud enable` lets a cloud model read the *words you type*, nothing else.
    - **What leaves the Mac:** the question, with every person and place name from your library replaced by a placeholder (`<PERSON_1>`,
      `<PLACE_1>`) on your Mac before it is sent, whether photos are on screen (yes or no), and today's date. Never photos, faces, places, dates in
      your library, labels, counts or results. The placeholders in the answer are mapped back locally.
    - **Who talks to the cloud:** only the *gateway*, a separate program that has no access to your library, runs in its own Seatbelt profile
      (`scripts/aperture-gateway.sb`: no reading of `/Volumes` or personal folders) and may reach only the provider's host
      (`APERTURE_TRUSTED_HOSTS`). The app itself stays air-gapped and talks to the gateway over loopback.
    - **The key** lives in the macOS Keychain (never in a file, an argument or this repository) and is handed to the gateway through its environment.
    - **Limits:** a monthly spending cap (default $5; the prices are placeholders, set your provider's in the settings), a strict check of every plan
      the provider returns (only known tools and arguments are accepted), and automatic fallback to the local model on any problem.
    - **Off:** `aperture cloud off` (and `--forget-key` to delete the key).
