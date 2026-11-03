# Aperture

A private, offline, agentic AI photo assistant for macOS (Apple Silicon). It indexes a large photo
library (tested design target: ~500 GB) on an external drive and lets you search it in plain English.

- **Local only.** A socket guard blocks every non-loopback connection at runtime; models are fetched once by an explicit command.
- **Originals are protected.** Aperture never modifies, renames or deletes your photos. By default it never moves them either. Moving is an opt-in switch (Tidy up page) that only moves files inside your photo folder, journals every move, never overwrites, and can undo any batch. All other writes are confined to `<drive>/Aperture` and your export folder (`WriteGuard`).
- **Smart filters.** The AI search understands time of day ("evening", "night", hours), weekend/weekday, portrait/landscape, how many people are in a photo (groups, selfies, no people), photos near a place ("within 30 km of Eindhoven"), defect labels and file type, alongside what is seen, written, who and where. Filters are plain SQL on stored data: the LLM only fills them in.
- **Similar shots and defects.** Groups bursts and retakes by visual similarity and capture time and suggests the sharpest, best-exposed photo to keep. Blurry, too-dark, too-bright and blank shots are suggested as defects; nothing is labelled until you confirm, and labels never touch files.
- **Tidy up.** Finds byte-identical duplicates, shows each group side by side (KEEP / MOVE), moves the extra copies to a folder after you confirm, and keeps an undo history. Any chat result can also be moved to a folder.
- **Agentic search.** A local LLM (Ollama) turns any phrasing into a structured plan over five engines: visual (CLIP), text (Apple Vision OCR + PDF text), path/filename, people (face clusters) and place (EXIF GPS -> offline GeoNames). No keyword heuristics: if the LLM is unavailable you get a clear error, not a guess.
- **Zero false positives, zero caps.** Engines combine by set algebra; no match means no results. Every id is kept and the UI paginates (36/page by default).
- **Safe export.** Copies (never moves) to a folder outside the library: temp file, fsync, SHA-256 verify, atomic rename, no overwrites, manifest.
- **Resumable indexing** in passes (index, faces, text), low priority, small memory footprint for 8 GB machines.

## Install (macOS, Python 3.10+)

```bash
git clone https://github.com/Prasanna666666/Prasanna.git && cd Prasanna
scripts/install.sh          # venv + models + Aperture.app, all on the external drive
```

Then `ollama pull ministral-3:3b` (the Ollama app stores weights in `~/.ollama`; set `OLLAMA_MODELS` to a folder on the drive to keep them off the internal disk).

## Use

`open ~/Applications/Aperture.app`, or `aperture ui`. CLI: `aperture doctor | scan | ask "..." | stats | settings`.

## Secure by default (macOS sandbox)

Photo commands (`ui`, `app`, `scan`, `ask`, `caption`, ...) **refuse to run** unless they are inside the sandbox or Docker. The normal way:

```bash
aperture secure-ui          # starts the UI in the sandbox: no internet, photos read-only; always http://127.0.0.1:8765
                            # (stops its own older copy first, opens your browser; Ctrl+C to stop; refresh the page as usual)
aperture secure-ui --allow-moves     # only if you want Tidy up to move files inside the photo folder
scripts/aperture-sandboxed.sh --selftest /path/to/photos    # once: must print three PASS lines
aperture --insecure ui      # explicit override (not recommended)
```
See `docs/safety.md` (items 8-10), including encrypting the drive.

Prefer a container? `docker-compose.aperture.yml` runs Aperture isolated with read-only photos; see `docs/docker.md` for the trade-offs (CPU only, no photo OCR).

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
