# Architecture: one personal platform, many private modules

Status: **proposed reference** (the rules every change is held to). Where today's code differs, section 12 says so. Change a rule only with an ADR (`docs/adr/`).

## 1. What we are building
One product that tracks everything personal (finance, photos, health, travel, whatever comes next) with **one address, one chat, one document intake and one local AI model**, while every domain keeps **its own data, rules and tools**.

> Shared platform, isolated modules. The model understands and explains; tools do the work; originals are never changed.

It is one *product*, not one *process*: Atlas (the shared page and platform services) plus one service per module, each in its own container with its own database. A fault, a bug or a leak in one module cannot reach another.

## 2. Principles
1. **One shared AI model**, reached only through one gateway (one request at a time on an 8 GB Mac; priority: chat, then intake, then indexing). Specialised models (CLIP, faces, OCR) are tools inside their module, not "the AI".
2. **One router, one chat.** Cross-module questions go through the platform; modules never call each other and never read each other's database.
3. **Separate domain databases and tools.** One database per module, one writer per database, no cross-database joins. The platform owns a small core database (artifacts, entities, events, reminders, chat, audit).
4. **Tools do the actual work.** SQL, Python and specialised readers compute every figure, filter, date and total. See section 3.
5. **Simple requests bypass the AI** for speed. The fast path passes the same answer checker as the AI path and keeps working when the model is down.
6. **Originals are read-only and kept as received** (content-addressed vault; photos stay in place). Derived data lives elsewhere. The AI never modifies source data.
7. **Every fact has a receipt**: source artifact, page or line, which reader, and verified or not. A figure that cannot be proven is reported as such, never guessed.
8. **Every answer is checked**: each figure and claim shown to you traces to a tool result.
9. **Retrieved text is data, never instructions.** Writes and deletes need your own words in the chat.
10. **Offline always.** No network egress except declared local addresses, enforced in code and in the container.
11. **Sensitivity tiers.** Health (and any later tier-3 module) is locked by default, has its own key, and stays out of search and chat until unlocked. Each chat has a scope.
12. **Idempotent and recoverable.** Imports never double-count; every database upgrade is versioned, backed up first and reversible.
13. **Degrade, never cascade.** A module or the model being down leaves everything else working.
14. **Logs never contain your content.**
15. **If a test or a CI gate does not enforce a rule, it is not a rule.**

## 3. AI usage policy: when, where and how much
The ladder, cheapest and most reliable first. Use the lowest rung that does the job.

| Rung | Use it for | Never for |
|---|---|---|
| 1. Code / SQL | Figures, totals, balances, filters, dates, currency, units, duplicate detection, proofs, permissions, fast-path answers to recognised questions | (always allowed) |
| 2. Specialised tool | EXIF, CLIP, faces, OCR, PDF engines, table readers, barcode, geo lookup | language tasks |
| 3. RAG (retrieval) | Unstructured text only: documents, notes, extracted passages. Hybrid: full-text (BM25) with the assistant's own alternative phrasings and word-ending matching, fused by rank. Every passage shows its source. "The files do not say" is a valid answer | the ledger, anything a query can answer |
| 4. One model call | Understanding a request into a validated structure, choosing the module, classifying a document, explaining results in plain words | producing any figure |
| 5. Agent loop | Open questions needing several tool calls or retrieval retries (the documents agent searching, rephrasing and opening the best file). Least-privilege tools per module agent, max steps, a deadline, output audited | figures, filters, dates, deletes, anything with a deterministic answer |

How much:
- **Fast path** (recognised question, a deterministic intent matches): code answers, no model, target under 1 second.
- **AI path**: target 10 seconds, hard limit set in settings (default 30), then the code fallback or an honest "needs more than I can do in that time".
- **Cross-module questions** use fixed lenses (Trip, Person, Month, Place). Code joins the results through the link book; the model only parses the request and explains. Free-form multi-step planning by a 3B model is not relied on.
- **Document intake**: the model classifies and describes layout; code reads every figure; proofs (balances, totals, a second independent reading, cross-checks such as ticket against payment) decide. A file that fails is left out and shown in the review queue.

