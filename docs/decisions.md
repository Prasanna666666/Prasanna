# Standing decisions (from the owner)

Every change is checked against this list before it is called done. It records what the owner has already said, so it is never asked twice.
If something here is wrong, the owner says so once and it is changed here.

## The product
- One personal platform called **Atlas**, one address (`http://atlas.localhost:8000`), one look. Today it holds **Finance** and **Documents** (files, mail and pictures in one); **health, travel, documents and more** are coming. No codenames on screen (not Finance, not Lumo, not Aperture).
- It is **one app**. Behind the one address its parts (money, documents and mail, pictures, later health and travel) keep their own storage and tools, but **every part's data is available to the one assistant and is used based on the question**: it can chain tools across parts inside one answer (ticket dates, then spending on those days, then the pictures taken on them). Parts do not talk to each other behind the scenes; the assistant is where they meet.
- **One chatbot for everything (one assistant over all data, using every part's tools)**, a general assistant the owner can simply talk to, which can also find information, browse, filter and find what things have in common, and give pictures or documents **only when asked**. No per-app chat buttons.
- **One button to read everything new** (documents, pictures, anything). Each kind of data is read in the way that suits it: photos get the extremely detailed indexing and stay on the external drive; PDFs and other documents keep their own reading and live on the Mac.
- **One document reader for everything, a common service (`library/`, shown as Documents), not part of Finance:** every file and mail is read once; the model says what it is (invoice, ticket, booking, medical, insurance, tax ...), code verifies amounts and dates, and any app asks for the kinds it needs (`/api/documents?kind=`). Bank statements are still imported only from the finance folder.
- **One document processor** in the end: whatever arrives goes through one intake and is handed to the right module, which verifies it.
- **One AI model**, one address, for input and output. Cross-queries must work ("expenses, pictures, health reports and tickets for my India trip 2026").

## How much AI, and where
- **AI is for understanding, routing, semantic search and explanation. The model decides what a message means, which part it is about and what to show. Do not decide that with word lists or regular expressions**, not even as a fallback.
- **Code, SQL and specialised tools do the actual work**: every figure, filter, date and total; EXIF, CLIP, faces and OCR for photos.
- **Agents and RAG wherever they are the right tool** (open questions, several steps, documents and notes). Retrieval only for unstructured text, never for the ledger.
- **Chat questions and answers are fully AI.** The model understands every message, routes it, calls the tools and writes the answer. No question is answered by code alone, and no word list or keyword rule routes or answers (when the model is not running the app says so). Code still does all the arithmetic inside the tools and checks every figure in an answer against the data before it is shown.
- Understanding runs on measured evidence: `python -m atlas.evaluate` scores the model by difficulty level and times each path; run it on the owner's Mac after any change to prompts or models.
- The AI never modifies or deletes source data on its own. **Moving, deleting and exporting pictures is a feature the owner wants**: it goes through one gate in Documents (the assistant can only prepare and describe it; a confirmation window shows the full list and only the person pressing Confirm there carries it out, after every check is run again; every move is journaled, audited and undoable, and a delete is a move to a trash folder, never an erase. The same gate **files original documents into folders of the inbox** (moved, undoable) and **copies mail messages** into `Filed mail/<folder>` (the mail stays); bank statements and Apple Mail's own store are never written to (the app sees the inbox **read-only by default**; filing is off until Documents is started with `LIBRARY_INBOX_MODE=rw`). Trip albums are one such change (`Trips/<year> <place>`).
- **Everything offline.** The apps never connect to the internet or a mail server. The only online steps are ones the owner runs outside the apps (downloading the model once, the exchange-rate file, building the Docker images, and Apple Mail's own syncing). Email is read from local files: Apple Mail export, `.mbox` or `.emlx`; there is no live mail fetch unless the owner decides otherwise.
- **Mail is read by the same Update button** (Apple Mail's folder, read-only, in the sealed reader), and **what is found in mail and documents feeds the calculations** (bills due, invoice-against-bank, tax, insurance, trips), not only search. A cheap gate picks what is worth the model's time; code verifies every amount and date.
- Never connect to the cloud. Everything runs on the owner's machine. (The old optional cloud reader in Photos has been removed entirely.)

## Numbers and honesty
- **Numbers must be exactly right.** Business-critical. No excuses. A figure that cannot be proven is not shown as fact; say plainly what could not be proven.
- Do not hard-code bank formats: the model infers the layout, code reads the figures, balances prove them. A file that fails its proof is left out and flagged.
- No CSV files made for the owner. No manual add or edit for event grouping. Original currency by default.
- No "Proven" badge; make sure it is right instead.
- Reports say what was verified and what was not, with no overclaiming. Nothing has been run on the owner's real data or Mac unless stated.
- The assistant (Claude) never accesses the owner's finance data and never asks for it to be pasted; the owner reports counts and words only.

## The interface
- Few words. Simple, non-technical language. Easy terms.
- Modern, attractive, easy to find things in; the same design in every module with its own colours. Charts and cards, not walls of text.
- Monthly or one-time expenses, never "everyday".
- The latest month with data is the default view (statements arrive monthly).
- Pictures and documents appear **only when asked for** (a count or a question is answered in words).

## Security and operation
- Secure by design for sensitive personal data; structured, fast, reliable; strict, modern coding standards enforced by tests and CI (complexity limit, strict types, lint, formatting, architecture tests).
- Threat model: **theft or loss of the laptop is out of scope.** No login password, no FileVault requirement. Other programs and web pages reaching local ports, hostile files, prompt injection, leaks and bugs **are** in scope.
- Health data is locked until unlocked each session (default; change by decision).
- **Very personal data (mail, documents, statements) is kept only in the encrypted database.** The sealed reader's readable copy is deleted as soon as the app has stored it; only content-free markers remain. Nothing personal goes to logs, the network or git.
- **Calls between the platform's programs are signed** with a shared secret kept in the Keychain (`scripts/platform-key.sh`); a service refuses unsigned requests. Opening an app's port directly in a browser therefore no longer works: use Atlas.
- Docker by default for both apps; no internet for the apps; originals mounted read-only, (the inbox can be made writable with `LIBRARY_INBOX_MODE=rw`, and then only the confirmation window writes to it).
- A **weekly summary** (what changed, what is due, what needs a check) is two tools, `weekly_summary` (Finance) and `whats_new` (Documents); the one assistant composes it from them. No figure is written by code into prose.
- **Names:** the three parts are Atlas, Finance and Documents; nothing says Orbit any more. What held your data was renamed *safely*: the data folder `~/.orbit` → `~/.atlas` and `orbit.db` → `finance.db` are renamed once on first start; `~/OrbitInbox`/`~/OrbitFinance` → `~/AtlasInbox`/`~/AtlasFinance` (the old names stay as links); the Keychain key is **copied** to `finance-db-key` (the old entry is kept); the Docker volume `orbit_orbit-data` is **copied** to `finance_finance-data` (the old one is kept until the owner deletes it). Settings are now `ATLAS_*`.

## How to work with the owner
- Do not make the owner explain things again. Check this list and `docs/architecture.md` first.
- Do the work; report briefly and honestly: what changed, what was verified, what was not.
- Ask only when a decision truly belongs to the owner.

- **What the person sees:** Documents has three sections of the same store: **Documents** (files), **Emails** (mail) and **Pictures**, plus Trips, Places, People and Changes. Finance is the money views and calculations over those documents, not a second reader. While reading, progress shows only a number done so far (no total, because files may still arrive); Finance shows "Waiting for Documents" until Documents is done.
- **Menu and Update, as the owner set them:** the menu is Documents, Mails, Pictures, Travel and Finance (Health when its lock exists); the first four are views of the one reader, Finance is the money app. **The Update shows what was added, in three rows: Documents, Pictures, Mails, each with its full number** (the reader counts what is in its folders at the start of every round; "N of M" while reading). Finance speaks up only when something needs a check.
- **Starts by itself:** `scripts/install-autostart.sh` installs a login item (LaunchAgent) that starts Docker, Ollama and Atlas at every login and an `Atlas` app that opens the address. Containers keep `restart: unless-stopped`.
- **Speed and safety, measured (60,000 documents, 50,000 photos):** the search re-indexes only what changed and skips even the check when nothing did (first index 2.8 s instead of over 100 s; each later question about 0.1 s); counts, kinds and the Update numbers come from indexed columns and are reused for 3 s; whole-library photo pages are worked out once per change to the library; the model stays loaded 10 minutes in every part. Services started in Docker refuse every request when the platform key is missing (`ATLAS_REQUIRE_SIGNATURE=1`, and the compose files will not start without it); unlocked Health closes again after 15 minutes unused; every container has memory, process and CPU limits.
