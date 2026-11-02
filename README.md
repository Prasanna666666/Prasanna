# Aperture

A private, offline, agentic AI photo assistant for macOS (Apple Silicon). It indexes a large photo
library (tested design target: ~500 GB) on an external drive and lets you search it in plain English.

- **Local only.** A socket guard blocks every non-loopback connection at runtime; models are fetched once by an explicit command.
- **Originals are protected.** Aperture never modifies, renames or deletes your photos. By default it never moves them either. Moving is an opt-in switch (Tidy up page) that only moves files inside your photo folder, journals every move, never overwrites, and can undo any batch. All other writes are confined to `<drive>/Aperture` and your export folder (`WriteGuard`).
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

Then `ollama pull llama3.2:3b` (the Ollama app stores weights in `~/.ollama`; set `OLLAMA_MODELS` to a folder on the drive to keep them off the internal disk).

## Use

`open ~/Applications/Aperture.app`, or `aperture ui`. CLI: `aperture doctor | scan | ask "..." | stats | settings`.

## Develop

`make install && make check` (ruff, mypy, pytest with fake ML - no models needed). See `docs/` for architecture, safety and agent design.

## Known limits

Visual strictness presets (`strict/balanced/broad`) are tunable defaults; calibrate on your library in Settings. NTFS drives are read-only on macOS and are rejected. First full index of 500 GB takes many hours.

MIT licensed.