| Task | Rung |
|---|---|
| "How much did I spend in September?" | 1 (fast path) |
| Total, savings rate, net worth, gain or loss, interest | 1 |
| Read a new bank's PDF | 4 (layout) + 1 (figures) + proofs |
| Sort a merchant into a category | rules first (1), model for the leftovers (4) |
| Find photos of "Amma at the beach" | 2 (CLIP, faces) + 1 (filters) |
| "What does my insurance cover?" | 3 + agent (5) + 4 to explain |
| "Get me everything about my India trip 2026" | 4 to parse, 1 to join, tools in each module, 4 to summarise |
| Delete something | only on the user's own words; never from retrieved text |

## 4. Services
```
Browser -> Atlas (page, menu, search, chat button, theme)         http://atlas.localhost:8000
              |-- Assistant      router, planner (lenses), fast path, answer checker
              |-- AI gateway     the one model: queue, time limits, safety rules
              |-- Intake         the one document processor (no network, read-only inputs)
              |-- Core DB        artifacts, entities, events, reminders, chat, audit
              '-- Modules        finance, photos, health, travel ...  (own container, own DB, own key)
```
Atlas talks to a module only through the module contract (section 6). Modules depend on the shared `kit`, never on each other.

## 5. Data
```
core.db     artifacts, extractions, passages (FTS5), classifications, deliveries (outbox),
            entities + entity_aliases + entity_links (the link book), events (timeline),
            reminders, conversations, messages, tool_calls, audit_log (hash-chained)
<module>.db domain tables only; every row carries artifact_id + locator into core
vault/      content-addressed originals, mounted read-only. Photos stay in place (path + hash).
```
Conventions: ULID ids; money as integer minor units plus ISO currency (original currency by default); times in UTC with the original zone kept; imports keyed by artifact hash plus line hash; soft deletes only for derived data; WAL mode; versioned migrations per module with an automatic backup; CHECK and foreign-key constraints wherever the database can hold them.

**One pipeline for everything that arrives** (PDF, CSV, photo, health export, ticket, note):
`capture -> vault -> identify (type, hash, duplicate?) -> extract (several engines must agree) -> understand (classify, entities) -> deliver to module(s) -> the module verifies and stores, or says "needs a check" -> index, link, remind`.
A module never trusts the router: finance still proves balances. A misrouted file lands in the review queue, not in your numbers.

## 6. Module contract (v1 today, v2 target)
- v1 (implemented in Orbit and Lumo): `GET /api/health`; `GET /api/search?q=`; `GET`/`POST /api/scan` (the one Update button: start reading everything new, report progress, summary, problems, items needing a check); routes as `#/<page>`; embed messages; one manifest file in `atlas/modules.d/`.
- v2 (target): `GET /api/manifest` (pages, icon, accent, contract version); `GET /api/tools` (name, JSON schema, **read or write**, **sensitivity tier**); the standard `items_in_window(start, end, place?)` returning `{module, kind, title, when, where, amount?, ref, artifact_id?}`; `GET /api/entities` (people, places, trips this module knows); `GET /api/feed` (what needs a look); `accepts` (which artifact kinds the module can ingest); all calls signed by the platform (section 7).
- Any module that implements `items_in_window` appears in every lens (trip, month, person) with no change to Atlas.

## 7. Security
Threat model.
- **In scope:** hostile files (prompt injection, parser exploits), other programs or web pages reaching local ports, DNS rebinding and CSRF, bugs that corrupt data, leaks through logs or outbound calls, dependency compromise, the model inventing figures, one domain leaking into another.
- **Out of scope (decided):** theft or loss of the computer, other users, remote access. Consequence: someone using the logged-in Mac can open everything unless a tier is locked. Default: finance and photos open; health locked each session. Revisit by ADR.

Controls (each has a test or a CI gate):
- Containers: non-root, read-only filesystem, all capabilities dropped, `no-new-privileges`, resource limits, internal networks; the intake reader has no network; only Atlas publishes a loopback port.
- Service-to-service: requests signed by the platform (per-module secret, timestamp, scope). A module rejects any caller that is not the platform, so a local program cannot bypass Atlas.
- Egress: denied by container network and by code; a CI test fails if a networking library appears outside the gateway.
- At rest: every database encrypted (per-module key in the Keychain, no typing); the health tier has its own key and lock; backups encrypted; documented key rotation.
- Web: strict CSP without inline styles, host and origin checks, custom-header CSRF check, framing only by Atlas.
- Parsers: size, time and memory caps; no network; file contents never executed; XML entities refused; fuzzed in CI.
- AI: retrieved text is data; tool scopes (read or write, sensitivity) enforced by the platform, not the prompt; deletes need the user's words; a red-team corpus of injection attempts runs on every change; the gateway cannot fetch URLs.
- Privacy: logs hold events, never content; the audit log is hash-chained; per-module export and erase.
- Supply chain: hash-pinned dependencies, images pinned by digest, `pip-audit`, `bandit`, secret scanning, SBOM; no third-party runtime code in the browser.

