# Atlas — Use-Case and Scenario Register

**Status:** Architecture baseline for review; not a claim of implementation.  
**Product boundary:** One owner, one Atlas application, macOS first, iOS later.  
**Purpose:** Turn the broad personal-assistant vision into a testable, extensible catalogue. This register is deliberately scenario-based rather than a list of domain names. Each scenario must eventually map to a capability, source/tool permissions, user-visible outcome, failure cases, tests and evidence.

## 1. How completeness is managed

“All possible use cases” cannot be proven by writing a long examples list. Atlas uses a coverage method. Every scenario is classified across:

1. **Life domain:** daily rhythm; communication; calendar/time; tasks/projects; files/knowledge; money; health; home; travel; work; learning/research; shopping; family/social; legal/administrative; media/photos; digital security; memory/settings.
2. **Interaction mode:** ask; command; quick capture; voice; proactive alert; scheduled run; batch; multi-step workflow; long-running job; correction; undo/recovery.
3. **Trigger:** owner request; time/event; new or changed source; deadline; threshold; failed task; previously stated rule.
4. **Lifecycle:** first-run/import; normal use; update/change; ambiguity/conflict; failure/partial result; revocation; backup/restore; device loss; migration/retirement.
5. **Risk:** read-only; reversible local change; external side effect; destructive/financial/irreversible action.
6. **Evidence:** source citation, deterministic calculation, action receipt, confidence/limitations, or explicit “not available”.

A scenario is not complete until its happy path, ambiguity, denial, partial-data, interruption/restart, stale-source and undo/approval behaviour are specified where applicable. Add scenarios when telemetry-free owner feedback, audits or testing reveal gaps. “Not applicable” and “later” must carry a reason and a revisit milestone.

## 2. Product-wide scenarios

| ID | Scenario | Expected Atlas behaviour | Acceptance evidence |
|---|---|---|---|
| UC-001 | Ask a question spanning multiple life domains | Retrieve only permitted sources, reconcile conflicts, answer with linked evidence | Cross-domain synthetic tests; source trace |
| UC-002 | Ask a question with insufficient evidence | Say what is missing; do not invent or imply a search occurred when it did not | Abstention and truthful-status tests |
| UC-003 | Ask for a current fact | Search public web when useful; cite dated sources and separate web facts from personal facts | Freshness and citation tests |
| UC-004 | Give a broad goal rather than steps | Clarify only essential ambiguity; plan, delegate and execute permitted work | End-to-end task trace |
| UC-005 | Ask “what changed?” | Compare current state with prior evidence and report material changes | Version/delta tests |
| UC-006 | Correct a remembered fact | Update the fact, retain provenance/change history and apply correction to future answers | Memory correction tests |
| UC-007 | Ask why Atlas believes something | Show source, timestamp/version, location and reasoning summary | Evidence-inspection test |
| UC-008 | Ask Atlas to continue a prior task | Restore durable state and resume safely without duplicate side effects | Restart/idempotency tests |
| UC-009 | Interrupt or cancel work | Stop at a safe boundary, report completed vs remaining work | Cancellation/fault-injection tests |
| UC-010 | Two sources disagree | Show conflict, recency and authority; do not silently pick a convenient value | Conflict-resolution tests |
| UC-011 | Source becomes unavailable or permission is revoked | Stop using it immediately; invalidate dependent cache/context and explain limitation | Revocation boundary tests |
| UC-012 | Long task runs in background | Show acknowledgement, progress, ETA only when supportable, cancellation and final result | UI/task lifecycle tests |
| UC-013 | Ask by voice or quick capture | Capture intent accurately, confirm uncertain transcription only when material | Speech evaluation |
| UC-014 | Ask for a scheduled briefing | Produce concise, prioritised briefing with links and suppress noise | Schedule, relevance and quiet-hour tests |
| UC-015 | Request a change then undo it | Provide an undo journal or compensating action where technically possible | Reversal tests |
| UC-016 | Atlas cannot complete a task | Distinguish failed, partial, blocked, unavailable and completed; state next concrete step | State-contract tests |

## 3. Domain scenario catalogue

