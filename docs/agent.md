# Agent design

`Planner` asks the LLM (Ollama JSON-schema output, few-shot prompt) for a `Plan`: intent (find/count/export/chat/clarify), boolean clauses (each with one or more engines, optional exclude), match all/any, date spec, scope (library/previous). `extract_json` + `plan_from_raw` tolerate fences, smart quotes, trailing commas, truncation and wrong types; up to 3 attempts with a repair prompt.

`Executor` evaluates each clause (union over its engines), combines clauses with set algebra, applies deterministic date resolution, then ranks (visual score else newest). A `ClauseReport` per clause explains empty results. No result cap anywhere.

Visual search is calibrated: cosine floor plus softmax against generic baseline captions, so unrelated queries return nothing.
