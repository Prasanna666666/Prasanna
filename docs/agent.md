# Agent design

`Planner` asks the LLM (Ollama JSON-schema output, few-shot prompt) for a `Plan`: intent (find/count/export/chat/clarify), boolean clauses (each with one or more engines, optional exclude), match all/any, date spec, scope (library/previous). `extract_json` + `plan_from_raw` tolerate fences, smart quotes, trailing commas, truncation and wrong types; up to 3 attempts with a repair prompt.

`Executor` evaluates each clause (union over its engines), combines clauses with set algebra, applies deterministic date resolution, then ranks (visual score else newest). A `ClauseReport` per clause explains empty results. No result cap anywhere.

Visual search is calibrated: cosine floor plus softmax against generic baseline captions, so unrelated queries return nothing.

## Filters

`Plan.filters` (`search/filters.py`) holds structured constraints the LLM fills in: time of day or hours, weekday/weekend, orientation, min/max people, defect status, GPS present, file kind and "near <place> within N km". `apply_filters` turns them into SQL and offline GeoNames distance maths. Time-of-day uses only photos whose camera recorded a time (`taken_exif`), never the file date. People counts only use photos the face pass has processed, and the answer says when it has not finished.

## Quality and similar shots

`quality.py` measures sharpness (95th-percentile block Laplacian variance on a 512 px preview), mean brightness and contrast. `similar.py` links photos taken within a time window whose CLIP embeddings are close (neighbour depth 40 in time order), then the best photo of each group is the highest `quality_score`. Thresholds are presets and need calibration on a real library.
