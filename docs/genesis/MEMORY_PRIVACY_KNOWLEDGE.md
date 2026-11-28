# Atlas — Memory, Knowledge and Privacy

**Status:** Target requirements

## 1. Purpose

Atlas memory is a governed, persistent representation of useful context—not an untraceable summary and not a replacement for source records. It should reduce repetition while allowing the owner to inspect, correct, restrict, expire and delete retained information.

## 2. Knowledge layers

Keep distinct records for:
1. **Source artefacts:** original file/message/record identity, source, timestamps, version and integrity metadata.
2. **Extracted observations:** text, tables, OCR, structured fields and extraction metadata.
3. **Facts:** normalised statements with subject, predicate, value, units, temporal validity and confidence.
4. **Entities and relationships:** people, organisations, accounts, places, projects and their links.
5. **Derived conclusions:** summaries, interpretations and recommendations with links to supporting facts.
6. **Conversation context:** session-specific information and explicitly retained durable preferences/decisions.
7. **Operational memory:** job state, user-approved preferences, action receipts and system configuration.

Do not collapse these into a single free-form vector store.

## 3. Provenance and temporal correctness

Every important fact should record, where available:
- Source ID and source version/hash.
- Exact location: page, paragraph, row, timestamp or message.
- Extraction method/model/version and time.
- Original value and normalised value.
- Confidence/verification state.
- Valid-from and valid-until (or unknown).
- Sensitivity and access classification.
- Links to contradictory or superseding evidence.

A newer source does not automatically make an older fact false. Preserve temporal history and distinguish “current”, “historical”, “superseded” and “disputed”.

## 4. Memory lifecycle and owner controls

- Retain useful information automatically only under explicit product policy and configured sensitivity rules.
- Provide owner-visible review and correction.
- Support configurable retention/expiry and user-controlled deletion.
- Propagate deletion to derived indexes, embeddings, caches and summaries, subject to documented legal/technical retention constraints.
- Record deletion completion and any residual copies/backups that expire later.
- Avoid storing sensitive content when a source reference or minimal derived fact is sufficient.

## 5. Sensitive data

Health data is a sensitive domain, separately labelled/keyed and unavailable to Atlas until the owner grants the applicable source and task permissions. Under G-021, the local model may read owner-authorised Health data within that scoped task context. Apply least privilege to tools, retrieval and memory; revoke access and invalidate derived caches immediately when the grant is withdrawn. Do not leak sensitive data into logs, telemetry, prompts for unrelated tasks or non-authorised capabilities.

**Finance is a separately controlled sensitive domain under G-021: owner-authorised Finance records may enter the local model's scoped task context. Keep Finance separately labelled/keyed with scoped grants, provenance, revocation, redacted logs and cache controls. Exact financial arithmetic and balances are deterministic/code-checked; no Finance content enters public web requests, cloud inference, logs or unrelated task contexts. A grant is purpose-bound and revocable.

## 6. Retrieval

Use hybrid retrieval where justified (structured filters, full-text search, semantic search and graph/relationship traversal). The authoritative source depends on the domain: financial calculations query the ledger; source documents remain authoritative for what they state; derived memory helps discovery and context but must link back to evidence.

Retrieval must enforce access controls in the data-access/retrieval layer before results enter model context: the retrieval interface must be unable to return records above the caller's clearance, not merely filter them after retrieval or rely on prompt instructions. Apply the same rule to full-text, semantic, graph, summaries, caches and derived indexes. Search quality is measured for recall, precision, stale/conflicting facts and cross-domain leakage.

## 7. Correction and contradiction handling

Owner corrections should be first-class, attributable records. Do not silently rewrite source evidence. A correction may supersede a derived fact while preserving the prior value and its provenance. Contradictions remain visible until resolved or explicitly accepted as ambiguous.

## 8. Security controls

- Encryption at rest and key handling appropriate to the current threat model.
- Explicit capability-level access checks.
- Separate sensitive partitions/keys where justified.
- No secrets or personal content in logs or source control.
- Prompt-injection-resistant separation between instructions and retrieved data.
- Auditable access to sensitive memory and actions.
- Backup and restore must preserve encryption and deletion semantics.

## 9. Open design work

Storage schema, graph representation, vector index, encryption partitioning, backup/restore, sync and deletion propagation require an implementation audit and ADR. Do not choose a database solely because it is fashionable.


## 10. Agent-scoped memory and context

The workforce does not share an unrestricted universal prompt or memory. Every task receives a minimal, purpose-bound context assembled only after access policy is evaluated. Agent context is scoped to the task, domain, owner permissions and retention policy. A specialist may return a result with provenance to the coordinator without exposing its underlying restricted records.

- Agent scratch context is task-scoped and expires according to policy; it is not automatically promoted to durable personal memory.
- Durable memory writes require the applicable retention and sensitivity policy, provenance, and owner controls.
- Cross-domain retrieval is denied by default unless an explicit policy authorises the specific data flow and purpose.
- Under G-021, the local model may read owner-authorised Finance and Health data only within the exact purpose-bound task grant. Keep each domain separately labelled/keyed with scoped grants, provenance, revocation, redacted logs and cache controls. Exact financial arithmetic and balances are deterministic/code-checked; no private domain content is sent to public search or cloud inference, logged, or exposed to unrelated tasks.
- Agent-to-agent delegation carries a validated typed task-scope structure checked by the central policy engine and no greater permission than the delegating task. Use a signed envelope only when scope crosses a process or trust boundary; in-process calls use validated structures. A child agent cannot broaden its own scope.
- Logs, traces, evaluation datasets and failure reports must not contain source content, secrets or sensitive personal data. Use redacted metadata and synthetic evaluation fixtures.
- Owner inspection, correction, expiry and deletion controls apply to retained agent-derived memory and task artefacts. Deletion propagation must cover source copies where Atlas owns them, full-text indexes, embeddings, caches, summaries, task artefacts and replicas. Backups must follow a documented expiry/crypto-erasure policy; audit logs retain only the minimum non-content evidence needed for integrity. Provide a deletion receipt or verification report without exposing deleted content.
