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
- **Store** (`store.py`): the service takes the reader's output into its encrypted database (SQLCipher, key in the macOS Keychain) and **deletes the readable copy**. Each document is judged once: the local model says what it is (invoice, receipt, payslip, statement, tax, insurance, contract, ticket, booking, medical, other) and quotes its facts; code accepts an amount or a date only if it is written in the document (`orbit.extract`). A cheap check (no model) skips newsletters; files from a collection folder are always read.
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

## Changing your pictures (move, delete, export)
Through the assistant, in two steps. `preview_move_pictures` / `preview_delete_pictures` describe what would happen and change **nothing**; `apply_change` carries it out only in a **later** question whose own words confirm it ("yes, go ahead"), never in the question that prepared it, and not while the indexer runs. Every move is journaled in the index and `undo_change` puts it back (only when you ask to undo). A delete is a move into `Aperture - deleted/<date>` inside the photo folder, so it can be undone too; nothing erases a file for good. `export_pictures` only copies. This is the one place the photo folder is writable (the service container; the indexer's mount stays read-only), and moves stay inside the photo folder.

## One reader per kind of file
`parser.PARSERS` maps each kind of file (text, csv, pdf, image, sheet, doc, html, email, json; archives and mailboxes are opened first) to its own reader. A new kind of file is a new function and its extensions, nothing else. Formats that can be recognised exactly need no model (`recognise.py`: bank standards, the ECB rate file).

## Pictures
The picture engine (`../images`) runs here too: a sealed indexer reads your photo folder and the service answers from its index (`GET /api/pictures?q=`, thumbnails at `/api/pictures/thumb/<id>`, text found in pictures searchable together with the documents). The page has tabs for the picture library (by date), trips, places and people. Set up by `docker-compose.pictures.yml` (included by `scripts/up.sh` when the photo drive is connected). The rest of this section is about pictures inside mail and the inbox:

A picture is read with offline OCR. If there is text in it (a photographed receipt, a letter), it is a document and is judged like any other. If there is none, it is a **photo**: it is stored with the kind `photo` and no model is asked, and `GET /api/documents?kind=photo` lists them, for the Photos app to take. Photos keeps its own deep index (faces, places, picture search); it does not yet read this list, so nothing is handed over today.

## Independent
Documents depends only on the shared `kit` (`../kit`: encrypted database, local model client, no-network guard, retrieval, and the checks on what a model reads out of a document). It imports nothing from Finance, and its image contains nothing of Finance. Finance and Documents each build from the repository root.

## Not done yet
Not run on a real Mac or with the real model: the Docker images have not been built and the Apple Mail folder has not been read.
