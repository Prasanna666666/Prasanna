# Aperture

A private, offline, agentic AI photo assistant for macOS (Apple Silicon). It indexes a large photo
library (tested design target: ~500 GB) on an external drive and lets you search it in plain English.

- **Local only.** A socket guard blocks every non-loopback connection at runtime; models are fetched once by an explicit command.
- **Originals are protected.** Aperture never modifies, renames or deletes your photos. By default it never moves them either. Moving is an opt-in switch (Tidy up page) that only moves files inside your photo folder, journals every move, never overwrites, and can undo any batch. All other writes are confined to `<drive>/Aperture` and your export folder (`WriteGuard`).
- **Smart filters.** The AI search understands time of day ("evening", "night", hours), weekend/weekday, portrait/landscape, how many people are in a photo (groups, selfies, no people), photos near a place ("within 30 km of Eindhoven"), defect labels and file type, alongside what is seen, written, who and where. Filters are plain SQL on stored data: the LLM only fills them in.
- **Similar shots and defects.** Groups bursts and retakes by visual similarity and capture time and suggests the sharpest, best-exposed photo to keep. Blurry, too-dark, too-bright and blank shots are suggested as defects; nothing is labelled until you confirm, and labels never touch files.
- **Tidy up.** Finds byte-identical duplicates, shows each group side by side (KEEP / MOVE), moves the extra copies to a folder after you confirm, and keeps an undo history. Any chat result can also be moved to a folder.
- **Agentic search.** A local LLM (Ollama) turns any phrasing into a structured plan over five engines: visual (CLIP), text (Apple Vision or Tesseract OCR + PDF text), path/filename, people (face clusters) and place (EXIF GPS -> offline GeoNames). No keyword heuristics: if the LLM is unavailable you get a clear error, not a guess.
- **Zero false positives, zero caps.** Engines combine by set algebra; no match means no results. Every id is kept and the UI paginates (36/page by default).
- **Safe export.** Copies (never moves) to a folder outside the library: temp file, fsync, SHA-256 verify, atomic rename, no overwrites, manifest.
- **Resumable indexing** in passes (index, faces, text), low priority, small memory footprint for 8 GB machines.

## Quick start (Docker, the normal way)

`ollama pull ministral-3:3b`, then `./scripts/up.sh` and open http://lumo.localhost:8765. Docker reads text in photos with Tesseract instead of Apple Vision and has no GPU (slower indexing); if you want speed instead, use the native install below.

## Install natively (macOS, Python 3.10+)

```bash
git clone https://github.com/Prasanna666666/Prasanna.git && cd Prasanna
scripts/install.sh          # venv + models + Aperture.app, all on the external drive
```

Then `ollama pull ministral-3:3b` (the Ollama app stores weights in `~/.ollama`; set `OLLAMA_MODELS` to a folder on the drive to keep them off the internal disk).

## Use

`open ~/Applications/Aperture.app`, or `aperture ui`. CLI: `aperture doctor | scan | ask "..." | stats | settings`.

## Lumo: the fast web app (the normal way to use Aperture)

```bash
aperture secure-ui          # starts Lumo in the macOS sandbox (no internet, photos read-only) on http://127.0.0.1:8765
                            # opens your browser when ready; it stops its own older copy first; Ctrl+C to stop
aperture secure-ui --classic     # the older Streamlit screens: Photos, People, Tidy up, Settings, export/move cards
scripts/aperture-sandboxed.sh --selftest /path/to/photos    # once: must print three PASS lines
aperture --insecure web     # explicit override (not recommended)
```

Lumo is a small local web app written for speed: the page opens instantly and "New chat" costs the server nothing; photo matches
stream in first (milliseconds), then the checked answer, then the reply word by word. One-subject
searches skip the AI plan, and every message first goes through a tiny model-driven router (no phrase lists anywhere). It is plain HTML/CSS/JS served by the standard library
(no frameworks, no CDN, no new packages) with a strict Content-Security-Policy, a per-run token, host/origin checks and photos served
only by number from Aperture's own thumbnail folders.

