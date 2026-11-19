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


## 9. Workload, resource and completeness requirements

The initial performance design must account for the owner's existing archive, currently estimated at about 26,000 email items and 1,400 documents; the implementation audit must verify actual counts, formats, sizes and duplicates. Do not add arbitrary hardcoded word/file/source limits or silently omit items. Resource ceilings may be configurable and hardware-aware, but pressure must cause back-pressure, pause, prioritisation or an explicit needs-attention state—not silent data loss.

The pipeline must remain restart-safe across macOS sleep/wake, application restart, low-battery conditions, model unavailability, disk pressure and worker termination. Persist completed work and checkpoints before pausing where possible. Resume from durable state and revalidate source/version fingerprints. Report skipped, unsupported, corrupt, permission-denied and partially processed sources distinctly.

## 10. Existing mechanisms and migration audit

Before redesigning stages, Claude must inventory and map the current consent checks, staged changes, undo journal, audit trail, completion markers (including any .done files), idempotency keys, atomic publication, retry policy and progress persistence. The reported progress returning to 90% after restart is a user-reported symptom, not a reproduced defect until verified against the current code and a reproducible test. Preserve useful mechanisms; identify proven gaps before proposing replacements.

## 11. Data portability and schema evolution

Every durable store needs explicit schema/version metadata and a tested migration strategy. Migrations must be restartable or safely atomic, preserve source IDs and provenance, validate record counts/checksums and provide rollback or restore. The owner must be able to export personal data and source-linked knowledge in documented, open, machine-readable formats. Export must state what is excluded, encrypted or transformed; it must not require Atlas to remain installed to interpret the exported data.
