# WP3.3: Mail read-only BODY path (synthetic fixtures only)

Scope: architect brief on PR #8 (comment 7069795504), `STAGE-3-EXECUTION-PLAN.md` WP3.3. Code: `src/atlas_core/mail.py`; tests: `tests/test_mail.py`. Evidence class: **CI-verified (Linux), synthetic fixtures only**. **No real mailbox, no Apple Mail store and no owner Mail was opened, read or copied; Mail has not been enabled on the owner's behalf; no attachment is touched.** macOS TCC and the Keychain anchor are not implemented or verified (deterministic fakes in CI, seams retained).

## What it is

```
Mailbox adapter (the platform seam)  --- guard ---> parse (strict, bounded) --> MailIndex (own encrypted file) --> Retriever / SourceStore --> the existing gate
 InMemoryMailbox (synthetic) now;                       only 5 fields taken                                            (policy -> GatedRetrieval -> ContextBuilder -> GatedModel -> verification)
 Apple Mail adapter = a later, owner-enabled package
```

* **Independent source type, existing gate.** The index is a `Retriever` and `SourceStore` for the unchanged `TaskService`; it names no source type in code (constructor argument). A Documents grant never implies Mail (tests with `SourceAccess` over the designation store: documents-only, mail-only, neither, both).
* **Both gates before every adapter call.** The index keeps only a guarded handle on the adapter: every `list` and every `read` first runs `SourceAccess.permitted` (owner grant AND fresh positive OS evidence, checked now); the index cannot be built without an access check. Tests count real adapter calls: nothing enabled, a missing/unknown/stale/future-dated/failing OS provider, consent withdrawn or OS permission lost at `scan:begin` and at `msg:before`, all mean zero listings or reads. A denied scan changes no state either. Revocation purges the index; mail already in local storage is still unretrievable once access ends, even if the purge function has not run.
* **Stored fields are trusted fields; message text is not.** Sender, date and subject are the stored fields of the message record, rendered by the Core as the `headers` part (one passage per line, locator `message_part: headers`, exact span). The body is a separate `body` part (one passage per paragraph, locator `message_part: body`, exact span). Text in a body that looks like `From: ...` is only ever a body citation; claiming it is a header does not resolve (`out_of_range`). The sender and date are never parsed from the message text. These use only the frozen 1.0 `EvidenceRef` and its `message_part` locator; no contract change.
* **Honest about authenticity.** "Stored sender" means the value Mail stored for the message, which a sender controls; the Core cites it as a stored claimed field and makes no claim that it is authenticated (the 1.1 `authenticity: claimed` flag is specification only and not served).
* **Strict, bounded, never repaired.** Only five fields are taken (message id, sender, date, subject, body). Missing or mistyped fields, an unparseable date, a control character (this also refuses a header line smuggled in through a sender or subject), a NUL byte, an oversized field or body, a record for another message, and an invalid identity are explicit failed outcomes with reason codes (`malformed_message`, `corrupt`, `oversized`, `unreadable`), counted in coverage; they are never searchable or cited and block `complete`.
* **Attachments do not exist for the Core.** Anything else an adapter returns (an `attachments` key, extra headers) is ignored and never stored, listed, counted or exposed (tested with a leaky adapter and a fixture that counts any attachment access: zero). There is not even a column for them. The answer discloses `attachments_not_searched` and the deferred `mail_attachment` source through the existing rule. G-O18 is a separate package.
* **Hostile content is data.** Instructions in a body (search everything, reveal secrets, send, delete, grant access to Finance/Health, change policy) change no scope, grant or state: only the granted type is searched, the question reaches the model unchanged, no grant appears or changes, and there is no action path in this module at all.
* **Never stale.** `get()` re-reads the message through the guard and re-hashes the stored text on every resolution: a changed, deleted, newly malformed or access-ended message is unresolvable and is skipped by search until rescanned and re-indexed.
* **Restart-safe and bounded.** Each message's state change commits with its stored fields in one transaction; a scan is one transaction after a durable `running` marker. A six-boundary crash matrix converges to the clean-run index; re-running is idempotent and does not re-read unchanged messages; indexing is sliced, newest first by stored date, and cancellable.
* **Redaction.** Source ids are opaque; coverage carries counts and reason codes only; logs, coverage and the raw (encrypted) index file contain no sender, subject, body or identity (tested with sentinels).

## Supported scope (honest)

Message body and stored headers (sender, date, subject) as text. **Not built:** thread context, recipients/other headers, HTML/MIME parsing, attachment content or metadata (G-O18), the real Apple Mail adapter, disk-pressure pause, and any send/reply/delete/draft action (the Mail path is read-only and has no action surface).

## Known limitations and pending evidence (not claimed)

* No real mailbox or Apple Mail store has been exercised; the real adapter, its real message-identity/versioning, scale and performance are unverified.
* Coverage is produced and tested but not yet carried in the answer envelope (1.1 fields, not served); ranking is lexical term overlap.
* The listing change-marker is adapter-supplied and only an optimisation: correctness never depends on it (every read is re-hashed).
* Mac-pending: TCC/Mail automation permission, the Keychain anchor and store key provider, real-volume behaviour, performance, owner-authorised end-to-end validation (which needs explicit owner enablement).

## Rollback

Delete `mail.py`, `tests/test_mail.py`, this file; revert `documents.py`'s `_blocks` → `paragraph_blocks` rename and the `IndexStore` base class it now shares with the document index (lock, hook, `meta` table, transaction helper; the repo's no-copied-function rule forbids duplicating it) and the layer/allow-list/forbidden-import lines in `test_architecture.py` and `test_tasks.py`. The index is its own file.
