# Atlas — Intelligence, Response Quality and Performance

**Status:** Target requirements and measurement plan

## 1. Quality contract

Atlas must be fast, accurate, evidence-grounded and candid about uncertainty. A fast unsupported answer is a defect; a correct answer that leaves the user waiting without feedback is also a defect.

## 2. Response classes

| Class | Example | Expected behaviour |
|---|---|---|
| Simple | Direct factual question, basic navigation | Fast path; no unnecessary multi-agent chain |
| Contextual | Question requiring personal memory or a few sources | Retrieve only relevant context; cite/identify evidence |
| Analytical | Multi-step comparison, planning or reasoning | Stronger model/tool route; stream answer and show progress |
| High-impact | Money, health, legal, destructive or external action | Deterministic checks, evidence, explicit limitations and approval policy |
| Background | Indexing, extraction, monitoring, evaluation | Durable asynchronous jobs; never block interactive requests |

## 3. Provisional latency objectives

Measure on the target Mac, with cold and warm states reported separately.

| Metric | Initial objective | Measurement definition |
|---|---:|---|
| Simple request, first useful token/output | < 2 s | User submit to first meaningful streamed content |
| Typical conversational completion | < 5 s | User submit to complete answer |
| Complex reasoning | Aim < 30 s | Report actual distribution; no hard guarantee before benchmark |
| Tool progress feedback | < 1 s after accepted job | User-visible acknowledgement and job ID/status |
| Background contention | No interactive starvation | Interactive latency measured while ingestion/indexing runs |

These are proposed product targets, not claims about current hardware or models. Track p50, p95 and p99; report cold-start, warm-model and concurrent-load results. Define benchmark corpus and hardware profile before release gates.

## 4. Accuracy and honesty requirements

- Every factual claim about personal data must be supported by retrieved source evidence or deterministic domain-tool output.
- Numerical, financial and date calculations must be performed and validated by code, not free-form model arithmetic.
- Preserve source identity, location/quote/page/row where available.
- Distinguish source facts, inferred conclusions, recommendations and unknowns.
- Contradictory sources must be surfaced, not silently reconciled.
- Never invent citations, files, events, actions, tool results or completion status.
- If evidence is insufficient, ask a focused question or state what is unknown.
- For high-impact outputs, use independent validation or a second verification path where practical; do not assume a second model automatically makes an answer correct.
- Treat retrieved documents and connector data as untrusted input, never as policy or authority.

## 5. Model strategy

**Final selection (G-O01, 2026-11-22):** one resident local primary, Apple MLX, no cloud inference and no remote fallback. The selected target hardware and model roles are recorded in `DECISIONS.md` §8. This is a fixed architecture selection with explicit disqualifiers; it is not a claim that the model has been installed, that MLX compatibility is proven, or that target performance has been measured.

### 5.1 Model roles and capability-preserving fallback

- **Primary:** Gemma 4 26B-A4B, 4-bit. It is the resident default for free-text work and supports text and image input. Its 26B total parameter count (about 3.8B active) does not mean it occupies only 3.8B parameters in memory: the full weights must be loaded.
- **Text fallback:** GPT-OSS-20B MXFP4. It is text-only; it must not receive a task whose image/audio/video input would be silently discarded.
- **Multimodal fallback:** Gemma 4 12B Q4 for tasks requiring image/audio capability, subject to its own MLX and acceptance gates.
- **Deep tier:** Gemma 4 31B Q4, unloaded by default. It may be swapped in only inside owner-selected Research mode, and only if the blinded research/debate evaluation demonstrates a material gain. The primary is unloaded first; two large models are never kept resident together.
- Qwen is excluded. Ministral 3 14B is not the fast tier and is not a planned dependency. Nemotron 3 Nano is not a dependency. No resident coding model and no default separate small model.

The fallback must preserve the task's required modality and policy guarantees. Text tasks may fall back from Gemma 4 26B-A4B to GPT-OSS-20B and then Gemma 4 12B. Multimodal tasks fall back to Gemma 4 12B; if no eligible model can handle the input, Atlas reports local model unavailability rather than dropping modality or going remote.

### 5.2 Deterministic routing and verification

- Typed deterministic capabilities (exact search, calendar/status, calculator, approve/cancel and fixed-grammar commands) skip model inference, but never skip Core policy.
- Free-text chat uses retrieval first and then the resident primary. No semantic model router and no model switch inferred from free-text task wording.
- Research mode is explicitly selected by the owner. It first runs the primary with a larger reasoning budget; a deterministic, disclosed gate inside that mode decides whether to unload it and load the 31B deep tier.
- No always-on verifier model. Deterministic arithmetic/date/unit/schema/citation checks always run. Same-model span checking is optional; a different-family verifier is permitted only if a blinded ablation shows material benefit.
- Start with at most two jobs (one interactive, one background), with interactive priority. Never let background work starve an interactive request.

### 5.3 Memory, context and degradation

