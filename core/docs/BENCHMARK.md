# Benchmark plan and baseline

## What this measures and what it does not
Only the overhead of the foundation itself, with stubs (no model, no retrieval, no ingestion). It says nothing about answer latency: the <2 s first-useful-output and <5 s typical-answer targets stay provisional and unmeasured (Stage 3, target Mac).

## Baseline (developer container; NOT the target Mac; NOT CI)
`python bench/overhead.py --runs 300 --json`, Python 3.13.18, Linux 6.18 x86_64, one run of the script, 300 samples each (one sample for the create-task call):

| Operation | p50 | p95 | max |
|---|---:|---:|---:|
| `contract_validate_TaskRequest` | 0.139 ms | 0.215 ms | 1.0 ms |
| `policy_decide` | 0.005 ms | 0.007 ms | 0.06 ms |
| `api_signed_version_roundtrip` (identity + version) | 0.252 ms | 0.317 ms | 0.64 ms |
| `task_submit_and_run_with_stubs` (about 14 encrypted transactions) | 20.1 ms | 28.0 ms | 49.5 ms |
| `api_signed_create_task` | 6.7 ms (1 sample) | | |

Reading: the dominant cost is the durable, encrypted task state (about 20 ms per task with stubs on this container), not policy or identity. Whether that matters depends on SSD and on the target Mac; it is small against model time but should be re-measured on the Mac, and could be reduced by fewer transactions per task if needed.

## Plan for the real baseline (later; needs the target Mac, owner-run or authorised)
Record machine model, RAM, OS, power/thermal state, model and quantisation, runtime, context size, concurrency, corpus and cold/warm condition; measure p50/p95/p99 of first-useful-output and typical answers idle and under ingestion load; report extrapolations as extrapolations.
