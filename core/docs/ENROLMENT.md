# Owner enrolment (first run) and client roles

Requirement: only an enrolled, authenticated owner client may change settings and source grants (TARGET_ARCHITECTURE.md; HANDOVER.md). The Core, not the UI, decides (signed request, fresh, single-use nonce, audited change). This page records the first-run flow that makes that usable without any manual step. It is an engineering decision within the delegated authority, recorded here and on PR #8 for the architect to confirm; it is **tested on Linux with the Python reference client; the Swift side is unverified**.

## Flow
1. The app creates a random client id and an Ed25519 key (Keychain on a Mac) and keeps the private key there. Nothing secret is ever sent.
2. First run, while the Core has **no owner client**: `POST /v1/enrol` (API 1.1 only) with `{client_id, public_key (32 raw bytes, base64), role: "owner"}` is accepted **unsigned**, once. It still arrives over the Core's owner-only Unix socket (folder 0700, socket 0600, peer user id checked by the transport), so only a process of the owner's own account can reach it. The check and the write are one step under one lock: of any number of racing callers exactly one becomes the owner client.
3. From then on the window is closed for good (also after a restart: the registry is persisted, mode 0600, public keys only). A second unsigned enrolment gets `unauthenticated`.
4. An enrolled owner client may enrol further clients with a **signed** `POST /v1/enrol`, only as `member` (it can ask questions and read index counts; it cannot read or change consent, and cannot enrol anyone). An owner client cannot mint another owner client. A taken id is `conflict`.
5. Consent routes remain owner-only (`/v1/consent`, `/v1/consent/{grant_id}`); the signed request's nonce is the single-use request id of every consent change.

## Threat model and limits
- What this stops: another user account, a remote host, a browser page or any non-owner process without the socket; a second enrolment racing or following the first; a member escalating; a key changing silently (re-enrolment of an existing id is refused).
- What it does not stop: **another process running as the same user that reaches the socket before the app does on first run** can enrol itself as the owner. That is the same trust boundary as the owner's own account (such a process can already read the owner's files), and the window is one-time; closing it further needs a platform-attested app identity (code-signing requirement checked on the peer), which is a Mac packaging item (G-O12) and is **not built**.
- Revocation: a revoked client is refused everywhere (`forbidden`); re-opening the first-run window after revoking the only owner is **not** implemented (the owner would need to reset the data folder); recorded as a limitation.
- iOS and remote devices: Stage 8 (G-O14/G-O15). Nothing here is remote enrolment.

## Evidence
`tests/test_enrolment.py` (17 tests; mutation checks: the lock-level one-owner rule, member-only rule, file mode), `tests/test_consent_api.py`. Swift: `app/Sources/AtlasApp/AtlasApp.swift` (`KeyStore.identity`, `ConversationModel.refreshConsent`) and `CoreClient.enrolSelf`, **never compiled or run**.