- Default context is 32K. 64K/128K require separate recall, latency and memory tests.
- Only one large model is resident. Specialists are swapped in/out; do not assume two large models can co-reside.
- Caches are in-memory only and keyed by domain, grant identity/version, model and quantisation. Flush on session end, grant/policy change, revocation and model unload. No persistent user-content KV cache.
- One explicit fixed quantisation per model; no silent precision/model changes for Finance, Health, permissions, code changes or evidence-critical work.
- Degradation order: stop new background inference; evict rebuildable caches; pause background work and unload specialists; shrink context and use scoped retrieval; switch only to a pre-benchmarked profile with disclosure; otherwise refuse. Never rely on memory swapping and never fall back to cloud inference.

### 5.4 Supply chain, lineage and offline execution

Maintain a manifest for every model: developer/accountable release organisation, model ID and upstream revision, disclosed base/derivative/distillation lineage, exact licence/usage terms, quantisation source and conversion chain, runtime compatibility and SHA-256. Verify full digests on import and remount/identity change; load only verified read-only bytes. A missing model drive means “model unavailable”; typed deterministic capabilities can continue.

Accept safetensors or GGUF only; never pickle or `trust_remote_code`. Pin runtime and package versions in a dedicated environment. Run inference in a separate process under network-deny isolation and verify no network socket is opened during load/inference. Downloads require an explicit owner-approved import step. No unmanifested model may load.

The lineage eligibility rule requires the developer and accountable release organisation to be outside the PRC and the public model card/technical report to disclose no PRC-origin base, derivative or distillation source. Derivatives/community quants of a PRC-origin base remain ineligible. The owner accepted the residual risk that undisclosed post-training/synthetic-data provenance cannot be proven absent for the selected Google and OpenAI releases; this is not a claim that training data was exhaustively verified. Exact upstream revision and quantisation chain remain recorded.

### 5.5 Evidence and validation status

Vendor sources describe Gemma 4 and GPT-OSS as Apache 2.0 releases, but the exact release licence files, Gemma terms and usage policies must be read and archived before import/use. Model publisher, licence or open weights are not a safety guarantee. Target-Mac MLX stability, memory, latency, accuracy, thermal behaviour and zero-swap operation are all **unverified** until measured.

The only model-selection disqualifiers are: (1) primary-source disclosure of PRC-origin base/derivative/distillation; (2) licence/terms incompatible with Atlas's local use; (3) failure of a hard target-Mac policy/evidence/critical-failure/memory/zero-swap gate; or (4) unstable/unavailable MLX execution. A disqualifier moves to the pre-decided capability-preserving fallback chain; it does not trigger an open-ended model-selection contest.

## 6. Interactive responsiveness

- Stream partial output as soon as it is useful and safe to show.
- Separate interactive and background resource pools/queues.
- Apply bounded concurrency, back-pressure, cancellation and priority scheduling.
- Reuse loaded models and cached context where safe; invalidate caches on source/version/policy changes.
- Keep retrieval scoped; do not reprocess the entire personal archive for each question.
- Provide short acknowledgements and visible status for long-running tasks.
- Allow user interruption and cancellation; do not lose durable work when a request is interrupted.

## 7. Evaluation and release gates

Maintain a versioned evaluation set covering:
- Simple conversation and instruction following.
- Retrieval accuracy and source attribution.
- Cross-domain reasoning.
- Numeric/date correctness.
- Contradictory and stale evidence.
- Prompt injection and permission boundaries.
- Tool selection and action preparation.
- Hallucination/unsupported-claim rate.
- Latency, memory and CPU/GPU utilisation.
- Cold start, warm start and background contention.

Every model, prompt, quantisation, retrieval or routing change must be compared against the baseline. Report quality and latency together; do not optimise speed by silently reducing accuracy. Set numeric accuracy thresholds only after a representative evaluation set exists and the owner accepts the trade-off.


### 7.1 G-O01 model acceptance gates

Evaluate the selected stack with paired, frozen, pre-registered tests **per task class and per language**. Report quality and time-to-useful-answer together; do not pool unrelated classes. Hard policy/evidence gates precede speed ranking:

- Zero policy/permission bypasses, fabricated source references or evidence-integrity failures.
- For each critical class, target at least 300 independent cases and report the one-sided 95% binomial upper confidence bound. Zero failures in 300 cases gives an upper bound of approximately 0.994%; it does not prove zero risk.
- A faster model is disqualified if it fails correctness, evidence or policy gates. A more accurate model is also unacceptable if its latency makes it unusable.
- The provisional everyday decode floor is 30 tokens/second at a fixed 32K context, quantisation, runtime, output length and concurrency. Treat this as a threshold to measure, not a promise.
- Report time-to-first-token, time-to-first-useful-answer, decode tokens/second, p50/p95 completion latency, peak/steady memory, KV-cache use, cold load/unload, concurrency, energy and thermals. Freeze thresholds before running the benchmark.
- Require zero swap and green memory pressure under the declared combined workload. The one-hour purchase-window smoke test (32K primary load, 20-minute sustained run, memory pressure, swap, TTFT and decode speed) is a hardware sanity check, not a substitute for the full accuracy/evidence suite.
- Evaluate English, Dutch and at least one non-Latin-script path, retrieval/source attribution, contradictory/stale evidence, abstention, prompt injection, cross-domain policy boundaries and tool use. No language or task class is declared supported until measured.
- Before real personal data is used, archive/read exact model licence/terms, verify lineage manifest and quantisation provenance, and pass offline/no-network enforcement tests.