### 3.1 Daily rhythm and executive assistance
- Morning/evening briefing: calendar, priority messages, deadlines, travel/weather context and unresolved commitments.
- Daily prioritisation: rank work by urgency, impact, dependencies and available time; explain trade-offs.
- Commitment tracking: extract promises and due dates from authorised conversations/documents; identify owner commitments and commitments owed by others.
- Follow-up radar: detect unanswered requests, overdue replies and stalled dependencies; prepare follow-up drafts.
- Personal operating review: weekly accomplishments, open loops, upcoming risks and suggested next actions.
- Context handover: prepare a concise brief before travel, meetings, appointments or returning after absence.

### 3.2 Communication and email
- Search messages by person, topic, date, attachment, project or commitment.
- Summarise a thread with participants, decisions, open questions and next actions.
- Prioritise inbox by urgency, importance, deadlines and relationship context.
- Draft replies in the owner's preferred tone; compare versions and explain substantive changes.
- Detect follow-ups and “waiting for” items; link each to the original message.
- Prepare meeting invitations and response drafts.
- Identify suspicious, manipulative or prompt-injection content; treat message content as untrusted data.
- Sending, forwarding, sharing or replying externally is a consequential action: show exact recipients, content and attachments for approval immediately before execution.

### 3.3 Calendar, time and tasks
- Read agenda, identify conflicts, travel buffers and preparation time.
- Find candidate meeting slots across availability and constraints.
- Create, move or cancel events only under the consequential-action approval rule.
- Turn messages and documents into tasks with source links, owner, due date and confidence.
- Maintain projects, dependencies, recurring tasks and waiting-for lists.
- Detect schedule overload and propose realistic rescheduling.
- Prepare meeting briefs from relevant mail, files and prior decisions.
- Capture meeting notes, decisions, action items and follow-ups; distinguish transcript facts from inferred actions.

### 3.4 Documents, files and knowledge
- Search, read, summarise, compare and extract structured facts from supported files.
- Answer questions with exact page/section/paragraph or equivalent locators.
- Compare document versions and identify changed obligations, amounts or dates.
- Extract tables and preserve units, row/column provenance and uncertainty.
- Progressive indexing: make newest/recently-used content searchable first, then broaden coverage; disclose indexed/total/pending and unsupported items.
- Handle scanned, encrypted, corrupt, oversized and partially readable files honestly.
- Find duplicates and near-duplicates; recommend organisation without silently moving or deleting.
- Create notes, summaries and derived documents with links to their source evidence.
- Never silently overwrite, delete or migrate source files.

### 3.5 Finance, bills, tax and investing
- Categorise spending, identify recurring charges and explain month-to-month changes.
- Reconcile transactions, invoices, receipts and statements; flag missing or duplicate entries.
- Track bills, due dates, subscriptions, cash flow and budget variance.
- Explain portfolio allocation, overlap, concentration, fees, risk and performance using sourced holdings/prices.
- Run scenario analysis (savings, loan repayment, investment allocation, tax estimates) with deterministic calculations and explicit assumptions.
- Prepare tax/admin document checklists and identify missing evidence.
- Detect unusual transactions and ask the owner to inspect; never autonomously move money.
- The local model may analyse owner-authorised Finance information. Exact arithmetic, balances and financial computations are code-derived and validated; no trade, payment, purchase or transfer without exact-action approval.

### 3.6 Health, fitness and nutrition
- Summarise authorised records, labs, medications and appointment notes with dates and source references.
- Track symptoms, measurements, activity, sleep and trends when connected sources permit.
- Explain nutrition and meal patterns against stated dietary constraints.
- Prepare clinician questions and appointment summaries.
- Support exercise plans with equipment, injury/limitation context and progression tracking; do not present as diagnosis.
- Flag conflicting or stale health records and distinguish measured values from estimates.
- The local model may read owner-authorised Health information; health advice must communicate uncertainty and escalation needs. No medical action or external sharing without approval.

### 3.7 Home, devices and energy
- Monitor connected device status, energy use, temperature, humidity and comfort patterns.
- Recommend heating/device schedules with cost, comfort and safety trade-offs.
- Detect abnormal energy use, offline devices or environmental patterns.
- Execute reversible device changes within owner-defined automation; explain and log them.
- Ask approval for purchases, paid services, security changes or consequential access changes.
- Keep platform-specific integrations behind adapters; never claim HomeKit or device control until tested.

