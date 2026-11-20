# Atlas Stage 3 — Baseline Audit

**Audit status:** Architect-inspected repository snapshot; not a code review or runtime test  
**Audited ref:** `ea4e48f5665055e988d7a04ebb6f27faca95173b`  
**Audit date:** 2026-11-20  
**Purpose:** Establish what exists, what can be reused, and the exact gaps before Stage 3 implementation.

## 1. Executive finding

The repository contains a useful Stage 2 policy/task/evidence foundation and several legacy domain capabilities, but **it does not yet contain the Stage 3 application workflow**. There is no checked-in native macOS app target, no concrete Core document or Mail retriever, no durable source-grant management path, no production local-model adapter, and no end-to-end source-to-cited-answer integration.

This is a repository inspection, not proof that no untracked code exists on a developer's machine. The audited Git tree contains no `.xcodeproj`, `.xcworkspace`, `Package.swift` for an app, or Swift application sources. The only Swift file found is `library/scripts/atlas-ocr.swift`, an OCR script, not an Atlas client.

**Recommendation:** retain Stage 2 Core as the policy/task/evidence reference foundation, build the first vertical slice around its versioned API, and add concrete adapters behind existing protocols. Do not transplant legacy application shells or rewrite Core as part of Stage 3.

## 2. Audited repository facts

| Area | Present at audited ref | Not present / limitation |
|---|---|---|
| Core API | `core/contracts/openapi.yaml`, JSON Schema 1.0, signed request identity, task create/read/cancel/answer/receipt/events | No source-status or grant-management routes; no API 1.1 delta yet |
| Core policy | Default-deny `PolicyEngine`, grant protocol, in-memory grant implementation, sensitivity ceilings, revocation revalidation | No durable grant repository or Get Started-to-grant provisioning path; Finance and Health are hard-denied by current rules |
| Retrieval | `Retriever` protocol and `GatedRetrieval`; policy checked before each source read | No concrete Core document or Mail retriever in `core/src`; no production source inventory |
| Evidence | Exact hash/version, spans, page/block/message-part locator validation | No real document parser provenance adapter; no real Mail locator adapter |
| Model | `ModelGateway` protocol, context builder, gated model boundary | No real MLX adapter, model selection/router, answer model identity, or target-Mac measurement |
| Tasks | Durable encrypted task store, checkpoints, idempotency, cancellation, recovery, safe events | No integrated ingestion/indexing worker or end-to-end app workflow |
| Client | Legacy browser UI exists under `atlas/src/atlas/static` | No native Atlas macOS client in audited tree; legacy UI is not accepted as the target client |
| Document processing | Legacy extraction and SQLite FTS/RAG helpers in `kit`; ingestion design docs | Not wired into Core; provenance/security/format behaviour needs audit before reuse |
| Mail | Mail appears in policy and target requirements | No Core Mail connector, local Mail-store adapter or message citation integration |
| Attachments | `mail_attachment` source type is explicitly deferred by G-O18 | No accepted attachment format matrix/parser package; content must remain unavailable |
| CI | Stage 2 test suites and architecture/contract tests | CI is not evidence of macOS, MLX or real-source behaviour |

## 3. Exact implementation map

### 3.1 Stage 2 Core — retain and extend behind contracts

- `core/contracts/openapi.yaml` and `atlas-contracts.schema.json`: language-neutral API 1.0 source of truth.
- `core/src/atlas_core/api.py`: signed request verification, version negotiation, route dispatch and response validation.
- `identity.py`: client registry, signature, nonce and replay/freshness checks.
- `policy.py`, `rules.py`, `policy-rules.json`: source grants, sensitivity, default-deny decisions and current-grant revalidation.
- `gate.py`: the only retrieval and model doors; `PermitToken` and `ModelContext` are minted under policy.
- `service.py`: task pipeline coordinating policy, retrieval, model, evidence verification and durable state.
- `evidence.py`: immutable text hash and exact page/block/message-part/span citation validation.
- `answer.py`: answer envelope and deterministic citation/figure/date checks.
- `tasks.py`: encrypted task persistence, checkpoints, cancellation and recovery.
- `events.py`: allow-listed, redacted operational events.

These are reference implementations with synthetic tests. Reuse is conditional on the Stage 3 threat model and contract delta; do not describe them as production source connectors.

### 3.2 Current policy conflict that must be resolved before real data

The product baseline (G-021 / PRD §10) allows the local model to read owner-authorised Finance and Health data under separate labels/stores, scoped grants, provenance, redaction, revocation and cache controls. The current Stage 2 implementation still lists `finance` and `health` in `restricted_domains` in `core/src/atlas_core/policy-rules.json`, and `PolicyEngine._judge` returns `restricted_domain` before it considers a grant.

That is a deliberate Stage 2 restriction, not the current product policy. Stage 3 must replace it with the G-021 grant model **before** any such data is made available. Tests must prove default-deny, owner-grant scope, domain separation, revocation, no cross-domain cache/context leakage, redaction and no egress. No real Finance or Health records may be used in CI. Do not simply remove the restriction without adding the replacement controls.

### 3.3 Legacy code — candidate reuse only

