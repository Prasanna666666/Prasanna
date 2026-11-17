# Security and deployment review: what was inspected, what was not

Only what was actually read or run is claimed. **Nothing here was run on a Mac. The repository's own Dockerfiles, compose files and `./up.sh` were not run.** The one exception is the sealed hand-over (O-16, below), which the author exercised in Docker with equivalent images; that is author-run evidence, not a check of the real deployment.

## Read in the Docker and Compose files (static)

| Check | Result | Where |
|---|---|---|
| Published ports bound to this computer only | **Yes**: `127.0.0.1:8000`, `:8501`, `:8502` | `atlas/docker-compose.yml:17`, `finance/docker-compose.yml:43`, `library/docker-compose.yml:58` |
| Hardened containers | `read_only: true`, `cap_drop: [ALL]`, `no-new-privileges` on Atlas, Finance, Library | each compose file, top of the shared block |
| Parser has no network | `network_mode: none` | `library/docker-compose.yml:22`, `docker-compose.pictures.yml:28` |
| Internal networks for the app pairs | `private: {internal: true}` | `finance/docker-compose.yml:64`, `library/docker-compose.yml:71` |
| Containers run as a non-root user | uid 10001 | `library/Dockerfile:6,24,35,51` (Finance and Atlas Dockerfiles **not read**) |
| Hand-over volume shared by parser (writes) and app (reads, deletes) | named volume `library-parsed`, same uid | `library/docker-compose.yml:30,49`; files now mode 0600 |
| Atlas signs its calls to the apps | `PLATFORM_KEY` from the Keychain | `atlas/docker-compose.yml:20` |

## Not inspected, or inspected only by tests with fakes

Token generation, expiry and reuse (`kit/sign.py`, Atlas token fetch); CSRF and Origin/Host checks beyond the Atlas tests; request size limits and malformed JSON in every endpoint; path traversal and symlink handling beyond the tests that exist; file-serving; Docker image and dependency vulnerabilities (`pip-audit` runs in CI and passed; images were not scanned); the database key's creation, storage in the Keychain and rotation (`scripts/platform-key.sh`, `up.sh`: read only in part); backup and restore scripts; autostart install and removal; Apple Mail integration; Apple Vision sandbox; Ollama configuration; disk-full, Docker-unavailable, missing-model and interrupted-startup behaviour (**no test exists**); first install, repeat install, upgrade and rollback of the Docker deployment.

## Run

- `scripts/update-code.sh`: clean, dirty, ahead, behind, diverged, no local branch, other branch (`atlas/tests/test_update_script.py`, 7 scenarios, real git repositories).
- `up.sh`, `down.sh`, `scripts/install-autostart.sh`: **not run**; a test only checks that `up.sh` does not rebuild when nothing changed (`library/tests/test_docker_files.py`, string checks, which is weak).

## Turning on the sealed hand-over (O-16; off by default; exercised only with equivalent images, not the repository deployment)

1. Make a key pair once: `python3 -m library.seal` prints the private key, then the public key (needs `pip install cryptography` and this repository's `library` folder on the path, or run it inside the app image).
2. Keep the private key in the macOS Keychain; never in a file or in git.
3. Start with the public key given to the parser and the private key to the app: `LIBRARY_HANDOVER_PUBLIC_KEY=<public> LIBRARY_HANDOVER_PRIVATE_KEY=<private> ./up.sh` (the compose file passes each only to its own container; a test checks this). The images must be rebuilt once, because both now install `cryptography`.
4. Press Read new files, then look in the shared volume: every document payload must be a `.sealed` file and there must be no `<sha256>.json` (the completion marks in `.done` and the reader's own notes such as `.failed.json`, `.progress`, `.found` are not payloads and are expected). A document that was read must still appear in Documents.
5. If the app has no key, a malformed key (not hexadecimal, not 32 bytes, empty, a key file that is missing or garbage) or the wrong key, sealed files and their completion marks stay where they are and are counted as unopened; nothing is deleted. Fix the key and the same files open. A disk or volume error while reading a result (`OSError`) also deletes nothing: it is counted as unreadable and tried again next time. A file whose name is not a sha256 (one the reader could not have written) is reported when it is not a usable result but is never deleted. Only a file named by a sha256 that is not a valid sealed file at all (too short, or with an invalid low-order ephemeral key) is rejected, on purpose, and read again next round. In `be059e4` a malformed key did delete them; fixed in `afb1b66`.
**What was run (author-run, in a Docker daemon in the author's session, not on the owner's Mac):** images equivalent to the repository's `parser` and `app` stages were built from `python:3.12-slim` (same user 10001, same `pip install` of the parsing libraries and `cryptography`, same library code; **not** the repository Dockerfile, because its `apt-get` step could not reach the network here, so no Tesseract, no torch, no sqlcipher, no `images` package). The real `library-parser --once` binary ran in a container with the compose file's hardening (`--network none --read-only --cap-drop ALL --security-opt no-new-privileges --tmpfs /tmp -u 10001`) and only the PUBLIC key, on a text file containing a name and a lab value. Result: the shared volume held one `<sha256>.sealed` file (mode 0600), no `<sha256>.json`, and the text searched for in every file of the volume was found nowhere. The parser image has `cryptography` and has no `kit` (`import kit` fails there). An app-like container with the PRIVATE key then ran `store.ingest_dir` on the volume: with no key, a malformed key (`not-a-hex-key`), a key one byte too long and a wrong valid key the `.sealed` file and its `.done` mark stayed and nothing was stored; with the correct key the document was stored and the `.sealed` file removed. **Found by this run:** `store.ingest_dir` matched the parser's own note `.failed.json` with `*.json`, counted it as a rejected document, showed it to the person as an unreadable file and deleted it (a bug that predates sealing); fixed in the next commit (`_handover_files`), with a test.
**Not run:** the repository's Dockerfile and compose file as written, `./up.sh`, the real Documents server, Tesseract or Apple OCR, the Keychain key flow, the owner's Mac. Until those are run on the Mac, the plain hand-over (mode 0600, removed after ingestion) is what runs by default.

- **Volume isolation is an operational assumption.** The app does not check that a result in `library-parsed` was written by the reader (a completion mark proves nothing once a result has been ingested); it relies on that volume being the reader's own and nothing else writing to it. A recovery container or a manual copy into it would be trusted as reader output.

## Known weak points, stated

- The test that checks `up.sh` is a source-string test; it does not run the script.
- Disk-full and interrupted-startup recovery are untested.
- A named Docker volume lives inside Docker Desktop's disk image on the Mac; FileVault is the only protection for it at rest.

**Reviewer's wording for the Docker status, adopted:** "The sealed hand-over was exercised by the author using equivalent parser and app images. The repository's actual Dockerfile, Compose deployment and ./up.sh were not run. This is author-run evidence, not independent verification or validation of the actual deployment."
