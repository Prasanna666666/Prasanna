# G-O19: source designation and consent gate (WP3.3 prerequisite)

Scope: architect brief on PR #8 (review 6000835791). Code: `src/atlas_core/designation.py`, `src/atlas_core/access.py`, the gate in `documents.py`; tests: `tests/test_designation.py`. Evidence class: **CI-verified (Linux)**. Nothing here is Mac-verified; **no Mail data is read, listed, indexed or opened** and there is no Mail adapter.

## What it is

```
owner decision (OnboardingDecision)                          OS permission (OSPermissionProvider: FakeOSPermissions in CI)
        |                                                                         |
DesignationStore (own encrypted file: grants, state, hash-chained audit)          |
        |  grants_for()                                                           |
        +------------------------------ SourceAccess ----------------------------+     one GrantSource for the existing PolicyEngine
                                              |  permitted()
                  DocumentIndex.scan / run / search / get  (and every future source adapter)
```

* **Policy stays the single decision point.** `SourceAccess` is just a `GrantSource`: `PolicyEngine` still judges grant, purpose, ceiling, expiry, restricted and deferred types, and mints the token with the same grant-identity and ceiling binding (incl. the checkpoint binding from `bd62fc1`). There is no second permission system.
* **Lifecycle per source type:** not_configured -> enabled | declined; declined -> enabled; enabled -> revoked; revoked -> enabled with a NEW grant identity. Nothing is enabled by default; documents and mail are decided independently; there is no per-folder grant and the store never records a folder name. Designable types are those the rules know that are not restricted and not deferred (today: `documents`, `mail`; never `mail_attachment`, Finance or Health).
* **One Get Started decision:** `OnboardingDecision(enable, decline, expires_at)`, also buildable from the 1.1 `ConsentRequest` shape. A decision is validated whole and applied in one transaction; a refused decision changes nothing. A request id is single-use (replay protection): an old enable cannot be replayed after a withdrawal.
* **Grants** are the existing `SourceGrant` (valid against frozen 1.0): unique opaque id, ceiling = the policy's own sensitivity for the type (never above), purpose `answer_question`, optional expiry. An expired grant is revoked (and purged) by a sweep.
* **Durable and verified.** One new encrypted file; every change commits together with a content-free, hash-chained audit row (types, states, grant id, reason code). Before anything is trusted the record is re-verified: chain, head (detects rolled-back rows), states vs audit, each grant's digest and revoked flag, schema version. Any mismatch (`corrupt`, `downgraded`, tampered, unreadable) makes every grant disappear and every change refuse (`StoreCorrupt`): fail closed.
* **OS permission is evidence, not a flag.** `OSPermissionProvider.current(type)` must return fresh (<= 30 s, not future-dated), positive evidence for exactly that type; a provider error, stale or wrong-type evidence is "unknown" and denies that check. Consent alone, a cached boolean, a UI checkbox or an environment variable is never accepted. A permission that was once evidenced and is then positively reported missing is a **revocation** (grant revoked, derived data purged; a new grant needed later); "unknown" never revokes.
* **Everything is gated:** `DocumentIndex` requires an `AccessCheck` (no default; `AllowAll` is test-only). Start-up (scan), indexing (checked again before every document), search (raises `PermissionRevoked`), reads and `get()` (returns nothing) touch no stored text and no folder byte unless the owner grant and the OS evidence are both current. Model-context construction and the model door are gated by the unchanged `ContextBuilder` / `GatedModel` through the same policy re-validation.
* **Revocation purges.** `register_purge(type, fn)` registers the function that deletes derived data (the document index registers `purge`); it runs after the revocation commits. A purge that fails or never ran leaves a durable `purge_pending`: the source stays revoked, a new grant for that type is refused (`PurgePending`), and `run_pending_purges()` finishes it at the next start.
* **Owner-facing state** (not served): `SourceAccess.consent_state()` returns the 1.1 `ConsentState` shape (grants + `os_access` per designable source), validated in tests.

## Boundaries and limitations (honest)

* No API 1.1 route is served and frozen 1.0 is unchanged. The store's mutators (`apply`, `withdraw`) are Core-internal: **who may call them** (an enrolled owner-interactive client, signed, replay-protected over the wire) is the consent-route package behind 1.1, not built here; an architecture test keeps `api` and `transport` from importing `designation`, `access` or `documents`.
* `request_id` single-use gives replay protection for these calls; it is not client authentication.
* `FakeOSPermissions` is a deterministic CI stand-in. **macOS TCC / Full Disk Access discovery, the real Get Started UI, and FileVault behaviour are not implemented or verified.**
* The Keychain key provider for this store (real data) is WP3.6; tests pass a test-only key.
* Expiry is revoked by a sweep on use, so a denial caused by expiry reports `grant_revoked` (the closed reason enumeration is unchanged) and the audit row says `grant_expired`.

## Rollback

Delete `designation.py`, `access.py`, `tests/test_designation.py`, this file; revert the `access` parameter and gate calls in `documents.py` and the layer/allow-list lines in `test_architecture.py` / `test_tasks.py`. The store is its own file.