- `kit/src/kit/rag.py` contains SQLite FTS5 indexing, passage chunking and incremental refresh concepts.
- `kit/src/kit/extract.py` contains document classification and deterministic checks against printed amounts/dates, plus medical extraction helpers.
- `kit/src/kit/db.py` contains SQLCipher support and legacy per-domain database conventions.
- `library/` contains existing document/OCR utilities; inspect exact parser support and provenance before selecting any.

These components are not currently wired through Core's `Retriever`, `SourceStore`, or `ModelGateway` protocols. The legacy RAG comments describe a Finance-specific flow and must not be treated as a safe general-purpose index. Reuse algorithms only after auditing data ownership, access checks before reads, source/version identity, locator fidelity, parser isolation, incremental correctness and restart behaviour. Never migrate, rename, delete or consolidate existing stores in this stage.

## 4. Stage 3 work package dependency map

| Package | Entry point / target | Required output | Dependency |
|---|---|---|---|
| WP3.0 Baseline | This audit; Core, kit, library, atlas trees | Requirement-to-code map and reuse decisions | Complete as repository inspection |
| WP3.1 Contracts/security | Core API/schema, policy, grants, evidence, events | Additive API 1.1 proposal, threat model, fixtures and tests | Before real source reads |
| WP3.2 Documents | New Core document adapter, parser interface, index worker | Progressive local document retrieval with exact locators | WP3.1 accepted |
| WP3.3 Mail | New Core Mail adapter and message source model | Read-only message/body/header retrieval and exact citations | Get Started grants + OS access; attachments remain separate |
| WP3.4 Intelligence | ModelGateway adapter, routing descriptor, verifier | Local MLX path and safe model identity | Contract + policy gates; Mac for actual MLX |
| WP3.5 macOS client | New native SwiftUI app target | Conversation, progress, cancellation, citations, source status | Stable API delta; Mac/Xcode |
| WP3.6 verification | Core, adapters, client and CI | Adversarial, recovery, quality and performance evidence | Incremental; target-Mac gates remain pending |
| WP3.7 acceptance | Exact final commit and evidence | Architect recommendation and owner acceptance brief | All required gates |

## 5. Non-negotiable design constraints

1. All reads, retrieval, cached passages and model calls pass through Core policy. UI permissions are not enforcement.
2. Documents and Mail are independent source-type grants. One Get Started flow plus OS permissions; no per-folder prompts or repeated incidental consent.
3. Finance and Health remain separately labelled/keyed and purpose-bound under G-021; no private content in public search, third-party services, model logs or CI.
4. Mail body, stored headers, thread context and attachment content have distinct provenance and coverage. Attachments stay denied until G-O18 acceptance.
5. Every personal-data claim has a resolvable source/version and exact locator. Invalid, stale or mismatched citations fail closed.
6. Progressive newest-first indexing is model-free at tier 1. Mail order uses stored received time; files use modification time, retaining content-created time separately. Coverage must be visible.
7. No silent truncation, unsupported-format skip, guessed timestamp, false completion or invented citation.
8. No cloud inference or silent fallback. Public web research is through the Core egress gateway and cannot receive private source content.
9. No autonomous source-code changes, destructive migration, store consolidation, legacy retirement, remote exposure or external write actions.
10. Stage 2 API 1.0 remains frozen. Add compatible API 1.1 contracts; do not reinterpret old fields or silently widen old clients.

## 6. Mac-independent versus Mac-dependent evidence

**Can be implemented and tested without the owner's Mac:** contract/schema validation, fake source adapters, deterministic extraction fixtures, FTS indexing logic, grant and revocation tests, evidence locator validation, injection tests, redaction sentinels, egress fakes, task recovery, cancellation, idempotency, synthetic quality evaluation and CI.

**Requires a real Mac:** Xcode/SwiftUI build and app lifecycle; macOS TCC permissions and local Mail access; Keychain provisioning and unlock behaviour; actual MLX model loading/routing; sandbox/network entitlements; FileVault/reboot/update behaviour; signing/notarisation; target hardware latency, memory, thermal and energy tests.

A Linux pass is not a Mac pass. Each evidence item must be labelled CI-verified, developer-reported, architect-inspected or owner-verified.

## 7. Stop conditions discovered by this audit

- Do not connect Finance or Health until the G-021 replacement policy and tests exist.
- Do not expose Mail attachment text until G-O18 technical acceptance.
- Do not claim a native app exists; none is present in the audited tree.
- Do not claim MLX works; there is no real adapter or Mac evidence.
- Do not use legacy RAG/indexes directly as a Core retriever before a security/provenance audit.
- Do not start real-source reads before a durable grant mechanism and Get Started/OS permission path are accepted.
- Do not make the existing legacy app/database a single source of truth or perform a destructive migration.

## 8. Audit conclusion

**WP3.0 repository inspection is complete at the audited ref.** The largest implementation gap is not model choice: it is the absence of a concrete, policy-governed source-to-evidence path and native client. The correct first engineering move is WP3.1: freeze the source/grant/evidence/model metadata contracts and their security tests, then implement the document-only vertical path. Mail, attachments, Finance/Health real-data access, and target-Mac model/client verification follow their explicit gates.
