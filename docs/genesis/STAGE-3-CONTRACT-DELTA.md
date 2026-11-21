# Atlas Stage 3 — Contract Delta and Security Test Specification

**Status:** SUPERSEDED historical proposal; not an implementation contract. For WP3.1, `core/docs/CONTRACT_1_1.md` and its linked schema/OpenAPI files are authoritative.  
**Baseline:** Stage 2 API 1.0 at `ea4e48f5665055e988d7a04ebb6f27faca95173b`  
**Compatibility rule:** API 1.0 remains frozen. The approved WP3.1 API 1.1 specification is documented in `core/docs/CONTRACT_1_1.md`; this older proposal must not be used to implement routes, events, schemas or coverage.

> **Supersession notice (2026-11-20):** This document predates the owner-approved WP3.1 v4 proposal and conflicts with the implemented WP3.1 specification. It is retained as historical design rationale only. Do not implement its proposed `/v1/sources/*` routes, `model.route` event, `routing_role`/runtime-version fields, or per-source coverage object. The authoritative WP3.1 surface is `GET/POST /v1/consent`, `DELETE /v1/consent/{grant_id}`, `GET /v1/index/status`, `model.routed`, the closed `ModelDescriptor` (`model_id`, `role`, `runtime`), and `Coverage` on each answer, as specified in `core/docs/CONTRACT_1_1.md`. That document also explicitly states that WP3.1 is specification-only and the Core does not yet serve API 1.1. Any future change requires a versioned contract update and review.

## 1. Historical design decisions (not implementation authority)

1. Keep Core as the only policy authority. The client may display source status and initiate owner actions but cannot grant itself access.
2. Keep source grants source-type scoped (Documents, Mail, Finance, Health); no per-folder grants and no repeated prompts. One Get Started flow plus macOS permission prompts establishes the initial source scope.
3. Documents and Mail are independent grants. Mail body/headers/thread and attachments have distinct provenance and availability; attachments remain denied until G-O18 passes.
4. Finance and Health are available to the local model only under current owner grants, separately labelled/keyed stores, purpose-bound access, provenance, redaction, revocation and cache invalidation. This replaces the Stage 2 hard-deny rule only after the complete tests in §8 pass.
5. Every model call, including a route switch, passes through the same Core policy gate. Model identity may be disclosed; prompts and personal content never appear in route events.
6. The first slice is read-only for external side effects. Approval policy remains the closed list in PRD §4.4; this contract adds no new approval category.
7. The first useful index is model-free, progressive and newest-first. Every answer discloses coverage; partial is never represented as complete.

## 2. API version 1.1 — proposed additive surface

The following is a contract proposal, not a claim that these routes or fields exist.

| Operation | Proposed route | Purpose | Security |
|---|---|---|---|
| Read source coverage | `GET /v1/sources/status` | Per-source-type enabled/denied state, indexed/searchable/pending/unsupported/failed counts and last progress | Signed owner-client request; no source names, subjects or private content in logs |
| Read current source grants | `GET /v1/sources/grants` | Return source-type grant state, scope, purpose, expiry and revocation state | Signed owner-client request; never expose credentials |
| Establish initial source grants | `PUT /v1/sources/grants/{source_type}` | Apply the one-time Get Started decision for a supported source type | Owner-client authority required; idempotent; audited; OS permission state separately verified |
| Revoke a grant | `DELETE /v1/sources/grants/{grant_id}` | Immediate revocation and cache/index access invalidation | Owner-client authority required; idempotent; audit contains IDs/codes only |
| Create/read/cancel task | Existing `/v1/tasks` routes | Preserve API 1.0 task lifecycle | Existing signed-request rules |

The grant endpoints must not accept arbitrary source paths or folder lists. The source type is an allow-listed policy identifier. The Core validates owner-client identity, signature freshness, nonce/replay, current authority and allowed transition. A revoked grant must be effective before the next source read and before every model call. A client cannot elevate its own authority by claiming a UI state.

### 2.1 Grant lifecycle

