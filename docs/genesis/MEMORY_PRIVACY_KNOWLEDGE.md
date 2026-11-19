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

Health data is locked by default. Highly sensitive categories must be isolated by policy and require explicit permission before access or retention beyond the minimum necessary. Apply least privilege to tools, retrieval and memory. Do not leak sensitive data into logs, telemetry, prompts for unrelated tasks or non-authorised capabilities.

## 6. Retrieval

Use hybrid retrieval where justified (structured filters, full-text search, semantic search and graph/relationship traversal). The authoritative source depends on the domain: financial calculations query the ledger; source documents remain authoritative for what they state; derived memory helps discovery and context but must link back to evidence.

Retrieval must enforce access controls before results enter model context. Search quality is measured for recall, precision, stale/conflicting facts and cross-domain leakage.

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