It is laid out like a regular website: a slim menu (Search, Library, Trips, Places, People), a search bar on every page and a status strip.
**Search** is the chat. **Library** shows every photo, newest first, narrowed by year and month, and loads more as you scroll. **Trips** lists trips and occasions
(from the library's own events, or runs of photos taken close together); **Places** lists every place with its photo count; **People** shows the faces found, each with
their clearest photo. Open any of them to see just those photos, with a removable filter chip; click a photo for the full-size view with arrow-key navigation.
The chat is always one tap away: **Chat** in the menu is the full-page conversation, and on every other page a round **Ask Lumo** button in the corner (or `Ctrl/⌘ J`) opens the same conversation as a panel, photos included, so you can ask without leaving what you are looking at; **Expand** makes it full-page.
Dark (Lagoon, the default), light (Shoreline) or automatic theme from the button at the bottom of the menu; on a phone the menu becomes a tab bar.
Not in the new app yet: naming or merging people, Tidy up, Settings and the export/move cards (use `--classic` for those).

Measure it: `aperture check` (seconds per step), `aperture eval-routes`, `aperture eval-plans`. See `docs/safety.md` (items 8-11).

Prefer a container? `scripts/up.sh` runs Lumo isolated (no internet, photos read-only); see `docs/docker.md` for the trade-offs (CPU only, so slower indexing; text in photos is read by Tesseract).

## Best setup for an 8 GB M1 (what this app is built for)
- The AI model (Ministral 3B) only understands language, with short prompts and tiny outputs. Search, matching and counting are plain code and image search: milliseconds.
- A tiny model-driven router sends photo questions to the planner and everything else to a short, streamed, photo-focused chat reply.
- One model in memory; indexing pauses while you chat and unloads the model when it starts.
- Measure it all with one command: `aperture check` (seconds per step, routing accuracy). Honest limit: a 3B model writes ~19 words a second and is weak at hard reasoning; a bigger Mac or a home server is the only way past that.

## The agent (how Lumo thinks)

Lumo's tool-using agent (RAG + tools + a loop), written to be read: `src/aperture/agent/toolagent.py` (about 250 lines, no framework).

1. **Retrieve**: facts from your own library that matter for this message (matching places and people, the date span, how much is indexed).
2. **Decide**: the model sees the conversation, those facts and its tools (`find_photos`, `count_photos`, `library_overview`, `look_up`). It answers in words
   or calls a tool and fills in the arguments ("last month" becomes `relative="last_month"`). Nobody tells it what the app is: the tools and facts are its world.
3. **Observe**: our code runs the tool with the real search engines and gives the model the result (how many matched, which dates, notes). It reads it and may
   look something up or search again (agentic RAG), within a budget of a few steps.
4. **Answer**: it writes the reply, streamed; the photos it found appear on screen. The code writes no user-facing sentences.

An agent is a goal plus a list of tools (`AgentSpec`); a specialist (a curator, an organiser) is the same loop with a different goal and tools. All tools are read-only.
Measure the whole agent, not single phrases: `aperture eval-tools` (all plan and routing cases).

## Develop

`make install && make check` (ruff, mypy, pytest with fake ML - no models needed). See `docs/` for architecture, safety and agent design.

## Measuring accuracy

```bash
aperture eval-plans                 # how well your Ollama model turns 42 varied requests into correct plans
aperture eval --template golden.json   # then list your own requests and the files that truly match
aperture eval golden.json --sweep   # precision/recall per visual strictness, with a recommendation
```

Aim for >= 90% on both. If `eval-plans` is lower, try a larger Ollama model in Settings; if search precision is lower, choose the strictness `--sweep` recommends.

## Known limits

Visual strictness presets (`strict/balanced/broad`) are tunable defaults; calibrate on your library in Settings. NTFS drives are read-only on macOS and are rejected. First full index of 500 GB takes many hours.

MIT licensed.

## At a glance (same in Orbit and Lumo)

| | |
|---|---|
| Start | `./scripts/up.sh` (Docker) |
| Stop | `./scripts/down.sh` |
| Address | `http://lumo.localhost:8765` |
| Internet | none: internal Docker network, in-code network lock |
| Your files | read-only |
| What it learns | a Docker volume, not a folder on your Mac |
| The AI | one local Ollama, shared by both apps (block its internet in your firewall) |
| Chat | the round button in the corner, or `Ctrl/⌘ J` |
| Search everything | `Ctrl/⌘ K` or `/` (or click the top search bar) |

## How it thinks (the same in Orbit and Lumo)

```
You ask  ->  AI: understand the question, choose the area and the tools
         ->  Router: Money / Documents / Tasks / Notes / Family / Briefing  (Lumo: photos, places, people, text in photos)
         ->  Tools do the actual work: code and SQL for figures, dates, totals and filters; RAG only for documents and notes;
             specialised readers (EXIF, CLIP, faces, OCR) for photos, never the language model
         ->  Every figure is checked against your data
         ->  AI: explain the result in plain words  ->  You
```

Rules:
- AI for understanding, routing, searching by meaning and explaining. Code for every calculation, filter, date and total.
- RAG only for unstructured text (documents, notes), never for the ledger.
- Source data is never changed by the AI: Lumo's assistant can only copy photos into a new folder, never move, rename or delete them.

## One address for everything (Home)
Lumo can run on its own, or as one part of **Home** (`http://home.localhost:8000`, see the `hub` folder on the `orbit` branch of this repository) together with Orbit (money) and any future app: one menu, one search, one chat button. Lumo stays its own sub-system. Inside Home it hides its own menu, top bar and chat button, and answers `GET /api/health` and `GET /api/search?q=` (places, people and trips).