### 3.8 Travel and mobility
- Research destinations, transport, accommodation, visa/entry requirements and current restrictions.
- Build itineraries around budget, accessibility, dietary needs, interests and travel pace.
- Compare routes and total journey cost, not only ticket price.
- Track bookings, check-in windows, cancellation rules and document expiry.
- Monitor disruption and propose alternatives.
- Prepare booking forms and exact selections; booking, payment or cancellation requires approval.
- Cite current official sources for rules and clearly timestamp volatile information.

### 3.9 Work, projects and professional life
- Convert goals into milestones, dependencies and deliverables.
- Prepare project status reports from authorised work sources.
- Review code, pull requests, tests and technical decisions; distinguish inspected evidence from claims.
- Draft proposals, emails, meeting agendas and status updates.
- Track blockers, owners and due dates; escalate only material risks.
- Coordinate specialist work with explicit task contracts and independent verification.
- Never merge, deploy, publish or change production systems without the required approval and release controls.

### 3.10 Research, learning and decision support
- Search the web, compare primary sources, assess recency and produce cited briefs.
- Explain unfamiliar topics at the requested depth and create learning plans.
- Compare alternatives using criteria, weighted trade-offs and sensitivity analysis.
- Maintain research notes with source links, dates and confidence.
- Distinguish facts, estimates, expert opinion and Atlas recommendations.
- Re-check time-sensitive facts before presenting them as current.

### 3.11 Shopping and ownership lifecycle
- Discover products and compare total cost, fit, quality, reliability, warranty, repairability and resale value.
- Track price changes and notify only when a meaningful threshold is reached.
- Compare new vs used and buy vs repair.
- Maintain receipts, warranties, serial references and return deadlines.
- Prepare carts or forms; purchase, subscribe or place an order only after exact approval.
- Never treat sponsored placement as evidence of quality.

### 3.12 Family, social and personal relationships
- Remember owner-approved names, preferences, important dates and commitments.
- Prepare thoughtful messages and reminders.
- Summarise shared plans from authorised conversations.
- Track gifts, events and follow-ups without making assumptions about relationships.
- No unsolicited disclosure or message sending; external communication follows approval policy.

### 3.13 Legal, government and administration
- Track permits, registrations, renewals, appointments and deadlines.
- Explain official correspondence and identify requested actions.
- Prepare forms and evidence packs; preserve source documents.
- Research current official procedures and cite the relevant authority.
- Flag when professional legal/tax advice is needed.
- Submitting forms, signing, paying fees or making declarations requires exact-action approval.

### 3.14 Photos, media and personal archive
- Search and organise photos by date, place, event and owner-provided labels.
- Detect duplicates and propose albums or collections.
- Summarise media libraries and retrieve relevant items for a task.
- Respect metadata provenance and distinguish visual inference from verified metadata.
- Do not delete, upload or share media without approval.

### 3.15 Digital security and account hygiene
- Inventory connected apps, permissions, tokens and device sessions.
- Alert on unexpected permission changes, expired credentials or suspicious access.
- Explain what data each integration can access and why.
- Support token revocation, device revocation and secure recovery workflows.
- Never expose secrets in model context, logs, notifications or web requests.
- Security-sensitive changes require explicit approval and a recoverable plan.

### 3.16 Memory, preferences and personalisation
- Retain useful facts, preferences, decisions, routines and ongoing project context.
- Track provenance, confidence, validity period and source conflicts.
- Ask for correction only when ambiguity materially changes an action or answer.
- Support review, correction, expiry, export and deletion.
- Keep highly sensitive facts under explicit owner control and configurable retention.
- Never convert a guess into a permanent fact.

## 4. Cross-cutting lifecycle and edge-case scenarios

