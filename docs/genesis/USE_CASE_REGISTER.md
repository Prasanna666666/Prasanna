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

## 2.1 Domain scenario IDs for stage traceability

| ID | Domain scenario | Expected outcome |
|---|---|---|
| UC-017 | Finance understanding | Explain balances, cash flow, recurring spend, bills and portfolio exposure from owner-authorised records; exact calculations are deterministic and cited |
| UC-018 | Health understanding | Summarise owner-authorised records, measurements, medications and trends with dates, sources and uncertainty |
| UC-019 | Home and energy | Explain device state, energy, heating and environmental patterns; propose or execute reversible device control under owner policy |
| UC-020 | Travel planning | Research routes, lodging, entry rules, costs and accessible/vegetarian options; prepare exact booking preview |
| UC-021 | Work and project management | Track deliverables, blockers, deadlines, decisions and dependencies across authorised work sources |
| UC-022 | Research and learning | Search current public information, compare primary sources, cite and build learning/decision briefs |
| UC-023 | Shopping and ownership | Compare total cost, quality, warranty, repairability and resale; track return/warranty windows |
| UC-024 | Family and social commitments | Remember owner-approved dates/preferences, prepare messages and track commitments without sending |
| UC-025 | Legal and government administration | Explain official correspondence, track renewals/deadlines and prepare evidence/form drafts |
| UC-026 | Photos and personal archive | Search, describe, group and retrieve media using metadata and clearly labelled visual inference |
| UC-027 | Digital security and account hygiene | Inventory connected apps/scopes/devices, detect permission changes and support revocation |
| UC-028 | Governed memory | Retain useful facts/decisions with provenance, confidence, correction, expiry and deletion controls |
| UC-029 | Proactive daily briefing | Summarise calendar, priority messages, deadlines, follow-ups, weather and travel context without notification noise |
| UC-030 | Cross-app workflow automation | Plan and complete multi-step tasks across authorised apps; only Action Gateway executes and approval follows the closed list |

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
- Routine local security hygiene and reversible settings do not prompt. Approval is limited to the closed list in PRD §4.4; no catch-all approval category is added.

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

| Canonical stage | Integration/source | Initial useful capabilities | Later capabilities / constraints |
|---|---|---|---|
| Stage 3 | Local files and folders | Search, read, extract, cite, progressive index | Organise/rename with undo; never destructive by default |
| Stage 3 | Apple Mail | Search/read/summarise/draft; supported attachments after separate acceptance | Send/reply/forward only with exact approval |
| Stage 3 | Apple Calendar | Read agenda, conflicts, availability only | Event creation/movement is Stage 5; own events are prompt-free, while sending invitations/updates follows PRD §4.4 |
| Stage 5 | Reminders/tasks | Read, create, complete and reprioritise with undo | Delete without reliable undo requires approval |
| Stage 3 | Public Internet | Search/fetch public pages, compare, cite, freshness checks | Downloads only to controlled staging; no arbitrary executable launch |
| Stage 5 | Contacts | Resolve, create and edit local contacts with undo | Sharing/exporting contact data outside the Mac requires approval |
| Stage 6 | Browser | Research, compare and fill forms to preview | Submit/send/upload, purchase or book only under the closed approval list |
| Stage 5 | Notes | Search/read/create/edit notes with version history and undo | Delete without reliable undo or share outside the Mac requires approval |
| Stage 6 | Photos/media | Search, describe, organise and deduplicate proposals | Upload/share outside the Mac requires approval; deletion with reliable undo is reversible |
| Stage 5 | Finance sources | Read owner-authorised statements, transactions, invoices and investment data; local-model interpretation plus code-checked analysis | Spend, pay, trade, purchase or book only with exact approval |
| Stage 5 | Health sources | Read owner-authorised records and activity; local-model summaries/trends | No diagnosis claims; upload/share outside the Mac requires approval |
| Stage 6 | Home/IoT | Device state, energy and environmental readings; reversible device control | Physical access unlock or disabling a safety/security system requires approval; paid changes require approval |
| Stage 6 | Work platforms | Project/task/mail/document context; local drafts and reversible task updates | External posts/sends/uploads require approval |
| Stage 6 | Travel providers | Research and itinerary context | Paid booking/payment requires exact approval; cancellation without external message or disclosure is prompt-free |
| Stage 6 | Messaging/social | Read/summarise/draft where supported and explicitly connected | Send/post/share outside the Mac requires exact approval |
| Stage 6 | Cloud storage | User-owned connector, least privilege, read-first sync | No cloud inference; external upload/share follows PRD §4.4 |
| Stage 8 | iOS client | Secure access to owner-controlled Mac Core | Offline cache/sync and remote threat model must be accepted first |

Stage numbers are defined only in TARGET_ARCHITECTURE.md §11. Prioritise specific vendors within a stage by owner value, API stability, privacy, implementation effort, ongoing maintenance and reversibility.

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

Owner direction: single-user product; reading, searching, analysing, summarising, drafting and computing should not trigger approval prompts. Approval is limited to the exhaustive categories in PRD §4.4; no broader approval rule is implied.

The closed approval list is defined canonically in PRD §4.4 and is intentionally exhaustive. Nothing else triggers an approval prompt. The action matrix below must be kept in sync with that list. Approval preview shows exact action, destination/recipient, content/attachments, amount, date and material terms. Approval is single-use and invalidated by any material change. Reversible local actions use an undo journal.

