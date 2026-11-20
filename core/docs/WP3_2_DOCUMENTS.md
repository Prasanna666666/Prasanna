# WP3.2: the document-only vertical path

Scope: `STAGE-3-EXECUTION-PLAN.md` WP3.2 and the architect brief on PR #8 (comment 7052484018). Code: `src/atlas_core/documents.py`; tests: `tests/test_documents.py` (synthetic files only). Evidence class: **CI-verified (Linux)**. Nothing here is Mac-verified.

## What it is

```
designated folder -> Scanner (descriptor-relative, no-follow, size cap) -> Extractor (bounded, stdlib) -> DocumentIndex (own encrypted SQLite file)
                                                                                                     |-- search()  = Retriever
                                                                                                     `-- get()     = SourceStore (re-verifies the bytes on disk)
                                                  existing path unchanged: policy -> GatedRetrieval -> ContextBuilder -> GatedModel -> verification
```

* **No parallel policy.** The index is only a `Retriever` and a `SourceStore` handed to the existing `TaskService`; the grant, the trusted per-item label (`StoredSource.sensitivity`, set by the index, never by file content) and the grant-bound checkpoint all apply unchanged. The source type is a constructor argument, not a literal in code (`test_architecture.py` rule).
* **Exact evidence.** One passage = one block; `locator = {"kind": "block", "block": n}`, `span` = the block's exact character offsets, `version_sha256` = hash of the indexed text. This uses only the frozen 1.0 `EvidenceRef`; no contract change was needed.
* **Never stale.** `get()` re-hashes the file's bytes on every resolution. A file that changed, vanished, became a link or is unreadable is unresolvable, so old citations stop resolving (`stale` / `unresolvable`) and `search()` skips it until it is rescanned and re-indexed.
* **Race-safe confinement.** Every directory and file is opened relative to the already-open parent descriptor with no-follow flags (`O_DIRECTORY|O_NOFOLLOW` for folders, `O_NOFOLLOW|O_NONBLOCK` plus a regular-file check for files), and the walk lists through the directory descriptor. A link planted on any component, even between a check and the open, makes the open fail instead of leading outside the root. A platform without `dir_fd`/`O_NOFOLLOW`/`O_DIRECTORY` support refuses to construct the scanner (fail closed). A test seam (`Scanner.seam`) swaps the tree at exact moments to prove this deterministically.
* **Explicit outcomes** (reason codes only, never content or paths): `unsupported_format`, `corrupt` (invalid UTF-8, NUL byte, nothing extractable), `oversized` (bytes or block count: refused, not truncated), `symlink_refused`, `unreadable_directory` and `unreadable_entry` (a folder or entry that cannot be opened, listed or examined is recorded, never dropped), `unsupported_entry` (pipe/device, never opened) and `unreadable` (a read refused or failed). All are counted in coverage and block `complete`.
* **Ordering.** Newest first by file modification time. A date inside a document (`created:` front matter in Markdown) is stored separately and never replaces it. A file with no usable time is ordered after all timed files (then by path), counted as `missing_timestamps`.
* **Coverage** (`coverage()`): `total, searched, pending, unsupported, failed, missing_timestamps, reasons, scan_complete, paused, complete`. `complete` is true only if a scan finished (and was not cut off by the file limit), nothing is pending, unsupported or failed, and nothing is paused.
* **Restart-safe.** Each document's change commits with its text in one transaction; a scan commits as one transaction after a durable `running` marker. Crash tests at six boundaries converge to the same index as a clean run, with no duplicates; re-running is idempotent and does not reprocess unchanged files.
* **Bounded and non-starving.** `run(max_docs)` processes a bounded slice, newest first, and returns; cancellation (`index.cancelled`) and low disk (`MIN_FREE_BYTES`) pause with a reason and lose nothing.
* **No evidence, no model.** If retrieval yields no usable passage (no match, or every item excluded by sensitivity) the service does not call the model: it records a fixed plain statement ("No usable source was found for this question, so no answer was produced.") with no citation, status `unverified`, limitation `partial_work` (plus `sensitive_items_excluded` when applicable), and the task ends `partially_completed`. No excluded content appears in it. This is a change in `service.py`/`answer.py` (not the contract: only existing enum values are used).
* **Revocation.** The gate stops searching and reusing; `purge()` additionally deletes all indexed text and status, so a later grant starts from an empty index. The index file is encrypted (SQLCipher, key supplied by the caller; the Keychain provider for real data is WP3.6).

## Supported formats (audited)

Plain UTF-8 text (`.txt`) and Markdown (`.md`), stdlib only. **PDF, Office, HTML, images/OCR and encrypted documents are NOT supported in this package**: they are reported as `unsupported_format`, never skipped or guessed. Adding one needs a separately reviewed parser with OS-level isolation (a Mac / later-package item).

## Legacy reuse decision (audited, nothing reused)

| Candidate | Finding | Decision |
|---|---|---|
| `kit/src/kit/rag.py` | own SQLite schema and chunker with no exact offsets or version hash, driven by the legacy source objects | Not reused: cannot give exact locators or the fail-closed version check |
| `library/src/library/readers.py` | PDF/OCR/mail readers that shell out (`subprocess`, tesseract, poppler), heavy third-party engines, no parser isolation | Not reused: fails the parser-isolation and bounded-dependency checks |
| `kit/src/kit/extract.py` | model-driven financial fact extraction | Not applicable (Finance is out of scope; the model must not extract) |

## Known limitations and pending evidence

* The coverage record is produced and tested, but is **not yet carried in the answer envelope**: that belongs with the coverage/limitation fields of API 1.1 (specification only, not served). No contract change was made.
* The retrieval is lexical term overlap (tier 1, model-free). Ranking quality and larger-scale performance are not measured here.
* Source designation (how the owner chooses the folder) and the consent flow are later packages; the index takes its root and label from its constructor.
* Mac-pending: FileVault/TCC folder access, real folder volumes, real power loss, Keychain key provider, performance on the target Mac.

## Rollback

Revert the `service.py`/`answer.py` no-evidence branch; delete `core/src/atlas_core/documents.py`, `core/tests/test_documents.py`, this file, and revert the one-line additions to `test_architecture.py` (layer entry) and `test_tasks.py` (store allow-list). The index is a separate file; deleting it loses nothing else.
