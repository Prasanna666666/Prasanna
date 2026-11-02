# Architecture

```
ui/ (Streamlit) --> bootstrap.AppContext --> agent/ (planner, executor, service)
cli.py ----------/                      \-> indexing/ (discovery, pipeline, runner)
                                         \-> search/ people/ export.py library.py
                                          -> ml/ (CLIP, SCRFD+ArcFace via onnxruntime, Apple Vision) behind Protocols
db.py (versioned SQLite migrations, WAL, FTS5 trigram)   safety.py   config.py
```

- **Ports/adapters:** `ml/protocols.py` defines the interfaces; `bootstrap.py` is the only composition root. Tests inject fakes.
- **Indexing:** worker threads do pure compute (`process_job`); a single writer thread owns SQLite (`ResultWriter`). Passes: index (metadata, thumbnails, CLIP, place) -> faces -> OCR. Each is resumable via per-item stage flags.
- **Storage:** `<drive>/Aperture/{data,models,logs,jobs,geo,tmp,cache}`; embeddings float16, searched in float32 chunks.
- **Pagination:** `paging.py` is pure; the UI renders only the current page's thumbnails.
- **Scalability:** memory is O(page) for UI, O(n x 512 x 2 bytes) for the visual index (~1 GB per 1M photos).
