# Saathi

A private personal assistant. One local SQLite database, one chat, small modules.

**Today:** Tasks & reminders (recurring), Notes, Money (expenses, income, budgets), People (family, parents, birthdays), a daily briefing.

```bash
cd saathi && pip install -e ".[ui]"
ollama pull llama3.1:8b           # the local model used by Chat (any tool-capable Ollama model works)
saathi ui                         # Today / Chat / Tasks / Notes / Money / People / Settings
saathi brief | saathi tools | saathi chat
```

Try in Chat: "remind me to call Amma every Sunday 6pm", "spent 450 on groceries", "add my father Ramesh, born 1958-03-14",
"what's due this week?", "how am I doing on budget?".

Data is in `~/.saathi/saathi.db` (override with `SAATHI_HOME`).

## Run in Docker (recommended for private data)
```bash
cd saathi
docker compose --profile setup run --rm pull-model     # once: downloads the model (only time it touches the internet)
docker compose up -d --build                           # then open http://127.0.0.1:8501
# Apple Silicon (native Ollama for GPU speed):  ollama pull llama3.1:8b  &&
docker compose -f docker-compose.yml -f docker-compose.mac.yml up -d --build
```
- `app`, `ollama`, `gateway`, `egress` share an **internal** network with no route to the internet.
- Only `egress` (an allowlist CONNECT proxy, `saathi/egress.py`) is also on an outside network; it permits just
  `api.open-meteo.com`, `geocoding-api.open-meteo.com`, `api.frankfurter.app` on port 443, and refuses private IPs.
- All containers: non-root, read-only filesystem, all Linux capabilities dropped, no-new-privileges. The UI is
  published on 127.0.0.1 only. Data lives in Docker volumes `saathi-data` and `ollama-models`.
- Disk encryption: Docker volumes are not encrypted by themselves - keep FileVault / BitLocker / LUKS on.
- Verify isolation: `docker compose exec app python -c "import urllib.request as u; u.urlopen('https://example.com')"` must fail.

## Privacy model
- **The model is local** (Ollama). No cloud AI is used anywhere.
- **Egress guard** (`netguard.py`): the process can reach loopback and three public hosts (Open-Meteo, Frankfurter/ECB) - DNS and connects to anything else are refused.
- **Public lookups carry no private text**: `weather` takes only a city name, `exchange_rate` only two currency codes (regex-validated, so a prompt-injected model cannot smuggle your data out in them). `current_time` is offline.
- **Audit**: every outbound request is logged; see Settings > "Everything sent to the internet".
- Not done yet: encryption at rest, container with network policy, Gmail. See roadmap.

## Adding a feature
1. Create `src/saathi/modules/health.py` with a `MODULE = Module(name, migrations, tools)` (see `tasks.py`).
2. Append it to `ALL` in `modules/__init__.py`.
3. The tools immediately work in the chat, and you add a page in `app.py`. Migrations are append-only.

## Roadmap (suggested order)
0. **Hardening**: encrypted database, Docker compose (app + Ollama on an internal network, allowlisting egress proxy), read-only fs.
0b. **Gmail, local-only**: fetch via OAuth into the local DB, summarised by the local model; drafts only, never auto-send.
1. **Health & parents' care** - medicines with dose schedules, appointments, vitals log, per-parent records.
2. **Reminders that reach you** - push/WhatsApp/Telegram/email delivery of due items (today they are only shown).
3. **Calendar** - read/write Google or Apple calendar; briefing merges events.
4. **Money import** - bank/UPI CSV import with auto-categorisation, recurring bills, subscriptions.
5. **Home** - appliance warranties, service dates, maintenance, shopping list, documents.
6. **Documents vault** - scan/photo of bills, prescriptions, IDs; extraction by Claude; searchable.
7. **Proactive agent** - morning briefing, nudges ("rent due in 3 days, balance low").

Dev: `pip install -e ".[dev]" && pytest`.
