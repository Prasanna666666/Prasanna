# Stage 3: threat model T1 to T12 as a traceability matrix (WP3.1)

For each threat: who owns the control, which package builds it, the test that proves it, and the evidence class. **L** = provable on Linux CI, **M** = needs the Mac. A test written in WP3.1 is named and exists; every other test is **pending** and is a proposed name for the package that implements the control. Nothing pending is claimed to exist. Contract and schema evidence here is developer-reported until GitHub Actions completes for the exact head.

| # | Threat | Control owner | Implemented by | Test | Evidence | Status |
|---|---|---|---|---|---|---|
| T1 | Hostile content steers the model or widens scope | Scope only from grants (`policy.py`, `gate.py`) | Existing; real-model part in WP3.4 | existing hostile-source tests in `test_policy.py`, `test_review_fixes.py`; `test_real_model_injection_resistance` | L existing; M pending | existing / pending |
| T2 | Parser bombs, traversal, symlinks, encrypted or huge files | Isolated parser with explicit limits | WP3.2 parser package | `test_parser_limits_end_in_needs_attention` | L | pending |
| T3 | Index poisoning replayed | Retrieved text is untrusted at read time | WP3.2 index package | `test_poisoned_passage_cannot_widen_scope` | L | pending |
| T4 | Stale grant, cache or index serves revoked content | Revalidation (existing) plus index and cache invalidation | Existing; index part in WP3.2 | existing revocation tests in `test_review_round2.py`; `test_revocation_invalidates_index_entries` | L | existing / pending |
| T5 | Deleted or changed source still cited | `EvidenceRef.version_sha256` (existing) plus deletion propagation | WP3.2 index package | `test_source_change_invalidates_citation_and_index` | L | pending |
| T6 | Consent route abused by a non-owner client or by content | Owner-interactive role and replay protection (shape specified in WP3.1) | Consent package | shape: `test_the_consent_shapes_exist_in_1_1_only_and_refuse_bad_values` (exists); behaviour: `test_only_owner_interactive_client_can_change_consent` | L | shape exists / behaviour pending |
| T7 | Spoofed sender or date believed; quoted text misattributed | `authenticity: claimed` and the `quoted` flag (schema in WP3.1) | WP3.3 Mail package | schema: `test_a_locator_missing_a_required_field_or_carrying_an_irrelevant_one_is_refused` (exists); behaviour: `test_quoted_text_never_cites_the_sender` | L | schema exists / behaviour pending |
| T8 | Private data leaves through egress (URL, query, path, subdomain, header, image) | Typed tools, taint rule, leak check (policy §10); the event shape `egress.decision` (WP3.1) | Egress package; OS isolation in WP3.4 | event shape: `test_a_safe_event_cannot_carry_content_a_host_a_url_or_a_free_text_field` (exists); `test_tainted_task_cannot_exfiltrate` (L); `test_model_worker_has_no_network` (M) | L / M | shape exists / rest pending |
| T9 | Logs, events or artefacts contain content | SafeEvent allow-list; new events are enumerations and counts; `reason_code` is a closed enumeration in 1.1 | WP3.1 (shape), every package (use) | `test_no_new_field_of_the_1_1_contract_can_carry_free_text`, `test_an_unknown_slug_or_a_content_like_value_is_refused_as_a_reason_code` (exist); per-package sentinel scans | L | shape exists / rest pending |
| T10 | Index or parser jobs starve interactive work or fill the disk | Bounded concurrency and explicit limits | WP3.2 and WP3.6 | `test_slow_parser_and_full_disk_degrade_explicitly`; real load | L / M | pending |
| T11 | Real data processed with a weak key provider | Keychain provider required for real data | WP3.6; real Keychain on the Mac | `test_real_data_requires_keychain_provider` (L); real Keychain (M) | L / M | pending |
| T12 | Crash mid-index or mid-answer duplicates or loses state | Stage 2 checkpoints and idempotency extended to index jobs | WP3.2 index package | `test_index_crash_matrix` | L | pending |

## Invariants the schema cannot express (for the implementing package)
- `Coverage.searched = Coverage.total` when `state = complete` (coverage package): test `test_complete_coverage_has_searched_equal_to_total` **pending**.
- The version a 1.1 client requests equals the version echoed; the signed message contains the applied version (identity package): enforcement tests **pending**; specification vectors exist (`tests/test_contracts_v11.py`).
