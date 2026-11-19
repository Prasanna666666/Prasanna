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
