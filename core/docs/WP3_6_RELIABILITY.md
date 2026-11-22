# WP3.6 — Reliability, security and performance

Everything here runs on Linux CI with deterministic stubs and synthetic data. **No claim about a Mac, a real model, FileVault, power loss or target-machine performance follows from it.**

## Fault, hostile-input and load matrix
| Area | Boundary / input | Test | Result |
|---|---|---|---|
| Task pipeline (real stack: document index + gateway + service + API 1.1) | crash at each of 11 boundaries (before/mid/after retrieved, drafted, verified; after attempt; before final) | `tests/test_reliability.py::test_a_crash_at_every_boundary_of_the_real_stack_gives_the_same_answer_as_an_uninterrupted_run` | After recovery the 1.1 answer (coverage and model identity included) is byte-identical to an uninterrupted run; exactly one closing event; a saved draft is not sent to the model again. |
| Indexing | crash at scan:begin, scan:mid, doc:before, doc:extracted, doc:mid_commit, doc:after_commit | `tests/test_reliability.py::test_a_crash_in_the_middle_of_indexing_resumes_to_the_same_index` | Same index as a clean run; each crash verified to have fired. |
| Partial index | documents still pending | `tests/test_reliability.py::test_a_half_built_index_gives_an_answer_that_says_indexing_is_incomplete` | Answer has coverage `indexing` and `indexing_incomplete`. |
| Disk pressure | free space below the floor | `tests/test_reliability.py::test_disk_pressure_pauses_indexing_and_says_so_then_resumes` | Indexing pauses and says so; answers say `indexing`; resumes to complete. |
| Cancellation vs run | cancel racing run, and cancel between the queued check and the start | `tests/test_retention.py::test_a_cancel_racing_a_run_ends_in_exactly_one_consistent_terminal_state`, `tests/test_retention.py::test_a_cancel_between_the_queued_check_and_the_start_leaves_the_cancelled_outcome_untouched` | **Found and fixed a real race**: `run()` raised `conflict` when a cancel (or expiry) won between two steps; it now returns the terminal outcome that stands. |
| Idempotency | 12 concurrent submits with one key; 8 concurrent runs | `tests/test_retention.py::test_concurrent_submits_with_one_idempotency_key_create_one_task`, `tests/test_retention.py::test_concurrent_runs_of_different_tasks_all_complete_with_their_own_answers` | One task; all complete with one final event each. |
| Revocation / stale content | purge on revoke; re-grant | `tests/test_retention.py::test_purge_removes_the_content_of_a_revoked_type_from_answers_events_and_checkpoints_and_is_idempotent`, `tests/test_retention.py::test_a_regrant_does_not_bring_purged_content_back`, `tests/test_retention.py::test_purge_is_atomic_when_it_fails_midway` | Answers, final events and checkpoint text of the type are replaced by content-free forms; atomic; idempotent. |
| Retention | finished tasks | `tests/test_retention.py::test_a_finished_task_keeps_no_passage_text_draft_or_quote_but_the_answer_is_still_served`, `tests/test_retention.py::test_every_terminal_path_scrubs` | No passage text, draft or quote is kept after a terminal state. |
| Caches | the gateway holds no prompt or passage | `tests/test_reliability.py::test_the_gateway_keeps_no_copy_of_the_question_or_passages_after_answering` | No persistent or in-memory content cache exists to invalidate; the test pins that. |
| Corrupt inputs | model files, manifest, import record, documents, mail | `tests/test_models.py`, `tests/test_documents.py`, `tests/test_mail.py` | Refused with content-free codes. |
| Hostile API input | 400 seeded random malformed requests (methods, paths, bodies, version headers, signed and unsigned) | `tests/test_reliability.py::test_random_malformed_requests_never_crash_the_api_leak_content_or_return_a_server_error` | No exception, no 5xx, no sentinel echoed or logged. |
| Load | 12 mixed interactive/background requests | `tests/test_reliability.py::test_concurrent_interactive_and_background_requests_never_exceed_two_inferences_and_all_finish` | Never more than two inferences; all finish; no stuck slot (a scheduler lost-wake-up was found and fixed in WP3.4a). |
| Model failure | runtime failing | `tests/test_reliability.py::test_a_model_that_fails_part_way_leaves_no_stuck_slot_and_the_task_ends_in_plain_failure` | Task ends `failed/model_unavailable`; the next question works. |
| Redaction | question, document text, model path, error paths | `tests/test_reliability.py::test_no_question_or_source_content_reaches_any_log_or_output_on_normal_failure_cancel_and_revocation_paths`, `tests/test_reliability.py::test_rejection_and_failure_reasons_of_the_model_layer_carry_no_path_or_content` | No sentinel in the event log, Python logging, stdout or stderr. |

Real bug found by the evaluation set (not by a test written for it): word tokenisation used `\w+`, which cut Hindi (and other marked-script) words into fragments, so a Hindi question never matched a Hindi document. Fixed (`documents.py::_WORD`), with regression tests.

## Ingestion benchmark (developer machine, synthetic, NOT target-Mac evidence)
Command: `python bench/ingest.py --json` from `core/` (seeded; data generated; in-memory mailbox).
Machine: Linux x86_64, Python 3.13, 4 CPUs (a cloud development container). Run once; no repetitions, so no variance is claimed.

| Source | Items | Index time | Search p50 / p95 / max (50 queries) | Database size |
|---|---|---|---|---|
| Mail (stored fields only) | 26,000 | 23.5 s | **2,927 / 3,131 / 3,318 ms** | 56 MB |
| Documents (plain text) | 1,400 | 0.7 s | 285 / 311 / 315 ms | 6 MB |
Peak resident memory of the benchmark process: 142 MB.

**Finding.** Search reads every indexed row (a linear scan), so its time grows with the amount indexed: about 2.9 s per mail search at the owner's stated scale on this machine. The plan's provisional target for a simple request is first useful output under 2 s *including the model*; retrieval alone already exceeds that here. This does not predict the Mac, but it shows the lexical scan will not scale to the owner's mailbox and needs an inverted index (for example SQLite FTS5 if the encrypted-database build provides it) before the performance gate can be met. This is recorded as a limitation and a recommended follow-up; it is not fixed in this package because retrieval ranking semantics are covered by reviewed tests and no threshold has been agreed. Quality was not measured with this run (retrieval and answer quality are in `evals/harness.py`).

Not measured: cold vs warm, p99, a real Mail store, real files, FileVault, concurrency under indexing load on the Mac, and any model latency.
