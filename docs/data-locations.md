# Where personal data lives on disk

Built from the code (file and line named). "Verified" means a test or a run in this review shows it; "Code only" means I read it but did not run it on a Mac. Docker volumes and the Mac's own folders were **not inspected**.

| Location | What is in it | Encrypted? | Evidence |
|---|---|---|---|
| `$ATLAS_HOME/finance.db` (+ `-wal`, `-shm`) | all Finance data | **Yes** with a key (SQLCipher encrypts the WAL too); refused without a key when `ATLAS_REQUIRE_ENCRYPTION=1` (Docker sets it) | Verified: `finance/tests/test_secure_by_default.py`, `kit/tests/test_db_safety.py` |
| `$ATLAS_HOME/library.db` | Documents, mail text, facts | **Yes** (same `kit.db.connect`) | Verified for the mechanism; the Docker deployment itself not run here |
| Images index (`aperture.db`) | picture index, full-text | **Yes**; a plain index is converted once and the plain file overwritten and deleted | Verified: `images/tests/test_engine.py`, `kit/tests/test_db_crash_points.py` |
| `$ATLAS_HOME/backups/before-upgrade-*.db` (kit and the Images index) and `backups/finance-<date>.db` (Finance) | full copies of a database | **Yes**: made through `connect`, which applies the key | Code only: `kit/db.py:copy_before_upgrade`, `finance/backup.py:daily` |
| `<name>.unencrypted` beside a database | the plain copy of a database from a conversion | **No.** New conversions overwrite and delete it (`ATLAS_KEEP_PLAINTEXT=1` keeps it). A leftover with the same rows is removed on the next start. **A copy that differs is only removed by `python -m kit.cleanup`, when you type yes for that file** | Verified: `kit/tests/test_db_safety.py` |
| `ATLAS_PARSED` (Docker `/parsed`) | one JSON per read file, **with the whole extracted text** | **No** | Code only: `library/parser.py`, `store.ingest_dir` deletes each file after it is stored. Plain between the read and the ingest (O-16) |
| `ATLAS_INBOX/mail`, `ATLAS_INBOX/notes` | mail exported as `.eml`, Apple Notes export | **No** (the owner's own files, copied) | Code only: `library/cli.py`, `finance/cli.py` |
| The owner's original files and folders | everything Documents reads | **No** (read-only; Atlas never changes them except through the confirmation window) | by design |
| `$ATLAS_HOME/atlas.log` | event names, counts and error types only, "never a payment, a file's text, a question or an answer" | No | Code only: `kit/log.py` (rule in its docstring; one test, `atlas/tests/test_assistant_safety.py`, checks a tool result is not logged) |
| `$ATLAS_HOME/apps.user.json` | names the owner gave to categories | No | Code only: `library/apps.py` |
| Atlas itself | nothing: it holds no data | n/a | `docs/architecture.md` |
| Ollama's model files and any prompts Ollama keeps | the model; Ollama's own logs and history | Owner's Ollama, outside Atlas | **NOT VERIFIED** |
| macOS (Time Machine, Spotlight, swap) | copies of any of the above | FileVault only | **NOT VERIFIED** |

**Secure deletion.** Overwriting a file and deleting it cannot promise that an SSD or APFS has erased the old blocks (wear levelling, snapshots). Full-disk encryption (FileVault) is what protects them. The code does not claim physical erasure.

**What this does not show.** It is not a claim that "everything is encrypted": databases and their backups are; the parser hand-over, the inbox exports and the owner's originals are not.