| ID | Scenario class | Required behaviour |
|---|---|---|
| UC-L01 | First run | One clear “Get started” flow explains local processing, internet use and connected-source access; no repeated incidental prompts |
| UC-L02 | Source onboarding | Explain scope in plain language; no source read before OS and Atlas grants are active |
| UC-L03 | Large import | Tiered/newest-first usefulness; visible coverage and queue; interactive work remains responsive |
| UC-L04 | Unsupported format | Identify file and reason; never silently skip or claim complete coverage |
| UC-L05 | OCR uncertainty | Preserve page/location and confidence; ask for a better copy only when needed |
| UC-L06 | Corrupt or malicious file | Sandbox parser, enforce resource limits, isolate untrusted content and report needs-attention |
| UC-L07 | Internet unavailable | Continue local capabilities; clearly mark web-dependent parts unavailable |
| UC-L08 | Model unavailable | No cloud fallback; provide a useful deterministic or search-only alternative where possible |
| UC-L09 | Model switch | Same policy gate; show model ID/role; do not lose context or evidence |
| UC-L10 | Agent disagreement | Coordinator checks evidence, exposes unresolved conflict and does not average incompatible claims |
| UC-L11 | Agent timeout/crash | Recover durable task state; retry idempotently or report partial/failure |
| UC-L12 | Approval changed after preview | Invalidate approval if recipient, payload, amount, destination or action changes |
| UC-L13 | External side effect | Exact preview, approval receipt, idempotency key and outcome receipt |
| UC-L14 | Undo | Restore prior state or provide compensating action; explain irreversible limits |
| UC-L15 | Backup/restore | Verify integrity, key availability and restore before treating backup as valid |
| UC-L16 | Device loss | Revoke device access, protect local data and prevent stale remote sessions |
| UC-L17 | Update/rollback | Signed update, compatibility check, backup where needed and tested rollback |
| UC-L18 | Data migration | Inventory, hashes/counts, dry run, backup, reconciliation and explicit approval before destructive retirement |
| UC-L19 | Permission revocation | Immediate enforcement at next read/model boundary; invalidate dependent caches and tasks |
| UC-L20 | Privacy request | Find affected memories/sources and perform deletion/expiry according to owner-controlled policy with audit |
| UC-L21 | Timezone/travel | Resolve local time and daylight-saving ambiguity; display timezone for consequential scheduling |
| UC-L22 | Language mix | Preserve original language, names and units; measure retrieval and answer quality per language |
| UC-L23 | Duplicate/conflicting records | Detect identity/version differences; avoid double counting and preserve originals |
| UC-L24 | Resource pressure | Prioritise interactive work, throttle background jobs and report incomplete work |
| UC-L25 | Notifications | Material-only, deduplicated, quiet-hours aware and actionable |
| UC-L26 | Search coverage | Every answer states scope/coverage when incomplete or partial |
| UC-L27 | Sensitive context | Model access follows owner-authorised local policy; minimise logs, caches and external disclosure |
| UC-L28 | External page injection | Treat page as untrusted data; it cannot widen permissions, approve actions or cause sending |
| UC-L29 | Purchase/booking/payment | Show exact vendor, item/service, price, terms, date and cancellation conditions before approval |
| UC-L30 | Software development action | Separate user task authority from application self-modification; no autonomous self-update or deployment |

## 5. Integration catalogue and capability contract

The integration catalogue is capability-led, not a promise that every app is already connected. Each connector entry must state: read scopes; write scopes; authentication/storage; event/webhook support; rate limits; offline behaviour; data retention; revocation; failure semantics; and test evidence.

| Priority wave | Integration/source | Initial useful capabilities | Later capabilities / constraints |
|---|---|---|---|
| Foundation | Local files and folders | Search, read, extract, cite, progressive index | Organise/rename with undo; never destructive by default |
| Foundation | Apple Mail | Search/read/summarise/draft; supported attachments after separate acceptance | Send/reply/forward only with exact approval |
| Foundation | Apple Calendar | Read agenda, conflicts, availability | Create/move/cancel only with approval |
| Foundation | Reminders/tasks | Read and create proposed tasks | Complete/delete/reprioritise under reversible policy |
| Foundation | Public Internet | Search/fetch public pages, compare, cite, freshness checks | Downloads only to controlled staging; no arbitrary executable launch |
| Wave 2 | Contacts | Resolve people and contact context | Create/edit/share contacts with approval where consequential |
| Wave 2 | Browser | Research and fill forms to preview | Submit, purchase, book or send only with exact approval |
| Wave 2 | Notes | Search/read/create notes | Edit/delete with undo; external sharing approval |
| Wave 2 | Photos/media | Search metadata, describe, organise proposals | Upload/share/delete requires approval |
| Wave 2 | Finance sources | Read statements, transactions, invoices and investment data; code-checked analysis | Transfers, payments, trades and purchases require approval |
| Wave 2 | Health sources | Read owner-authorised records and activity; summaries/trends | No diagnosis claims; external sharing requires approval |
| Wave 3 | Home/IoT | Device state, energy and environmental readings | Reversible control under policy; security/paid changes require approval |
| Wave 3 | Work platforms | Project/task/mail/document context | Issue/PR/task updates and external posts require policy/approval |
| Wave 3 | Travel providers | Research and itinerary context | Booking, cancellation and payment require exact approval |
| Later | Messaging/social | Read only where supported and explicitly connected | Send/post/share requires exact approval |
| Later | Cloud storage | User-owned connector, least privilege | No cloud inference; external storage writes require approval |
| Later | iOS client | Secure access to owner-controlled Mac Core | Offline cache/sync and remote threat model must be accepted first |

