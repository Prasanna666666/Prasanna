# Security and deployment review: what was inspected, what was not

Only what was actually read or run is claimed. **Nothing here was run on a Mac or in Docker.**

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

## Turning on the sealed hand-over (O-16; off by default, not yet run in Docker)

1. Make a key pair once: `python3 -m library.seal` prints the private key, then the public key (needs `pip install cryptography` and this repository's `library` folder on the path, or run it inside the app image).
2. Keep the private key in the macOS Keychain; never in a file or in git.
3. Start with the public key given to the parser and the private key to the app: `LIBRARY_HANDOVER_PUBLIC_KEY=<public> LIBRARY_HANDOVER_PRIVATE_KEY=<private> ./up.sh` (the compose file passes each only to its own container; a test checks this). The images must be rebuilt once, because both now install `cryptography`.
4. Press Read new files, then look in the shared volume: it must hold only `.sealed` files, no `.json`. A document that was read must still appear in Documents.
5. If the app has no key or the wrong one, sealed files stay where they are (shown as unopened); nothing is deleted.
This has not been run here: the images were not built or started. Until it is, the plain hand-over (mode 0600, removed after ingestion) is what runs.

## Known weak points, stated

- The test that checks `up.sh` is a source-string test; it does not run the script.
- Disk-full and interrupted-startup recovery are untested.
- A named Docker volume lives inside Docker Desktop's disk image on the Mac; FileVault is the only protection for it at rest.
