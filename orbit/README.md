# Orbit

A private personal assistant. One local SQLite database, one chat, small modules.

**Today:** Tasks & reminders (recurring), Notes, Money (expenses, income, budgets), People (family, parents, birthdays), a daily briefing.

```bash
cd orbit && pip install -e ".[ui]"
ollama pull llama3.2:3b           # the local model used by Chat (any tool-capable Ollama model works)
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
Open http://127.0.0.1:8501. Drop PDFs / CSVs / text into `~/OrbitInbox`; the parser picks them up, then use the Documents page.

```
 ~/OrbitInbox (read-only) -> [parser: NO network, 1 GB, 128 procs] -> parsed JSON volume -(read-only)-> [app: no internet,
                                                                                    encrypted DB, assistant] -> 127.0.0.1:8501
```
- **parser**: the only code that opens untrusted files. No network at all (`network_mode: none`), inbox read-only, each file
  parsed in a throw-away subprocess with CPU/memory/time limits. Outputs plain JSON only.
- **app**: sees parser output **read-only**, contains no PDF/parsing libraries, internal Docker network (no internet).
- **Encrypted database** (SQLCipher, AES-256): key in the macOS Keychain, passed as a Docker secret, never written to disk.
  `ORBIT_REQUIRE_ENCRYPTION=1` makes the app refuse to start without it - no silent plain-text fallback.
- All containers: non-root, read-only filesystem, all capabilities dropped, no-new-privileges. UI on 127.0.0.1 only.
- `gateway` and `ollama` are byte forwarders on Docker's default network (needed to show the page and reach Ollama on the Mac).
- The **documents agent is read-only** and told to ignore instructions inside documents, so a booby-trapped PDF cannot make
  Orbit change or delete anything.
- Not covered by Orbit: Ollama itself and macOS (turn off Ollama update checks, or switch Wi-Fi off / use LuLu). Keep FileVault on.
- Verify: `docker compose exec app python -c "import urllib.request as u; u.urlopen('https://example.com')"` must fail;
  `docker compose exec app sh -c "touch /parsed/x"` must fail (read-only).
- Untested on a real Mac (no Docker engine where this was written). Send only error text if a step fails.

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
- If the default model is not installed, Orbit uses an installed fallback or tells you the exact `ollama pull` to run.

## Adding a feature
1. Create `src/orbit/modules/health.py` with a `MODULE = Module(name, migrations, tools)` (see `tasks.py`).
2. Append it to `ALL` in `modules/__init__.py`.
3. The tools immediately work in the chat, and you add a page in `app.py`. Migrations are append-only.

## Roadmap (suggested order)
0. **Hardening** (done): encrypted DB, isolated parser. Next: OCR for scans (Tesseract in the parser box), approval cards for changes.
0b. **Mail, offline**: import a Google Takeout .mbox file (no live connection), summarised by the local model.
1. **Health & parents' care** - medicines with dose schedules, appointments, vitals log, per-parent records.
2. **Reminders that reach you** - push/WhatsApp/Telegram/email delivery of due items (today they are only shown).
3. **Calendar** - read/write Google or Apple calendar; briefing merges events.
4. **Money import** - bank/UPI CSV import with auto-categorisation, recurring bills, subscriptions.
5. **Home** - appliance warranties, service dates, maintenance, shopping list, documents.
6. **Documents vault** - scan/photo of bills, prescriptions, IDs; extraction by Claude; searchable.
7. **Proactive agent** - morning briefing, nudges ("rent due in 3 days, balance low").

Dev: `pip install -e ".[dev]" && pytest`.
