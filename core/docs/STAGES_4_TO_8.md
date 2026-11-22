# Stages 4 to 8: what was built, what is evidenced, what is not (developer report for architect review)

Branch `genesis-stage4-6` (despite the name it carries Stages 4 to 8), made from the Stage 3 head. **No pull request was opened and PR #8 was not touched**, so the Stage 3 head under review did not move. Authorisation:
the owner's instruction of 2026-11-23 ("Do it"). `TARGET_ARCHITECTURE.md` §11 says the roadmap is not implementation authorisation by itself and the architect's earlier brief said Stage 4 waits for a reviewed
package: **these stages are therefore implemented on the owner's instruction and are NOT architect-reviewed, NOT accepted, and Stage 3 is still not accepted.** Nothing here is a release, an owner-tryable build or a
claim about real hardware.

**CI:** push run [45078151927](https://github.com/Prasanna666666/Prasanna/actions/runs/45078151927) on `049fd58` passed every job, including Core on Python 3.11 and 3.13, the hosted macOS Swift and Core jobs, the MLX sandbox job and the app packaging job (hosted-runner evidence only). An earlier run on `88d02d2` failed only the secret scanner on a test variable name, fixed in `049fd58`.

Evidence classes as in `STAGE3_ACCEPTANCE.md`: **L** = automated test on Linux with synthetic data and deterministic stubs. **R** = hosted macOS runner (CI on this branch is read separately; until then every
result is developer-reported). Statuses: **MET-L** (met for its stated testable scope), **PARTIAL**, **NOT BUILT**, **DEFERRED-FINAL** (cannot be tested without hardware, accounts, a real model or a person; stays
release-blocking).

## The one defect found on the way
`ClientRegistry.revoke` set the flag but never wrote it to disk: a revoked client was un-revoked by a Core restart. It now persists (`tests/test_devices.py::test_revocation_is_immediate_durable_and_survives_a_restart`).
The method was introduced in the Stage 2 foundation commit `8fc495e` and was tested only with an in-memory registry, so the accepted Stage 2 scope contains the same defect and Stage 3's owner-client registry inherits it. It is fixed here, not in PR #8; the architect should decide whether to port the fix to PR #8.

## Stage 4: storage, keys and recovery (UC-L15, UC-L18, UC-040, UC-044, UC-046; G-O02, G-O05)
Design: `ADR_STORAGE_KEYS.md` (proposed). Code: `backup.py`, `storage.py`, `launchagent.py`, `host.KeychainLocked`, `serve.EXIT_NEEDS_SIGNIN`, `CoreLauncher.swift`.

| Exit evidence (roadmap §11) | Status | Tests | Not done |
|---|---|---|---|
| Storage / encryption / key-boundary ADR | proposed | `ADR_STORAGE_KEYS.md` | architect review and owner acceptance; G-O02 stays open until then |
| Integrity-checked backup and restore | MET-L | `test_backup.py::test_a_backup_verifies_holds_only_what_cannot_be_rebuilt_and_leaks_no_plaintext`, `::test_a_corrupted_truncated_missing_or_tampered_backup_is_refused_with_a_code`, `::test_the_restore_drill_a_replacement_mac_gets_its_tasks_back_but_no_grant_and_the_index_is_rebuilt`, `::test_a_restore_goes_only_into_an_empty_place_and_a_failure_leaves_nothing_behind`, `::test_a_damaged_backup_is_never_restored_even_partly` | an owner-facing way to run it (CLI, API route, schedule, destination choice); an open-format export beyond the backup folder |
| Key recovery | MET-L (mechanism) | `test_backup.py::test_the_keys_come_back_only_with_the_recovery_passphrase` | **G-O05, the acceptable recovery experience, is the owner's and is open**; real Keychain provisioning of recovered keys (fake only) |
| Restore verified before sensitive-domain indexing or any single-copy dependency | PARTIAL | the restore drill above | nothing in code refuses to index Finance or Health until a restore drill has passed; that gate is a release rule, not an enforced one |
| Disk pressure | PARTIAL | `test_storage.py::test_usage_is_reported_by_category_and_originals_are_not_counted`, `::test_pressure_levels_follow_the_stricter_of_the_fraction_and_the_floor`, `::test_pressure_can_pause_derived_work_and_warn_but_never_delete_anything` | the indexers do not yet consume the pause actions; the report and the policy exist |
| Reboot / Keychain behaviour | MET-L for the files and the exit path | `test_launchagent.py::test_the_agent_runs_only_in_the_owners_login_session_and_restarts_only_after_a_crash`, `test_launcher.py::test_a_locked_keychain_makes_the_core_exit_with_its_own_code_and_the_launcher_says_the_mac_needs_sign_in`, Swift `testACoreThatExitsBecauseTheKeychainIsLockedIsReportedAsNeedingOwnerSignIn` | **DEFERRED-FINAL:** a real reboot with FileVault on, real Keychain locking, a real LaunchAgent install; nothing installs or loads the plist |

## Stage 5: personal-data domains and migration (Finance §3.5, Health §3.6, Calendar, Contacts, Notes; G-021)
Code: `records.py`, `finance_calc.py`, `migration.py`, `recordstore.py`; `policy-rules.json` (source types and the `records` schema are data); `CoreConfig.records`; `designation.allow_adapter_types`.

| Exit evidence | Status | Tests | Not done |
|---|---|---|---|
| Domain access (own store, own key, own grant, G-021) | MET-L, synthetic | `test_domains.py::test_a_restricted_domain_answers_under_its_own_grant_with_an_exact_citation`, `::test_no_domain_answers_for_another_domains_grant_and_nothing_crosses_over`, `::test_a_domain_is_offered_for_designation_only_when_its_adapter_is_configured`, `::test_contacts_and_calendar_are_labelled_by_the_policy_and_carry_their_fields_exactly` | **real adapters for Calendar, Contacts and Notes on macOS (permissions, EventKit, the Contacts framework, Notes access) are NOT BUILT; Photos is NOT BUILT**; only synthetic record sources exist; a question spanning two granted domains is covered by the Stage 3 policy tests, not by a new end-to-end test |
| Arithmetic by code | MET-L | `test_finance_calc.py::test_sums_are_exact_where_floats_are_not`, `::test_month_over_month_is_exact_and_the_percentage_is_labelled_rounded_and_absent_without_a_base`, `::test_a_summary_names_its_inputs_is_a_finance_record_and_can_be_recomputed`, `::test_a_tampered_or_stale_summary_is_refused`, `test_domains.py::test_a_code_computed_total_is_served_with_the_inputs_it_names_and_verifies` | portfolio, tax and loan scenario analysis, reconciliation of statements, unusual-transaction detection are NOT BUILT; Health has no computations and no measured-versus-estimated labelling |
| Cache and revocation | MET-L | `test_domains.py::test_withdrawing_a_domain_purges_its_index_and_what_tasks_derived_from_it`, `test_health.py::test_a_permission_reset_withdraws_every_grant_and_purges_what_was_derived` | |
| No egress for restricted data | MET-L | `test_domains.py::test_a_task_with_a_restricted_domain_in_scope_has_no_network_even_when_live` | the egress gateway itself is still disabled and unexercised on the real Internet (Stage 3, F-11) |
| Migration parity | MET-L for the legacy `transactions` table only | `test_migration.py::test_the_import_reconciles_row_for_row_and_the_original_is_byte_for_byte_unchanged`, `::test_a_row_that_cannot_be_carried_over_exactly_stops_the_import_before_anything_is_written`, `::test_reconciliation_catches_a_changed_a_missing_and_an_extra_record`, `::test_a_migrated_finance_database_is_durable_and_listed_newest_first`, `test_domains.py::test_a_migrated_legacy_finance_database_answers_through_the_core_under_the_finance_grant` | the legacy `payslips`, `finance_docs`, `goals`, `rates`, `budgets` and other tables are inventoried and NOT migrated; Library, Images and Aperture data are not addressed; nothing was run on a real database |
| Undo | MET-L | `test_recordstore.py::test_undo_restores_exactly_and_only_the_latest_change`, `::test_deleting_is_soft_and_undoable_and_the_history_keeps_everything`, `test_actions.py::test_own_calendar_and_notes_changes_never_prompt_and_every_one_can_be_undone` | |
| Destructive migration separately accepted | **never offered** | `test_migration.py::test_retiring_the_original_is_never_done_here_and_the_module_has_no_way_to_delete` | retiring a legacy database stays a separate, owner-approved, separately accepted action |

## Stage 6: chief of staff and connected actions (PRD 4.4, 4.5; TARGET_ARCHITECTURE 12)
Code: `actions.py`, `record_actions.py`, `orchestrator.py`, `browser.py`, `watchers.py`.

| Exit evidence | Status | Tests | Not done |
|---|---|---|---|
| Only the closed approval list ever prompts; prompt-count | MET-L | `test_actions.py::test_the_action_matrix_only_the_four_categories_ever_need_approval`, `::test_own_calendar_and_notes_changes_never_prompt_and_every_one_can_be_undone` | |
| Approval single-use and bound to the exact payload; expiry | MET-L | `::test_sending_an_invitation_needs_approval_bound_to_the_exact_payload_and_is_single_use`, `::test_an_approval_expires_and_cannot_be_granted_after_use` | |
| Content is never the owner | MET-L | `::test_instructions_in_content_can_neither_propose_nor_approve`, `test_browser_watchers.py::test_page_text_is_untrusted_data_and_whatever_it_asks_for_is_refused` | |
| Conflict, idempotency, undo, compensation, honest partial failure | MET-L | `test_actions.py::test_irreversible_removal_needs_approval_and_a_retry_does_not_run_twice`, `::test_a_stale_edit_is_a_conflict_not_an_overwrite_and_a_failing_handler_is_a_code`, `::test_a_workflow_takes_back_what_it_did_when_a_step_fails_or_it_is_cancelled`, `::test_a_workflow_stops_at_a_step_that_needs_approval_and_reports_a_step_that_cannot_be_taken_back` | |
| Connector revocation | MET-L (generic, fake connector) | `::test_a_revoked_connector_refuses_every_one_of_its_actions` | **the home, travel, shopping and work connectors are NOT BUILT** |
| Audit | MET-L | `::test_the_audit_is_chained_content_free_and_tampering_is_detected` | the audit lives in memory; it is not persisted |
| Orchestration (sealed registry, least authority, bounded retries, honest ends, direct path first) | MET-L against stub agents | `test_orchestrator.py` (all) | **no real specialist agent exists**; the agent-versus-single-model benchmark is **DEFERRED-FINAL** (needs the real model) |
| Browser workflows | MET-L for policy and untrusted handling with a fake browser | `test_browser_watchers.py::test_only_allowed_public_https_hosts_are_opened_and_a_redirect_off_the_list_ends_the_workflow` | the real Playwright adapter and macOS app automation are NOT BUILT |
| Notifications and proactive watchers | MET-L | `test_browser_watchers.py::test_a_notification_carries_no_content_and_a_watcher_has_no_way_to_act`, `::test_quiet_hours_hold_normal_notifications_release_them_once_and_never_repeat_an_event`, `::test_calendar_conflicts_are_overlaps_not_touching_ends` | OS notification delivery is a seam; no unusual-transaction watcher; **voice is NOT BUILT** |
| **Wiring** | **PARTIAL** | `test_operations_api.py::test_the_owner_creates_edits_and_undoes_a_note_without_a_single_prompt`, `::test_an_invitation_needs_the_owners_approval_of_exactly_that_payload_and_is_sent_once`, `::test_only_the_owner_can_propose_approve_or_undo_and_a_device_cannot`, `::test_a_device_syncs_its_offline_queue_once_and_conflicts_are_reported`, `::test_a_core_without_an_edits_key_has_no_actions_and_no_sync_at_all`, `::test_the_erase_action_exists_only_with_a_platform_eraser_and_always_needs_approval` | **Wired:** the Action Gateway and sync are reachable through four additive API 1.1 routes (`/v1/actions`, `/v1/actions/approve`, `/v1/actions/undo`, `/v1/sync`; contract, OpenAPI, client and tests), owner-only except sync, and the Core builds them when `CoreConfig.edits_key` is set. **Not wired:** the production host (`host.build_config`) does not yet provision the edits-store key, the sender or the eraser, so on a real Mac these routes answer `not_found` until it does; the orchestrator, the browser workflows and the watchers are libraries with no route; device pairing and revocation (`devices.py`) have no route |

## Stage 7: production Mac release
Code: `updater.py`, `health.py`, `scripts/sign_and_notarize.sh`, `launchagent.py`.

| Exit evidence | Status | Tests | Not done |
|---|---|---|---|
| Authenticated update, atomic install, rollback | MET-L | `test_updater.py` (signed install; unsigned, altered or mismatched refused; never backwards; unhealthy rolls back by itself and the data folder is untouched; crash leaves the old version; unsafe artefacts refused; explicit rollback) | the update channel, the one-click UI, a backup before update, and an additive-schema check at rollback time |
| Health checks and redacted diagnostics | MET-L | `test_health.py::test_health_names_each_check_and_reports_codes_not_content`, `::test_diagnostics_hold_no_question_passage_file_name_key_or_home_path`, `::test_redaction_is_a_second_line_of_defence_for_anything_that_slipped_in` | |
| Permission reset | MET-L | `test_health.py::test_a_permission_reset_withdraws_every_grant_and_purges_what_was_derived` | |
| Signing and notarisation | script and dry-run MET-L | `test_signing_script.py` | **DEFERRED-FINAL:** an Apple Developer ID and a real run; stapling and Gatekeeper on a real Mac |
| Auto-start after login | MET-L (file) | `test_launchagent.py` | installation and `launchctl` are not done |
| Target-Mac Keychain, FileVault, update-restart, performance, model isolation, crash recovery | **DEFERRED-FINAL** | | needs the target machine and the real model |

## Stage 8: iOS and secure worldwide access (Core side only)
Code: `devices.py`, `sync.py`, `watchers.push_payload`. **The iOS client does not exist and cannot be built or tested here (no Xcode, no device).**

| Exit evidence | Status | Tests | Not done |
|---|---|---|---|
| Device enrolment and revocation | MET-L (Core side) | `test_devices.py` (owner-only offers; single-use, five-minute, guess-limited code; Core pinning; immediate, durable revocation; last owner protected) | the device-side enrolment flow and its UI |
| No public database or model ports | MET-L | `test_devices.py::test_no_module_of_the_core_binds_an_internet_address_or_opens_a_public_port` | the remote channel itself (relay or VPN) is **NOT BUILT and G-O14 is open** |
| Sync, offline cache, conflicts | MET-L (Core side) | `test_sync.py` (ordered queue, idempotent replay even after a restart, conflicts never overwrite, revoked device rejected, no approval-gated operation can be queued, cache policy) | the device-side queue persistence and cache; real network behaviour |
| Notification privacy | MET-L | `test_browser_watchers.py::test_a_push_payload_is_a_kind_and_an_id_and_nothing_a_push_service_or_a_lock_screen_could_read` | an actual push service |
| Remote threat model | written below | | architect review |
| Accessibility, supported regions | **DEFERRED-FINAL** | | need the client |

### Remote threat model (Core side, for review)
| Threat | Control now | Residual |
|---|---|---|
| A stranger pairs a device | owner-only offer, single-use hashed code, five minutes, five wrong guesses close it, member role only | an owner who shows the code to the wrong person; the code is the whole secret |
| A man in the middle at pairing | the offer carries the Core key fingerprint; the Core signs the device key and nonce; the device pins it | depends on the QR or code channel being the owner's own screen |
| A stolen or lost device | revocation is immediate and durable; the device holds no authority offline, only a time-limited cache of its own-record domains | whatever the device already cached before revocation (wipe is requested, not enforced) |
| Replay of a request or a queued operation | signed requests with nonces (Stage 3); operation ids; versions | the op-id memory is per run; replay after a restart yields conflicts, not double effects |
| A device edits something it should not | queue vocabulary excludes approval-gated actions; Finance and Health are not cached or editable; the gateway re-checks everything | none known |
| Exposed ports | the Core binds only the owner-only Unix socket; a test forbids an Internet bind in any module | the relay or VPN in front of it is unbuilt and unreviewed |
| Push leaks | a push carries kind and id only | the push service sees that a notification of a kind exists |

## What would make these stages acceptable
1. Architect review of this branch as a whole, and an owner decision on whether it becomes a pull request (the repository's rule is one PR; this branch deliberately did not open another).
2. The remaining wiring: the production host providing the edits-store key, sender and eraser; routes for device pairing and revocation; the orchestrator, browser workflows and watchers reachable from the Core.
3. The owner decisions G-O02, G-O05, G-O14, and the connector and voice scope for Stage 6.
4. Everything marked DEFERRED-FINAL, on the owner's hardware and accounts.
