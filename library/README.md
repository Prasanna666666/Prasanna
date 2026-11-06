# Documents

The **one reader and store for everything that arrives**: files in your inbox, folders you keep for one purpose (finance, later health), and your mail. It is a common service. Finance is one client of it; Health, Travel and anything later are others. No app reads files itself.

```
 inbox, collection folders, Apple Mail (all read-only)
        |
 [reader: sealed, NO network]  -- plain JSON --> [Documents service: no internet, encrypted database]
                                                       |  says what each document is; code verifies every amount and date
                                                       v
                                  GET /api/documents?kind=...&area=...   <- Finance, Health, Travel ... each takes what is relevant
```

## How it works
- **Reader** (`parser.py`, `readers.py`): the only code that opens untrusted files (PDF, scans with offline OCR, images, spreadsheets, Word, web pages, JSON, ZIP, CSV, MT940/camt, and mail: `.eml`, `.emlx`, `.mbox`, with attachments as documents of their own). No network, sources read-only, every file in a throw-away subprocess with limits.
- **Store** (`store.py`): the service takes the reader's output into its encrypted database (SQLCipher, key in the macOS Keychain) and **deletes the readable copy**. Each document is judged once: the local model says what it is (invoice, receipt, payslip, statement, tax, insurance, contract, ticket, booking, medical, other) and quotes its facts; code accepts an amount or a date only if it is written in the document (`finance.extract`). A cheap check (no model) skips newsletters; files from a collection folder are always read.
- **Update**: `POST /api/scan` wakes the reader and keeps taking in and judging until the reader is idle and nothing is new. **One press reads everything**, however much mail there is; an interrupted first read carries on where it stopped.
- **Asking**: `GET /api/documents?kind=medical,ticket&area=<collection>&place=&year=&since=<ready number>&limit=&full=1`. `since` is a `ready` number, so an app that asks "what is new?" never misses a document judged late. `GET /api/search?q=`, `GET /api/document?id=`, the tools for the one assistant (`GET /api/tools`, `POST /api/tool`: `search_files`, `find_documents`, `read_document`, `trips`, `find_pictures`, `library_overview`), the module contract (`/api/health`, `/api/scan`), and a small page.
- **Collections**: `LIBRARY_COLLECTIONS=finance=/collections/finance,health=/collections/health` names folders you keep for one purpose. A document carries its collection's name as its `area`; apps can ask for it.

## Mail
Apple Mail keeps your Gmail on this Mac; the service reads Apple Mail's own folder (`~/Library/Mail`) **read-only**, every mailbox except Junk, Trash and Drafts, only new messages each time, with no date limit. macOS may ask once to let Docker read it (Full Disk Access); `ORBIT_NO_MAIL=1 ./scripts/up.sh` turns it off. Nothing connects to a mail server. `library export-mail` copies mail into the inbox as `.eml` files if you prefer. Mail text is data, never instructions.

## Run
```bash
./scripts/up.sh          # key in the Keychain on first run, then starts the reader and the service (needs Ollama on the Mac)
./scripts/up.sh --show-key
```
Open `http://documents.localhost:8502`, or Atlas (`atlas/modules.d/documents.json`). Finance finds it at `http://library.internal:8502` through a byte forwarder.

## Security
Sources read-only; the reader has no network; the service has no internet; the database is encrypted; no readable copy is left on disk (only empty marker files); only this computer's own host names are answered and changes need the service's own header. Other programs on this computer can still reach the port (no login, by decision); the data itself stays encrypted.

## Writing to your files: one gate, one window
Documents is the one place that reads **and** writes your pictures. Every write (move into a folder, delete, copy out, undo) goes through `changes.py`, the same way every time:
1. **Prepared.** The assistant (`preview_move_pictures`, `preview_delete_pictures`, `preview_export_pictures`) can only describe what would happen. Nothing on disk changes, and it has no tool to go further.
2. **Shown.** A card in the chat opens the **Changes** page and a confirmation window: the full list (from, to), size, destination, and what is wrong with it right now. Opening the window is recorded.
3. **Confirmed by you.** Only the button in the window carries it out (`POST /api/change/confirm`); no tool, sentence or model can. Delete is red and says it goes to a trash folder; Cancel forgets it.
4. **Checked again at that moment.** The window was opened (and for a moment) with the key it was given; the change is under an hour old and not already done; no picture changed, vanished or would land on an existing file since it was prepared; everything is inside the photo folder (never the program's own folders); the pictures are not being read; at most 1,000 files; one change at a time; room to copy.
5. **Done with a journal, verified, audited.** Each move is journaled before the file is touched, checked afterwards, and recorded in the audit trail (`write_audit`). **Undo** (a button in the same page, also confirmed) puts every file back. A delete is a move into `Aperture - deleted/<date>` inside the photo folder; nothing is erased for good.
This is the only place the photo folder is writable (the service container; the indexer's mount stays read-only); statements and mail stay read-only.

## One reader per kind of file
`parser.PARSERS` maps each kind of file (text, csv, pdf, image, sheet, doc, html, email, json; archives and mailboxes are opened first) to its own reader. A new kind of file is a new function and its extensions, nothing else. Formats that can be recognised exactly need no model (`recognise.py`: bank standards, the ECB rate file).

## Pictures
The picture engine (`../images`) runs here too: a sealed indexer reads your photo folder and the service answers from its index (`GET /api/pictures?q=`, thumbnails at `/api/pictures/thumb/<id>`, text found in pictures searchable together with the documents). The page has tabs for the picture library (by date), trips, places and people. Set up by `docker-compose.pictures.yml` (included by `scripts/up.sh` when the photo drive is connected). The rest of this section is about pictures inside mail and the inbox:

A picture is read with offline OCR. If there is text in it (a photographed receipt, a letter), it is a document and is judged like any other. If there is none, it is a **photo**: it is stored with the kind `photo` and no model is asked, and `GET /api/documents?kind=photo` lists them, for the Photos app to take. Photos keeps its own deep index (faces, places, picture search); it does not yet read this list, so nothing is handed over today.

## Independent
Documents depends only on the shared `kit` (`../kit`: encrypted database, local model client, no-network guard, retrieval, and the checks on what a model reads out of a document). It imports nothing from Finance, and its image contains nothing of Finance. Finance and Documents each build from the repository root.

## Not done yet
Not run on a real Mac or with the real model: the Docker images have not been built and the Apple Mail folder has not been read.


## Filing and albums (all through the confirmation window)
- Filing documents is **off by default**: the inbox is mounted read-only. Start with `LIBRARY_INBOX_MODE=rw library/scripts/up.sh` to allow it. Trip albums only touch the photo folder.
- `preview_file_documents` (tool): moves original documents of a kind into a folder inside the inbox, or with `mail` copies mail messages into `Filed mail/<folder>`. The file behind a document is found again by name and proved by its content hash. Moves can be undone; copies leave the original in place. Bank statements (a named collection) and Apple Mail's own store are never touched. Documents that came out of an archive or a mail have no file of their own and are not filed.
- `preview_trip_albums` (tool) and the **Sort into trip albums** button on the Trips page: one change that sorts every trip's pictures into `Trips/<year> <place>`.
- `whats_new` (tool): new documents of the last days by kind and what waits for confirmation (part of the weekly summary).