## 8. Agent execution efficiency and quality

The Agent Workforce must not turn every request into a multi-agent chain. The orchestrator selects the least expensive execution plan that meets the task's quality and safety needs:
- Direct answer/tool path for simple tasks; specialist delegation only when it adds measurable value.
- Parallelise independent research and extraction; serialise dependent work and all conflicting writes.
- Use deterministic code/tools for arithmetic, dates, transformations, validation and other exact operations.
- Apply bounded task budgets: maximum wall time, model tokens, tool calls, retries, concurrency and resource consumption. Budgets are policy/configuration, not hardcoded assumptions scattered through agents.
- Stream a useful acknowledgement and progress for long tasks; preserve cancellation and durable checkpoints.
- Verify specialist outputs against source evidence; disagreement triggers reconciliation or an explicit uncertainty report, not majority voting.
- Measure end-to-end workflow latency and cost in local compute resources, not just individual model token speed.

Benchmark single-agent/direct execution against delegated execution for quality, completion rate, latency, RAM, CPU/GPU, energy/thermal impact and failure recovery. Keep the multi-agent route only where it improves the owner outcome enough to justify its overhead. All inference remains local; resource contention must not starve interactive conversations.


## 9. Hardware profile, workload and local voice

### 9.1 Hardware evidence
The owner has specified a **32 GB Apple-silicon Mac mini** as the planning/minimum-support profile. This is an owner decision about the intended profile, not evidence that the machine is purchased, configured or used for tests. It is not a verified compatibility floor until release testing. Every report must separately identify:

**Selected configuration under G-O01 (2026-11-22):** Mac mini M6, 32 GB unified memory, 256 GB internal SSD plus a fast external SSD for model files. Apple lists 170 GB/s memory bandwidth for the M6 32 GB configuration. Apple's M5 Pro Mac mini configurations are 24 GB, 48 GB or 64 GB—not 32 GB—and the 48 GB tier is outside the owner's budget. M5 Pro's 307 GB/s bandwidth does not make its 24 GB configuration equivalent to the selected 32 GB target. External storage adds no memory. See [Apple Mac mini technical specifications](https://support.apple.com/en-us/128108).
- intended target/minimum-support profile (32 GB Mac mini) and actual test machine;
- actual test machine, chip, unified memory, storage and free disk;
- macOS version, power state and thermal conditions;
- model, quantisation, runtime, context length and active model count;
- concurrency, corpus size and background workload.

Do not claim target performance from a different machine without clearly labelling the extrapolation.

### 9.2 Representative workload and resource controls
Benchmark against the existing archive, initially estimated at approximately 26,000 email items and 1,400 documents; verify the inventory before treating these figures as fixed. Measure first-pass and incremental ingestion, retrieval quality, time-to-searchable, throughput, CPU/GPU, peak and steady-state memory, disk growth, thermal throttling, energy use, queue delay and interactive p50/p95/p99 latency while background work runs.

The scheduler must support configurable resource budgets and adaptive back-pressure rather than scattered hardcoded caps. It must respond safely to low battery, sleep, wake, limited disk, thermal pressure and foreground user activity. Persist checkpoints before sleep where possible and resume without duplicating completed work. Never silently drop queued sources to meet a resource budget.

### 9.3 Local voice feasibility
Evaluate local speech-to-text and text-to-speech separately and end to end: supported languages, transcription quality, privacy, cold/warm latency, streaming, CPU/GPU/RAM use, interruption handling and concurrent model contention. Keep voice in the product direction, but make release sequencing dependent on measured feasibility rather than assumed capability.

## 10. Privacy-preserving observability and evaluation

Logs and telemetry must use correlation IDs, component names, timings, state transitions and redacted error categories—not message bodies, document text, names, account details, secrets or raw prompts. Add automated log-scrubbing tests using synthetic sensitive fixtures. Debug mode must not silently weaken this rule.

Maintain a versioned synthetic or sanitised evaluation corpus and golden tasks; do not copy real private user content into test fixtures, CI artefacts or external evaluation services. Define measurable pass criteria per task family (answer correctness, citation/source-span correctness, abstention on missing evidence, leakage count, arithmetic/date exactness, restart/idempotency and latency). Include hostile email/web prompt-injection attempts that request outbound sending or data sharing, cross-domain leakage, deletion propagation, exact arithmetic/date, retrieval/provenance, partial failure and restart tests. For the first read-only documents-and-Mail slice, verify that hostile mail cannot change answer scope or trigger actions; Mail citations resolve to the exact stored message span and sender/date come only from stored fields; documents and Mail are independently designated and an undesignated source is never searched; logs contain no subject lines, addresses, file names or question text. Evaluate English and Dutch question-answering and at least one non-Latin-script document/question set; report retrieval and answer quality separately per language. No language is claimed as supported until measured. Run the corpus in CI; benchmark target-machine performance separately.