## 8. Reliability and performance
- Imports are transactional and idempotent; deliveries use an outbox with retries and a dead-letter queue.
- Start-up integrity checks, daily backups that are verified by restoring, hash checks on the vault.
- Timeouts and circuit breakers on every module call; a module's failure is shown, not propagated.
- Targets: fast path under 1 s, AI path 10 s (hard limit configurable), page loads under 300 ms on 60,000 payments and 100,000 photos (load tests on synthetic data).
- Chaos test: kill a module and the model mid-request; the rest must keep answering.

## 9. Engineering standards (enforced)
- Types: `mypy --strict` for all Python; JavaScript checked with `tsc --checkJs` and split into modules.
- Style and complexity: ruff with the broad rule set, cyclomatic complexity at most 15, Prettier and ESLint, no file or function that cannot be read in one sitting.
- Tests: coverage gate per package; property-based tests for money and parsing; differential tests for refactors; mutation testing on money and proof code; contract tests for every module; fake-model tests for the assistant.
- Architecture tests (import-linter): modules do not import each other; only the gateway touches the network; the browser code has no third-party imports.
- Process: ADR per decision, conventional commits, required CI checks, one `make verify` that runs everything locally.

## 10. Worked example: "the expenses, pictures, health reports and travel tickets for my India trip 2026"
1. The model parses the request into `{lens: trip, place: India, year: 2026, wants: [expenses, photos, health, tickets]}`; code validates it.
2. The link book resolves the trip (candidates nominated by photos, finance and tickets, merged by overlap in time and place). Two matching trips: Atlas asks which, or offers both.
3. Atlas calls `items_in_window` in each module in parallel, within the chat's scope. Health is locked: the page shows "3 reports, unlock to include".
4. The checker verifies every figure; a ticket's dates are cross-checked against the matching flight payment. The model writes a short summary.
5. Atlas shows one page with a section per module and can export a copy of the originals.
Tickets and health reports are served from the shared document store (by classified kind and date) until dedicated modules add structure.

## 11. Module checklist (a new module is done when)
Own database and key; migrations and backup; tools declared with read or write and sensitivity; `items_in_window`; entities and feed; ingestors for the kinds it accepts, each with a proof or a review-queue path; contract tests; no import of another module; documented in `modules.d/`.

## 12. Where the code is today
Implemented: Atlas shell, search, chat button and one Update button across Orbit and Lumo; contract v1; Orbit's answer checker, fast-path intents, agent-with-fallback, hybrid document search, balance proofs and cross-checks; no-network guards in both apps; separate databases; Orbit's database encryption; complexity gate, ESLint and Prettier in CI.
Not yet: core database and shared intake (Orbit's reader is still inside Orbit); the link book, lenses and `items_in_window`; the shared assistant and AI gateway (each app still has its own chat engine); service-to-service signing (any local program can call a module's port); at-rest encryption for Lumo and the core; strict types everywhere; strict CSP in Orbit (it still allows inline styles); hash-pinned dependencies and digest-pinned images; fuzzing, mutation testing, import-linter, `make verify`; health and travel modules; the Docker images have not been built on a real Mac.

## 13. Open decisions (defaults in bold; change by ADR)
- Health locked each session: **yes**.
- Chat scope: **all unlocked modules, with chips to narrow**.
- Intake: **documents copied into the vault, photos referenced in place**; arrival route **one inbox folder for PDFs, CSVs and photos**.
- Trip boundaries: **inferred from tickets, photos and payments, with a one-tap "wrong trip?" choice, no manual editing**.

## 14. Order of work
1. Foundation: one repository layout with a shared `kit`, this document, the enforcing gates (architecture tests, strict types, pinned dependencies), signed service-to-service calls.
2. Core database and the shared intake taken out of Orbit.
3. AI gateway and one assistant engine (merging Orbit's loop and Lumo's tool agent).
4. Contract v2 (`tools`, `items_in_window`, `entities`, `feed`), the link book and the lenses.
5. Health and travel modules, tier locks.
6. The India-trip request as the end-to-end acceptance test.