| Action | Prompt? | Reason |
|---|---|---|
| Read/search/summarise/analyse/draft/compute | No | Routine work |
| Create/move own calendar event | No | Local reversible change |
| Send calendar invitation/update | Yes | Sends outside the Mac |
| Create/edit/rename/organise files or notes with undo | No | Reversible local change |
| Delete/overwrite with reliable undo | No | Reversible local change |
| Delete/overwrite without reliable undo; destructive migration | Yes | Irreversible data loss |
| Send/share/publish/upload outside the Mac | Yes | External disclosure |
| Spend/pay/trade/purchase/paid booking | Yes | Financial commitment |
| Unlock external door/disarm alarm/disable safety system | Yes | Physical safety/security boundary |
| Ordinary device control, reminders, task updates, local settings | No | Not on the closed list |

Acceptance: table-driven tests cover every action above and every action in the integration catalogue. UC-L01 must show zero approval prompts from after Get Started through a read-only answer. A prompt is permitted only for an action explicitly marked Yes above.

### 7.1 Approval and autonomy test invariant

The closed approval list in PRD §4.4 is authoritative. The table in §7 is the expected prompt matrix; the integration catalogue must not add a prompt category. The read-only UC-L01 journey has zero approval prompts after the one-time Get Started and OS permissions. Calendar create/move for the owner's own calendar is prompt-free; sending invitations/updates is approved as external sending.

### 7.2 Agent execution integrity

Only the Action Gateway executes. Agents propose; the coordinator checks conflicts; a durable unique action ledger and deterministic idempotency key prevent duplicate effects; per-target leases/fencing tokens and compare-and-set protect against concurrent changes; every reversible action has an undo record. Specialist deployment requires a frozen benchmark against the direct/single-model baseline. See TARGET_ARCHITECTURE.md §18.

## 8. Roadmap alignment

TARGET_ARCHITECTURE.md §11 is the sole canonical delivery roadmap, including stage numbers, scenario IDs, dependencies, exit evidence and first-tryable outcomes. This register does not define a competing wave or release sequence. Every integration row uses the canonical stage number; if an integration is not yet assigned, mark it deferred and record the reason.

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

## 10. Additional scenario coverage added after independent challenge

| ID | Scenario | Expected behaviour | Stage / evidence |
|---|---|---|---|
| UC-031 | Conversation-history management | Search, pin, archive and owner-requested deletion of conversations; explain retention and preserve audit where required | Stage 3+; history and deletion tests |
| UC-032 | Capability discovery | Owner asks “what can Atlas do?”; show available, connected, gated and future capabilities without implying unavailable features work | Stage 3; capability-registry/UI test |
| UC-033 | Mac-to-iPhone task handoff | Continue a durable task on iOS without duplicating actions or exposing data to an untrusted device | Stage 8; sync/idempotency/device-revocation tests |
| UC-034 | Accessibility | VoiceOver, keyboard-only, dictation, large text, contrast and reduced-motion paths remain usable | Every client stage; accessibility test matrix |
| UC-035 | Bulk operation preview | Preview scope, sample and affected count for batch rename/organise; reversible changes have undo; destructive no-undo actions follow PRD approval list | Stage 5+; dry-run/undo tests |
| UC-036 | Ambient context | User explicitly invokes “summarise what I’m looking at”; no continuous screen capture by default; sensitive fields are not captured without task scope | Later/deferred; explicit invocation and redaction tests |
| UC-037 | Location/arrival trigger | Run only when an owner-configured location trigger is enabled; disclose platform permission and battery implications | Stage 8/later; trigger/permission tests |
| UC-038 | External-source watcher | Watch a connected source with a visible cadence/budget; deduplicate changes and stop immediately on disconnect | Stage 6; event/poll-budget tests |
| UC-039 | Folder-arrival watcher | Notice new files in owner-designated folders; process incrementally and report unsupported files | Stage 3+; file-event/restart tests |
| UC-040 | Replace the Mac | Restore Atlas on replacement hardware from verified backup; re-enrol device, restore keys safely and reconcile counts/hashes | Stage 4/7; full restore drill |
| UC-041 | macOS permission reset/upgrade | Detect revoked/reset Full Disk Access or other grants; pause affected source reads and guide the owner once without repeated prompts | Stage 3/7; OS permission reset test |
| UC-042 | Model/quantisation update | Run frozen answer-quality, citation, safety, latency and resource regression suite before changing default model | Stage 6/7; model release gate |
| UC-043 | Apple ID/iCloud change | Detect changed account context and connector authentication; do not silently bind a different account | Stage 5+; account identity tests |
| UC-044 | Data growth and storage pressure | Show source/index/cache usage, keep originals, tier derived data and pause/rebuild caches without silent retention loss | Stage 4; storage budget and pressure tests |
| UC-045 | Trusted-person/emergency access | Not applicable to the single-user product; no delegated emergency access in current scope | Deferred by single-user boundary |
| UC-046 | Headless Mac mini reboot and Keychain availability | Keep FileVault enabled. Atlas Core starts as a user LaunchAgent after owner login/unlock; after reboot before login, remote clients show “Mac needs owner sign-in”. Do not enable auto-login or disable FileVault to gain unattended startup. Revisit only with a separately reviewed system-keychain design. | Stage 7; target-Mac reboot/FileVault/Keychain test |
| UC-047 | Quoted/forwarded sender attribution | Distinguish actual stored sender/header from quoted or forwarded text; never attribute a quoted instruction to the current sender | Stage 3; adversarial Mail fixture |
| UC-048 | Attachment-borne prompt injection | Treat text in PDF/Office/image/OCR attachments as untrusted; it cannot widen source access or cause actions | Attachment package; hostile-format test suite |
| UC-049 | Calendar-invite prompt injection | Treat event title, description, attendees and links as untrusted data; they cannot trigger external actions or policy changes | Calendar stage; adversarial invite test |

The scenario register is continuously extensible. A scenario is not accepted until its stage, permission boundary, normal path, failure path and test evidence are defined.
