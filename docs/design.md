# Design

The longer decision log is `docs/decisions.md`; the layer map is `docs/architecture.md`. This page is the review-friendly summary, with the data flows and the safety design in one place.

## Layers

```
kit  (imports nothing)
 ├── images   (kit)
 ├── finance  (kit)
 ├── library  (kit, images)      "Documents": reader, store, judging, health, travel, pictures
 └── atlas    (kit)              front door: no data, talks to the apps over HTTP only
design/   shared CSS + JS, copied into each app by scripts/sync-design.sh
```

`kit/tests/test_architecture.py` fails on a wrong import, a copied function body, a function over 50 lines, or a "kind word" in code.

## Runtime

```
Browser ── atlas.localhost:8000 ── Atlas ──HTTP──> Finance :8501   (own DB, own container)
                                     │      └────> Documents :8502 (own DB, parser container)
                                     └──HTTP──> Ollama on the Mac (host.docker.internal:11434)
```

Each app signs its calls (`kit.sign`), checks Host and Origin, and only Atlas's own page can start an Update.

## Reading a file (Documents)

1. **Read**: extract text (PDF, Office, images with OCR, mail). Kept whole.
2. **Sort**: the model gives kind, apps, title, facts. Code checks every amount, date, party and entity against the whole text (`kit.extract`); what the document does not say is dropped, never guessed.
3. **Group**: related files are grouped into cases.

A document records which limits cut it (`meta.limits_hit`) and under which version of `limits.json`; changing the limits finds and re-reads those documents.

## Money

Stored as integer minor units. `kit.money.to_minor` reads a number or text as the decimal it was written as and rounds once, half away from zero (1.005 → 101). Statements are proven per month against the raw ledger before any report is given.

## The assistant and its tools

- The model **chooses** tools (schema-constrained) and **writes** the answer; every figure in the answer must appear in a tool result (`kit.audit.unproven_figures`), otherwise the answer is refused.
- Tool results are data. The system prompt says so, but nothing relies on that: permissions are enforced in code.
- Every Finance tool is classified (`finance/toolrun.py`): READ_ONLY, ROUTINE_WRITES, DELETES, CONSEQUENTIAL. A test fails for an unclassified tool.
  - **CONSEQUENTIAL** (eleven tools that change money records or overwrite a note or person) and every **DELETE** (except `delete_transaction`, which is never offered) are only *prepared*: run for real inside a transaction that is rolled back (so errors return at once), then kept in `assistant_changes` as `waiting`.
  - The owner's **own next message**, passed on by Atlas, confirms it only if the **whole message is a yes** (≤ 6 words, no question mark, nothing left after the yes-words but filler: `kit.consent.confirms`; "no, don't do it", "I'm not sure", "ok what is my budget" are not confirmations), the changes were prepared in an earlier question, and not more than 10 minutes ago. Everything announced in one question is made by one yes; each change is claimed before it runs, so a second yes finds nothing. The summary names what a delete or overwrite is about ("Delete a task permanently [Pay rent]").
  - **DELETES** need the owner's own delete word in the same message *and* the owner's yes afterwards; `delete_transaction` is never offered.
  - The model cannot confirm anything: confirmation is not a tool and its input is the owner's message, never a tool result or a document.
  - Every proposal and its outcome (`waiting, running, done, failed, superseded, expired`) is the audit trail (`GET /api/changes`).
- Pictures keep their own "prepare, then confirm in a window" flow in Documents.

## Model use

One local model, schema-constrained output, temperature 0 for extraction, fixed seed 7. The model server address is checked at start-up and again in the client. Atlas selects `ATLAS_MODEL` (default `ministral-3:3b`) using the same rule as Finance (`kit.llm.pick_installed`) and never another installed model. Atlas keeps its own HTTP client because Ollama needs the `Host` header it sets.

## Encryption

SQLCipher with a raw 256-bit key derived from `ATLAS_DB_KEY[_FILE]`. `ATLAS_REQUIRE_ENCRYPTION=1` (Docker) refuses to open without a key. Converting a plain database (`kit.db.encrypt_in_place`): build the encrypted copy beside it, compare every table's rows, the integrity check and the version, swap, compare again, then overwrite and delete the plain file (`ATLAS_KEEP_PLAINTEXT=1` keeps it). A crash between the renames is finished or undone on the next open.

## Migrations

Each step and its version note run in one `BEGIN IMMEDIATE` transaction, statement by statement (triggers stay whole); any error rolls back and the step can be retried. A copy of the database is taken before an upgrade (last three kept).

## UI design

One look for every app (`design/design.css`): light by default, dark on request, white cards, one accent, no gradients (see UI review for places that break this), plain words, shared helpers in `design/common.js`. Apps are shown inside Atlas; opened alone, the Documents pages say they belong inside Atlas.

## Known design limits

Every currency is stored in hundredths. Three places still name the model (Atlas env, Finance setting, Documents env). Routine organiser writes (tasks, notes, people) run at once. See `defects.md` "Open".