- Grant records are durable, encrypted and separate from source content and connector credentials.
- A grant identifies `grant_id`, `source_type`, `purpose`, `max_sensitivity`, `designated_by=owner`, `issued_at`, optional `expires_at`, `revoked`, and policy/schema version.
- Default is deny, including after a crash, restore, missing Keychain item or permission reset.
- Grant creation is idempotent for the same owner decision; conflicting scope requires a new explicit owner decision, not silent overwrite.
- Revocation is monotonic for that grant ID. Re-enabling creates a new grant ID.
- The first-run flow is one consent step for the source types the owner selects; Core stores separate grants. macOS TCC permissions are independent system gates. A missing/revoked OS permission produces a visible unavailable state, never a repeated Atlas prompt.
- No grant or OS permission is inferred from the presence of files or a connected account.
- Health and Finance grants are distinct, explicitly scoped, and never inherited by Documents or Mail tasks.

### 2.2 Source coverage response

Proposed shape (illustrative; final JSON Schema must use the repository's conventions):

```json
{
  "source_type": "documents",
  "access": "enabled",
  "permission_state": "available",
  "index_state": "partial",
  "total": 1400,
  "searchable": 320,
  "pending": 1040,
  "unsupported": 20,
  "failed": 20,
  "last_progress_at": "2026-11-20T20:00:00Z"
}
```

Counts must be computed from durable source/job state, not guessed. Unknown totals remain null/unknown and progress is indeterminate; do not fabricate a percentage. File ordering uses filesystem modification time; content-created time remains separate metadata. Mail ordering uses stored received timestamp. Missing timestamps use a deterministic stable fallback and increment a visible missing-timestamp count.

## 3. Answer and model-route metadata

### 3.1 Answer envelope addition

Add an optional API 1.1 `model` object to the answer envelope:

- `model_id`: stable model identifier, not a prompt or personal value.
- `routing_role`: controlled role such as `fast`, `main`, `reasoning`, `vision`, or `embedding`; final enum must be agreed with model router.
- `runtime`: `mlx` for the selected local runtime.
- `runtime_version`: optional runtime version.
- `model_revision`: optional immutable model revision/hash where available.

Do not include prompt text, retrieved text, filenames, source IDs, user query, credentials or free-form private context. The UI shows the model ID and role. If model identity is unavailable, state that honestly; do not invent it.

### 3.2 Safe route event

Add an allow-listed `model.route` safe event with only task ID, route sequence, model ID, role, runtime, runtime version, and a fixed reason code. No prompt, output, source identifier, personal content, arbitrary URL or model-generated string. Route changes must be emitted after policy revalidation and before generation. Every route invokes the same `GatedModel` policy path; no adapter is allowed to call MLX directly from a feature module.

### 3.3 Streaming and cancellation

- Reuse the durable task/event stream; do not introduce a second progress channel.
- Keep safe operational events separate from user-visible answer deltas. Deltas may contain answer text; they must never contain source passages or prompts by default.
- Cancellation is cooperative at source, parser, retrieval, model and verification boundaries. Persist the cancellation request and final state.
- A permission revocation during generation stops further model work and withholds any answer built from the revoked source, including uncited passages.
- Reconnect uses the existing event sequence cursor; no duplicate event delivery or progress regression.

## 4. Evidence and source provenance contract

The existing `EvidenceRef` has a source ID/type, content hash, locator and character span. Retain it and add a source manifest/provenance record that the UI can use to open the exact item without placing private names in operational logs.

Required source manifest fields:

- opaque stable `source_id`;
- source type and sensitivity label;
- provider/connector type (fixed enum);
- opaque provider item identity;
- immutable content version/hash;
- ingestion/parser version;
- observed and modified timestamps (nullable and semantically distinct);
- extraction state: complete, partial, unsupported, corrupt, encrypted, needs_attention;
- locator map and character-offset coordinate system;
- source deletion/revocation status.

Locator rules:

- Documents: exact page when available; otherwise stable block/section plus span. Preserve page boundaries through OCR/extraction. Never label a span-only citation as a page citation.
- Mail: cite exact message identity, stored header fields and body span. Sender/date must come from stored message metadata, not inferred from body text. Thread context is a separate locator.
- Attachments: separate source identity/version and locator from the parent Mail message; unavailable until G-O18 acceptance.
- Every citation resolves against the exact stored source version. Changed source/parser output invalidates old citations until re-indexed and re-verified.
- A citation must be among the passages retrieved for that task and its quoted text must match the resolved span exactly.
- Source display names and paths are only returned to an authenticated UI when needed; never include them in safe events, error strings or general telemetry.

## 5. Retrieval and progressive-index contracts

### 5.1 Adapter boundary

Define concrete adapters behind the existing Core protocols:

- `DocumentSourceAdapter`: enumerate only owner-authorised local document roots; read metadata; hand bytes to isolated parsers; preserve identity/version/locators.
- `MailSourceAdapter`: enumerate/read only when Mail grant and OS permission are current; body/header/thread are distinct parts.
- `SourceStore`: resolve immutable source versions and locators; no adapter can bypass the policy gate.
- `IndexRepository`: persist source version, parser version, tier, checkpoint, completion and coverage counters.
- `LocalModelGateway`: the sole adapter behind `GatedModel`; no network capability and no direct calls from UI or source adapters.

The adapter interfaces should accept a validated task-scoped permit/capability rather than a boolean such as `allowed=true`. A raw filesystem path or Mail identifier must never be sufficient authority.

### 5.2 Index tiers

- Tier 0: inventory/metadata only, no content reads before source grant and OS permission.
- Tier 1: model-free full-text extraction/indexing for supported formats; newest-first; searchable as soon as each source is durably committed.
- Tier 2: optional richer extraction/semantic enrichment, only after tier 1 works and the resource budget is measured.
- Attachments: a separate pipeline and status, never silently included in Mail body coverage.

Coverage must report total, searchable, pending, unsupported, failed, needs-attention and missing timestamp counts. Each source has durable per-stage checkpoints and a source-version fingerprint. Restart resumes without duplicate passages or falsely completing a stage. A corrupt file cannot block unrelated files. A source change invalidates only dependent outputs.

## 6. Egress, parser and model isolation

- Model worker has no network at the OS boundary; verify this on macOS. Linux tests use a deny-all network fake and assert no socket/HTTP call path.
- All public web requests pass through the Core egress gateway. When a task context contains private data or untrusted content, only typed search/fetch tools and returned/allow-listed URLs are available; no model-composed arbitrary URL, custom header, cookie, subdomain or redirect bypass.
- Apply URL/query/path/header length caps, redirect revalidation, DNS/private-IP/rebinding checks, and leak sentinels for exact/long substrings, hashes and encoded/high-entropy payloads. Record blocked attempts as redacted reason codes. Plain-language paraphrase exfiltration cannot be perfectly detected; Finance/Health-touched tasks must use restricted query templates or block unsafe free-text queries.
- UI never auto-loads remote images, previews, embeds or markdown resources from model output. Links open only on explicit click and show the destination.
- OAuth callbacks bind to loopback or a Unix socket only. No public listener.
- Parser workers are isolated, resource-limited, timeout-bounded and unable to access credentials, unrelated files or network. Malformed, encrypted, oversized and decompression-bomb inputs fail visibly; no silent skip.
- Credentials are Keychain-held and never sent to model context, logs or search queries.

## 7. Error and lifecycle states

Use stable machine states and plain-language UI messages for:
- denied before search (`not_searched`);
- search attempted but no durable passages confirmed (`attempted`);
- source content retrieved and persisted (`confirmed`);
- partial extraction/indexing;
- unsupported, corrupt, encrypted, unavailable permission, revoked grant;
- model unavailable (no cloud fallback);
- citation stale/unresolvable;
- cancelled, needs-attention, failed, completed.

Never conflate “search attempted” with “content retrieved”. Do not show a green completed state if any required source is pending/unsupported/failed. Partial answers state exactly what was and was not searched.

## 8. WP3.1 security and contract acceptance matrix

All tests below use synthetic content and fake connectors unless explicitly marked Mac-only.

| ID | Test | Required result |
|---|---|---|
| C-01 | API 1.0 compatibility snapshot | Existing 1.0 requests/responses remain byte/schema compatible for supported paths |
| C-02 | Unknown source type / missing grant | Denied before adapter read; zero read calls |
| C-03 | Documents grant without Mail grant | Documents searchable; Mail untouched |
| C-04 | Mail grant without Documents grant | Mail searchable; Documents untouched |
| C-05 | Revoke during queued task | No source read after revocation; task stops honestly |
| C-06 | Revoke between two source reads | Second source is not read |
| C-07 | Revoke after retrieval, before model | Model receives no protected context |
| C-08 | Revoke after draft, before answer/stream | Answer and future stream withheld |
| C-09 | Finance grant absent | Finance untouched and denied |
| C-10 | Finance grant present | Only permitted Finance records enter the labelled Finance task context; no cross-domain leakage |
| C-11 | Health grant absent/present | Same default-deny and scoped-grant properties as Finance |
| C-12 | Cross-domain cache/index collision | No record returned under another domain/source grant |
| C-13 | Forged/replayed/stale owner-client mutation | Grant create/revoke refused and audited without content |
| C-14 | Mail body asks to search more or send data | Treated as untrusted data; no scope or action change |
| C-15 | Quoted/forwarded sender spoof | Sender/date taken from stored headers only |
| C-16 | Citation references wrong source/version/page/span | Citation rejected; answer fails closed |
| C-17 | Parser corrupt/oversized/encrypted input | Visible needs-attention; no silent completion or data loss |
| C-18 | Crash after source read before checkpoint | Report attempted, not confirmed; restart does not duplicate or overstate |
| C-19 | Model route changes during task | Policy gate re-run; safe route event contains metadata only |
| C-20 | Model worker attempts network | Denied by test harness; Mac OS-level enforcement separately verified |
| C-21 | Model output includes remote image/link preview | No automatic network fetch by UI |
| C-22 | Cancellation at every stage | Durable cancelled state; committed work retained; no later model call |
| C-23 | Coverage denominator unknown | Indeterminate state; no invented percent or total |
| C-24 | First useful tier before full corpus | Search works against committed tier-1 subset and visibly reports remaining coverage |

**Mac-only acceptance:** actual TCC prompt behaviour, Mail access, Keychain grant persistence/revocation, process sandbox/network denial, SwiftUI client lifecycle, MLX loading and target-Mac benchmarks. A Linux fake is not a substitute.

## 9. Implementation order and handoff

1. Claude challenges this contract delta and the baseline audit against the exact branch head. Report contradictions, missing tests, feasibility risks and any necessary owner decision. No code during challenge.
2. ChatGPT reconciles and freezes the WP3.1 schema/API proposal.
3. After explicit Stage 3 authorisation, Claude implements WP3.1 contracts/tests only; ChatGPT reviews exact commit.
4. Implement WP3.2 document-only adapter and tier-1 index with synthetic fixtures.
5. Integrate the minimal native macOS client once a Mac/Xcode environment is available; meanwhile keep the API and UI contract testable on Linux.
6. Enable Mail only after Get Started/OS grant tests; attachments remain separately gated.
7. Enable Finance/Health only after their G-021 store, grant, cache and redaction tests pass.
8. Add MLX only behind the model gateway; choose the exact model/quantisation after target-Mac benchmark.
9. Run exact-head CI and present a bounded owner acceptance brief. No merge/release or destructive migration is implied.

## 10. Open technical choices (do not guess)

- Concrete local document roots and exact supported file-format matrix.
- Parser implementation per format and isolation mechanism.
- Mail provider path (Apple Mail local store vs another supported connector) and exact OS permission behaviour.
- Durable grant-store location/key lifecycle and owner-client role semantics.
- API 1.1 final endpoint and schema naming after challenge.
- Index persistence layout and whether legacy FTS5 can be reused safely.
- MLX Swift versus MLX Python adapter for the first release; compare same model candidates and workloads on target hardware. Apple's MLX ecosystem supports Swift and Python, so choose by measured integration, packaging, performance and maintainability rather than assumption. See Apple's MLX sessions and upstream MLX Swift documentation.
- Model ID, routing roles, quantisation, context budget and fallback policy.
- Native app packaging and update mechanism (G-O12).

No unresolved choice may be silently converted into a hard-coded assumption or a cloud dependency.
