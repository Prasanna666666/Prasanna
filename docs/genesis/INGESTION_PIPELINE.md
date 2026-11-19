# Atlas — Ingestion and Durable Processing

**Status:** Target pipeline; replaces neither current behaviour nor data until migration is approved

## 1. Problem statement

The current Read → Sort → Group flow captures useful stages, but the user has reported long processing times and progress that reappeared at 90% after restart despite a completed run. The target must make stage completion durable, avoid repeating completed work, and connect related information across multiple sources without losing provenance.

The stage names are not the architecture. Preserve useful concepts, redesign internals where evidence warrants it.

## 2. Target pipeline

```
Discover / capture
  -> identify source and version
  -> extract / parse / OCR
  -> interpret / classify / structure
  -> verify / reconcile
  -> link entities and related evidence
  -> index / publish
  -> monitor changes and maintain
```

Each stage is independently versioned and can be retried. A source may be partially complete; that state must be explicit and must not be represented as complete.

## 3. Durable job model

Persist at minimum:
- Stable source ID and source version/fingerprint.
- Job ID, stage, stage version and state.
- Attempt count, timestamps, worker lease/heartbeat.
- Input/output references and checksums.
- Checkpoint/cursor and completed work units.
- Resource usage and scheduling priority where practical.
- Warnings, errors and partial-completion details.
- Retry eligibility and next retry policy.
- Cancellation request and terminal outcome.

The UI is a projection of persisted state, never the source of truth. A restart must reconstruct the exact stage status from durable records.

## 4. Correctness and resilience

- **Idempotency:** retrying the same stage/input must not duplicate facts, documents, links or side effects.
- **Checkpointing:** commit useful progress at bounded intervals; never mark a stage complete before outputs are durable and validated.
- **Atomic publication:** downstream stages see either a validated output version or no new version, not a half-written result.
- **Isolation:** one corrupt/unreadable file must not stop unrelated sources.
- **Retries:** classify transient vs permanent failures; use bounded backoff and a review/dead-letter state.
- **Cancellation:** cooperative cancellation at safe points; retain committed work and resume safely.
- **Versioning:** parser, prompt, model, schema and stage versions are part of cache keys and reproducibility metadata.
- **Change detection:** process new or changed sources only; reprocess when relevant dependencies or versions change.
- **Resource management:** bounded concurrency, back-pressure, low-priority background execution and fair access to model resources.

## 5. Cross-document understanding

Related evidence may be distributed across many files. Avoid forcing each document into an isolated final interpretation. Build a knowledge-linking stage that:
- Extracts candidate entities and relationships from individual sources.
- Uses deterministic identifiers and exact matches where possible.
- Uses model-assisted matching only with evidence and confidence.
- Retains source-level facts and provenance for every link.
- Represents uncertain or conflicting relationships explicitly.
- Supports later re-evaluation when new evidence arrives.

Grouping is a derived view over evidence, not a destructive merge of source records.

## 6. Progress semantics

Expose distinct states: queued, running, paused, waiting for resources, partially complete, completed, failed, cancelled and needs review. Show stage and source counts with a clear definition. Percentages must be mathematically meaningful; if total work is unknown, show completed work units or indeterminate progress rather than a misleading percentage.

Persist progress at stage and source level. A completed source/stage must not revert to an earlier percentage after restart unless its input version or processing version changed; explain that invalidation.

## 7. Performance strategy

- Profile discovery, extraction, OCR, inference, verification, linking and indexing separately.
- Batch model requests where this improves throughput without harming correctness.
- Cache only with complete dependency fingerprints.
- Avoid repeated full-library scans and repeated model interpretation of unchanged sources.
- Use specialised deterministic parsers for well-defined formats and model inference for ambiguity/semantic interpretation.
- Benchmark representative corpora and report throughput, error rates, memory, CPU/GPU, and tail latency.

## 8. Acceptance tests

At minimum:
- Kill/restart at every stage boundary and selected mid-stage points.
- Re-run completed and partially completed jobs.
- Change source bytes, parser version, prompt version and model version.
- Inject duplicate events and concurrent workers.
- Simulate disk full, corrupt input, unavailable model and worker crash.
- Verify no duplicate records or lost source evidence.
- Verify progress matches durable state after restart.
- Verify one failed source does not block unrelated work.
- Verify links retain provenance and do not merge conflicting facts.
