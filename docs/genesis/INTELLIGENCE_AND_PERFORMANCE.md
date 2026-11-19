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

Model architecture is an implementation choice, not the product architecture:
- Dense and Mixture-of-Experts (MoE) models are both eligible.
- Select by measured task quality, latency, memory footprint, context capacity, structured-output reliability and energy/resource cost.
- Active parameters do not equal memory requirements; benchmark actual quantised model footprint and runtime overhead.
- Support model/runtime adapters so a model can be replaced without changing domain capabilities.
- Use small models for low-risk routing/classification only when their error rate is acceptable; escalate when confidence or task complexity requires it.
- Avoid unnecessary serial model calls. Prefer one capable model plus deterministic tools over elaborate agent chains when quality is comparable.
- Local inference only. A missing or unavailable local model must produce an honest local-unavailable state, not remote fallback.

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
