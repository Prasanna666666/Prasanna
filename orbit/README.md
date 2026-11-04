# Orbit

A private personal assistant. One local SQLite database, one chat, small modules.

**Today:** Tasks & reminders (recurring), Notes, Money (expenses, income, budgets), People (family, parents, birthdays), a daily briefing.

```bash
cd orbit && pip install -e ".[ui]"
ollama pull ministral-3:3b       # the one local model Orbit uses (check the exact name at ollama.com/library)
orbit ui                         # Today / Chat / Tasks / Notes / Money / People / Settings
orbit brief | orbit tools | orbit chat
```

Try in Chat: "remind me to call Amma every Sunday 6pm", "spent 450 on groceries", "add my father Ramesh, born 1958-03-14",
"what's due this week?", "how am I doing on budget?".

Data is in `~/.orbit/orbit.db` (override with `ORBIT_HOME`).

## Run in Docker (offline, encrypted, split by trust)
Needs Ollama installed natively on the Mac (fast, uses the GPU) and Docker Desktop.
```bash
ollama pull ministral-3:3b                  # the ONLY step that needs internet (once); afterwards Wi-Fi can be off
./scripts/up.sh                             # creates the database key in your Keychain on first run, then starts everything
./scripts/up.sh --show-key                  # print the key ONCE and store it offline: lose the key = lose the data
```
Open http://127.0.0.1:8501. `orbit ui`, `chat`, `brief`, `tag`, `import-notes` and `ingest` **refuse to run without the encryption key** (so effectively only via Docker); for throwaway fake data use `ORBIT_ALLOW_PLAIN=1 ORBIT_HOME=/tmp/orbit-test orbit ui`. Drop PDFs / CSVs / text into `~/OrbitInbox`; the parser picks them up, then use the Documents page.

```
 ~/OrbitInbox (read-only) -> [parser: NO network, 1 GB, 128 procs] -> parsed JSON volume -(read-only)-> [app: no internet,
                                                                                    encrypted DB, assistant] -> 127.0.0.1:8501
```
- **parser**: the only code that opens untrusted files. No network at all (`network_mode: none`), inbox read-only, each file
  parsed in a throw-away subprocess with CPU/memory/time limits. Outputs plain JSON only.
- **app**: sees parser output **read-only**, contains no PDF/parsing libraries, internal Docker network (no internet).
- **Encrypted database** (SQLCipher, AES-256): key in the macOS Keychain, handed to the app container as an environment variable by `up.sh` (Docker stores container settings inside its own disk image on your Mac, so keep FileVault on). It is never in this folder or in git.
  `ORBIT_REQUIRE_ENCRYPTION=1` makes the app refuse to start without it - no silent plain-text fallback.
- All containers: non-root, read-only filesystem, all capabilities dropped, no-new-privileges. UI on 127.0.0.1 only.
- `gateway` and `ollama` are byte forwarders on Docker's default network (needed to show the page and reach Ollama on the Mac).
- The **documents agent is read-only** and told to ignore instructions inside documents, so a booby-trapped PDF cannot make
  Orbit change or delete anything.
- Not covered by Orbit: Ollama itself and macOS (turn off Ollama update checks, or switch Wi-Fi off / use LuLu). Keep FileVault on.
- Verify: `docker compose exec app python -c "import urllib.request as u; u.urlopen('https://example.com')"` must fail;
  `docker compose exec app sh -c "touch /parsed/x"` must fail (read-only).
- Untested on a real Mac (no Docker engine where this was written). Send only error text if a step fails.

## Your finance folder (statements, payslips, invoices, receipts, tax and insurance letters, contracts - any bank, any language)
Keep your PDFs where they are and point Orbit at the folder; it is mounted **read-only** and only the offline parser can open it:
```bash
ORBIT_FINANCE_DIR="/path/to/your/finance folder" ./scripts/up.sh      # default: ~/OrbitFinance. Subfolders are fine (ing/2026/, payslips/ ...)
```
Then open **Money -> Read new finance files** (or `orbit import-statements`).
- **Any finance file:** the model says what each file is (bank statement, payslip, invoice, receipt, tax, insurance, contract or other) and pulls
  out who it is from, the date, due date, reference, total and VAT. Invoices and receipts are filed and summed by kind, month or supplier; they are not
  added as bank transactions (the payment already appears on the statement). Ask in chat: "what invoices are due?", "how much VAT on receipts?".
- **The model never copies a number.** The local model (Ministral via Ollama) only works out the *layout* of a file: which column is the date, the
  description, money out, money in, the balance; how dates and numbers are written. Plain code reads every line with that layout, so no digit is
  mistyped and no line is invented. Dutch, English, any bank: nothing is coded per bank.
