# Safety model

1. Drive check: mounted, writable, not on the internal disk (`drive_problem`).
2. `WriteGuard`: every write is checked to be inside `Aperture/` or the export root; the photo folder is never a write target.
3. Export folder must be on the drive, outside the photo folder and Aperture data.
4. Offline guard: `socket.connect/getaddrinfo/...` refuse non-loopback hosts; HF/transformers offline env is forced. Only `aperture fetch-models` lifts it.
5. Export copies with verification and never overwrites different files.
6. No deletion API exists for originals.
7. Moves (`organize.py`) are the only change to the library: off by default (`allow_moves`), refused while indexing runs, same-volume `os.rename` only, destination inside the photo folder, never overwrite, write-ahead journal in the `moves` table, per-batch undo.