“Wave” is a recommended sequence, not a commitment to a specific vendor API. Prioritise by owner value, API stability, privacy, implementation effort, ongoing maintenance and reversibility.

## 6. Agent workforce and task contracts

Atlas Core is the single coordinator. Specialists are on-demand internal workers, not independent apps or unrestricted agents.

- **Executive coordinator:** decomposes requests, selects specialists, tracks dependencies and consolidates.
- **Research:** public-web discovery, source quality, recency and citations.
- **Knowledge:** files, mail, memory, evidence and conflict resolution.
- **Communication:** inbox triage, message drafting and follow-up tracking.
- **Calendar & planning:** time, tasks, commitments and schedule optimisation.
- **Finance:** deterministic calculations plus model-assisted interpretation of owner-authorised records.
- **Health:** summarisation, trends, nutrition and appointment preparation.
- **Travel:** route, lodging, itinerary and disruption research.
- **Home:** devices, energy and household workflows.
- **Work/project:** deliverables, status, code and project coordination.
- **Shopping:** product discovery, comparison and ownership lifecycle.
- **Guardian/verifier:** policy checks, exactness, source integrity, approval and action receipts. This is a control role, not a second authority.

Every delegated task has a bounded objective, source/tool scope, deadline, budget, expected artefact, evidence requirement and cancellation condition. Specialists return structured findings with citations, uncertainty and limitations. The coordinator verifies important claims and handles disagreement. Parallelism is used only when tasks are independent; do not create agents merely to appear sophisticated.

## 7. Approval and autonomy contract

Owner direction: single-user product; reading, searching, analysing, summarising, drafting and computing should not trigger approval prompts. Approval is reserved for consequential actions with effects outside Atlas or material irreversible change.

Approval required for:
- Sending, forwarding, publishing, sharing or disclosing information outside the owner's controlled Atlas environment.
- Spending money, making payments, trades, purchases or paid bookings.
- Deleting or overwriting source data, destructive migration or irreversible changes.
- Similar consequential actions where a mistaken execution would be materially costly or difficult to reverse.

Approval preview must show the exact action, destination/recipient, content/attachments, amount, date, relevant terms and scope. Approval is single-use, short-lived and invalidated by any material change. Atlas must not ask again for routine read-only work or low-risk internal computation. Reversible local actions should use an undo journal and owner-configured policy.

## 8. Release prioritisation

1. **First usable slice:** one Atlas conversation; local model adapter; source-backed memory; progressive document search; exact citations; transparent coverage; durable tasks; coherent Mac UI.
2. **Personal information layer:** Mail and supported attachments; Calendar; unified search across owner-enabled sources; morning briefing and follow-up tracking.
3. **Personal chief of staff:** Finance and Health analysis, tasks/projects, Internet research, specialist delegation, voice and notifications.
4. **Action capability:** drafts, calendar/task/file operations, browser workflows and app actions; approval only for consequential actions; undo and audit.
5. **Connected life:** Home, travel, shopping, work integrations and proactive monitoring.
6. **Mobile and worldwide access:** iOS client, secure remote connectivity, offline/cache/sync and device revocation.

Each wave is a capability milestone, not a separate app. Release order may change only with an explicit value/risk/effort rationale and updated dependencies.

## 9. Definition of done for every scenario

A scenario is “implemented” only when:
- Its user journey and failure states are documented.
- Permission and data-flow boundaries are mapped.
- Relevant automated tests pass, including adversarial and restart cases.
- Citations/calculations/action receipts are verifiable.
- Partial coverage and unsupported cases are visible.
- Performance is measured on the appropriate environment.
- User documentation and support/recovery steps exist.
- Evidence is labelled as developer-reported, CI-verified, architect-reviewed or owner-verified.