- **Every statement is proved.** Each line is a transaction, the continuation of one, a balance line, or ignored text; a line with an amount that fits
  none of these is reported. Running balances must add up from line to line (also when printed newest-first). A file ends as **verified** (the
  balances add up), **unverified** (no balances to check against: imported, marked) or **needs check** (a balance does not add up, a direction cannot be
  known, a line is unexplained, or the layout is not understood). **A file that needs a check adds nothing to your totals**, and Money says so, with the reason.
- **Payslips and invoices:** the model quotes each amount exactly as printed; an amount is kept only if that exact text is in the document.
- **Honest limits.** Scanned (image-only) or password-protected PDFs have no text and are listed as such. A statement without balances can be read but
  not proven. Categories and trip/event grouping are interpretation, not arithmetic: they can be wrong and are fixed by telling Orbit in chat.
- **Safe to repeat and to interrupt.** A line is never stored twice, even when statements overlap. Reading takes a minute or two per file: the model is only
  asked for the layout.
- **Verifier agents** (independent checkers; any one can fail a file; see `verify.py`). *Per file:* layout reader, balance prover (running balances add up),
  totals prover (opening + transactions = closing, which also proves credit cards that have no running balance), second reader (the layout is worked out
  again from a different part of the file and both readings must give identical transactions), standard reader (MT940 / camt.053: exact, to the cent).
  *Across documents, after every import:* payslip net pay vs the bank deposit (to the cent), invoice/receipt totals vs a payment, each statement starting
  where the previous one ended per account (and no month missing), and plausibility (nothing dated in the future or outside its own statement).
  Money > Documents & checks shows what each agent concluded, in words.
