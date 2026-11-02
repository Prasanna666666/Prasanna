# Safety model

1. Drive check: mounted, writable, not on the internal disk (`drive_problem`).
2. `WriteGuard`: every write is checked to be inside `Aperture/` or the export root; the photo folder is never a write target.
3. Export folder must be on the drive, outside the photo folder and Aperture data.
4. Offline guard: `socket.connect/getaddrinfo/...` refuse non-loopback hosts; HF/transformers offline env is forced. Only `aperture fetch-models` lifts it.
5. Export copies with verification and never overwrites different files.
6. No deletion API exists for originals.