- **Everything must tally.** *Currencies* are kept apart: every payment carries its currency (read from the statement; the main currency is assumed, with a
  warning, if it says nothing) and every report shows ONE currency at a time, so euros and rupees are never added. *Transfers between your own accounts* are
  matched exactly (same amount and currency, opposite directions, different accounts, within three days, and each the other's only candidate) and kept out of
  spending and income on both sides; ambiguous or lonely ones are reported, never guessed. *Account ledger:* for each run of consecutive proven statements,
  opening + every payment stored for that account = closing, which catches a payment lost or counted twice between a statement and your ledger. *Tally:* every
  month and currency, the raw ledger's net change must equal money in - day to day - trips and events + transfers, so no report can drop or double-count a payment.
- **Your own calculations are checked too.** Notes you imported (Apple Notes) with blocks like "Asian games 2026 / Tickets: 634.1 / ... / Total: 2438.36"
  are read by code: *notes arithmetic* checks that the lines add up to the total you wrote, to the cent (refunds negative), and *notes <-> app* compares each
  block with the event of the same name, line by line and total, listing every difference in words. Neither your notes nor the app is trusted until they agree.
- **How the verifiers are tested.** 340 randomly generated statements (several number notations, one or two amount columns, oldest-first and newest-first) must be
  read back exactly; each is then altered (one cent on a balance, one cent on an amount, a line dropped, a line duplicated) and every alteration must be caught.
  One limit is written down as a test: a missing LAST line is invisible to running balances unless the closing balance is printed; the next statement's opening
  balance (continuity) is what catches it.
- **Any file, one shape.** The parser (offline, isolated) reads PDFs (text, **scanned**, **password-protected**), photos/screenshots (png, jpg, tiff, webp), spreadsheets
  (xlsx), Word (docx), web pages, emails (with their attachments), JSON, ZIP archives, CSV/TSV, MT940, camt.053 and plain text, and turns every one into the same shape:
  plain text plus rows or positioned cells. Scans and photos are read with **Tesseract** (Dutch + English, no network); the balance checks catch a misread digit.
  For protected PDFs put the passwords, one per line, in `passwords.txt` in your finance folder (it is never read as a document).
- **Everything in euros, at the rate of its day.** Each payment gets its amount in euros using the ECB's daily reference rate for its own date (weekends use the
  last published rate, up to a week back; nothing older is used). Run `./scripts/fetch-rates.sh` once on your Mac (the only step that goes online, and not part of
  the app) to download the ECB history into your finance folder, then press **Read my files**. Payments with no rate are left out of the euro totals and reported.
  A transfer between two of your accounts in different currencies (e.g. rupees to euros) is matched when the euro values are within 6% and the days within 3; the
  fee and spread (what was sent at the day's rate minus what arrived) becomes an expense of its own, so the euros still tally. The switch at the top of Money shows
  **All in EUR** (default) or one currency as it is.
- **The agents.** Money > Documents & checks > *The agents* lists every reading, proving and cross-checking agent and whether it is working or only planned.
- **Best way to get each bank's data (exact beats PDF).** From the bank's own pages and third-party descriptions; *none of these layouts has been tested on
  a real file yet*:
  - **ABN AMRO:** download "Bij- en afschrijvingen" as **MT940** or **camt.053** (exact, read without a model), or the TXT export. PDF is read best-effort.
  - **Wise:** use the **CSV** statement. The PDF often has no date column (dates sit inside the description) and its headers vary by language and currency.
  - **ICICI / SBI:** use the **CSV** or Excel-as-CSV export from net banking. ICICI PDFs are usually password-protected, which Orbit cannot open. SBI PDFs show
    Txn/Post Date, Value Date, Description, Ref/Cheque No, Debit, Credit and a running Balance (sometimes with a CR/DR marker); they are read by layout.
  - **Credit cards (e.g. ABN AMRO card):** read by layout and proved by the previous/new balance printed on the statement.
- **Categories, automatic.** Everyday spending: a few cheap keyword rules, then the local model for the merchants left (it sees only names, never
  amounts). **Trips, matches, shows and cancellations:** after every import the local model groups payments that belong together into named events
  (Asian Games 2026: Tickets, Flights, Stay ... Total), each under sports, events, trips or cancellations; refunds count negative, so a cancellation can
  end below zero. Each payment is looked at once. Nothing to click: if something is wrong, tell Orbit in chat ("move the Ajax tickets to the PSV event").
- **Views:** day-to-day tiles by category, trips and events with totals, month by month, regular payments, payslips, and chat ("what did I spend on food
  last month?", "how much tax did I pay this year?"). **What did Orbit make of each file?** lists every file with counts only, never content.
- Scanned (image-only) or password-protected PDFs have no text to read: Orbit lists them as "read: 0 transactions". Remove the password or use the bank's
  CSV/PDF download instead.
- The model, Ollama, lives on your Mac in `~/.ollama/models` (about 2 GB); your data never leaves your Mac, and Orbit makes no network requests.

## Your data boundary
- Real data lives only on your Mac: `~/OrbitInbox` (files you drop in), Docker volume `orbit-data` (the database), Ollama (model).
  It is never in this folder. `.gitignore` and `tests/test_data_boundary.py` block data files from git.
- `mkdir -p ~/OrbitInbox` before `docker compose up`; it is mounted **read-only** into the app.
- Never paste real statements/notes into a cloud AI chat (including the one that wrote this code). Paste error text only.

## Bring in your Apple Notes
```bash
pip install -e .                 # on the Mac, outside Docker (no dependencies)
orbit export-notes               # allow the "control Notes" prompt; writes text files to ~/OrbitInbox/notes/
orbit import-notes               # or the button on the Notes page; safe to repeat - updates, never duplicates
```
Locked notes are skipped and counted; images/attachments are not exported (text only). Untested on a real Mac.

## Agents and tagging
- A router picks a **specialist agent** per message (instant keyword routing; the local model only breaks ties):
  `money`, `tasks`, `family`, `notes`, `briefing`, else `general` (all tools). `orbit agents` lists them.
- Each agent is offered, and allowed to call, **only its own tools** (enforced in code). Fewer tools = faster and more
  reliable on a 3B model, and a confused agent can only affect its own area. The chat shows which agent answered.
- **Auto-tagging**: `orbit tag` or the Notes page button tags untagged notes (rules + people names first, then the local
  model, limited to a fixed vocabulary). It never changes tags you set yourself.
- If the model is not installed, Orbit tells you the exact `ollama pull` to run. It never switches to a different model family.

## Adding a feature
1. Create `src/orbit/modules/health.py` with a `MODULE = Module(name, migrations, tools)` (see `tasks.py`).
2. Append it to `ALL` in `modules/__init__.py`.
3. The tools immediately work in the chat, and you add a page in `src/orbit/static/app.js`. Migrations are append-only.

## Roadmap (suggested order)
0. **Hardening** (done): encrypted DB, isolated parser. Next: OCR for scans (Tesseract in the parser box), approval cards for changes.
0b. **Mail, offline**: import a Google Takeout .mbox file (no live connection), summarised by the local model.
1. **Health & parents' care** - medicines with dose schedules, appointments, vitals log, per-parent records.
2. **Reminders that reach you** - push/WhatsApp/Telegram/email delivery of due items (today they are only shown).
3. **Calendar** - read/write Google or Apple calendar; briefing merges events.
4. **Money import** (done: CSV/PDF statements, categories, repeating payments). Next: budgets from history, alerts for unusual spending, OCR for scans.
5. **Home** - appliance warranties, service dates, maintenance, shopping list, documents.
6. **Documents vault** - scan/photo of bills, prescriptions, IDs; extraction by Claude; searchable.
7. **Proactive agent** - morning briefing, nudges ("rent due in 3 days, balance low").

Dev: `pip install -e ".[dev]" && pytest`.
