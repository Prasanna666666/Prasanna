# Atlas — UI/UX Product and Design Specification

**Status:** Canonical design baseline — documentation complete; implementation and visual acceptance are separate gates  
**Owner:** Product owner  
**Design authority / specification integrator:** ChatGPT  
**Implementation and design-system engineering:** Claude Code  
**Platform sequence:** macOS first; portable contracts and interaction patterns for later iOS  
**Applies to:** The single Atlas application, all first-party domains and shared workflows

## 1. Purpose and completion boundary

This document is the binding UI/UX specification for Atlas. It removes the need for Claude to infer the product's visual direction, navigation, screen responsibilities, interaction patterns, states, or design-quality bar from scattered implementation details.

“UI/UX specification complete” means the design decisions and implementation contract are documented here. It does **not** mean the screens have been implemented, run on the owner's Mac, visually inspected, accessibility-tested, or accepted by the owner. Those are measurable implementation and verification gates in §13. No one may mark those gates passed based on a build, unit tests, screenshots of mockups, or a hosted CI launch alone.

The PRD and accepted architecture remain authoritative for product scope, privacy, permissions, data and system behaviour. This document governs presentation and interaction; it cannot weaken those requirements.

## 2. Product experience direction

### 2.1 Design intent

Atlas should feel like a calm, capable, premium macOS personal workspace—not a generic chatbot, an admin console, a collection of mini-apps, or a dashboard crowded with widgets.

The experience must be:
- **Quietly confident:** deliberate hierarchy, restrained visual emphasis, clear language.
- **Focused, not empty:** use whitespace to separate meaningful groups; every visible element earns its place.
- **Useful at a glance:** the home surface answers “what matters, what changed, what needs me?”
- **Conversational at its core:** chat is the universal command and explanation surface, not a separate product mode.
- **Evidence-first:** facts, citations, source inspection and confidence/limitations are understandable without exposing implementation jargon.
- **Predictable:** consistent navigation, actions, states, terminology and keyboard behaviour.
- **Native-feeling:** use macOS conventions, system typography, standard controls and platform behaviours where they improve usability.
- **Accessible and resilient:** legible, keyboard-operable, VoiceOver-aware, responsive to window size and system appearance.

### 2.2 Explicit anti-goals

Do not ship:
- A screen filled with cards, charts, counters, badges or permanent status panels.
- A giant empty hero area or a sparse screen that feels unfinished.
- A generic AI chat clone with a sidebar of unrelated conversations and a blank prompt.
- Separate user-facing apps or competing navigation systems for Documents, Mail, Finance, Images, Travel or other domains.
- Decorative gradients, glass effects, glow, excessive shadows, noisy animation or ornamental icons without functional meaning.
- Colour as the only way to communicate status.
- Raw API states, internal package names, file paths, stack traces, model prompts or policy-engine terminology.
- Fake activity, fabricated metrics, sample personal data or demo content presented as real.
- A permanent approval centre that implies routine actions require approval; approvals exist only for the closed consequential-action list in the PRD.

### 2.3 Visual language

Use a restrained neutral foundation with one controlled Atlas accent. The visual system must work in both light and dark macOS appearances and respect system contrast settings.

- **Typography:** system San Francisco; clear type hierarchy; body text optimised for sustained reading; tabular numerals for aligned figures; avoid tiny secondary text.
- **Colour:** semantic tokens for primary, secondary, muted, separator, accent, success, warning and destructive states. Status must always include text or an icon, not colour alone.
- **Surfaces:** primarily one main canvas with subtle grouping. Use cards only when they create a meaningful boundary or support comparison.
- **Borders and elevation:** separators and spacing first; shadows only for genuine layering such as popovers and sheets.
- **Icons:** consistent SF Symbols where suitable; icons accompany labels for unfamiliar or consequential actions.
- **Shape:** restrained, consistent corner radii; no pill-shaped everything.
- **Motion:** short, purposeful transitions that explain state changes; respect Reduce Motion; never delay user input.
- **Density:** default to comfortable density. Dense tables or technical detail may use a deliberate compact mode later, never as the default.

Exact colour values, spacing units, type styles, radii, control heights and motion timings must be centralised as named design tokens in the implementation. Do not scatter literal values across views. Claude may select concrete token values consistent with this direction and record them in the implementation's design-token reference; this is an engineering detail, not a new product decision.


### 2.4 Everyday simplicity and progressive disclosure

Atlas is designed for a regular person using it repeatedly, not an administrator operating a control centre. The default experience must be immediately understandable without learning Atlas's internal capability map.

- Keep the persistent navigation to the four destinations in §3.1. Do not add a top-level destination for every feature, domain, agent, data source or integration.
- The Home first viewport should remain calm and useful in seconds. It is not a miniature dashboard of every Atlas capability.
- Ask Atlas is the universal entry point. Natural-language intent should route to the right capability and open a focused workspace only when that improves the task.
- Explore groups followed subjects into a small number of readable views. Individual topics such as cricket, Olympics, AI, politics or markets are filters or contextual destinations within Explore—not a growing tree of navigation sections.
- Life capabilities are surfaced when relevant and can be pinned as optional shortcuts by the owner, but pinning must never be required to use them.
- Prefer one clear next action over multiple competing buttons. Put advanced options behind a named disclosure such as “Filters”, “Details” or “More”.
- Do not show every metric by default. A summary may reveal its evidence, calculation, history and technical detail on demand.
- Avoid duplicated entry points, redundant cards, permanent empty panels, excessive badges, nested navigation trees and feature-specific dashboards that repeat the same personal context.
- A new feature must first fit an existing destination and interaction pattern. It may justify new persistent navigation only after demonstrated frequent use and an explicit product-design review; implementation convenience is not justification.

The acceptance test is simple: a first-time everyday user should understand where to start, how to ask Atlas for something and where to find their information without being taught the internal architecture.

## 3. Information architecture and navigation

### 3.1 One application, one navigation model

The user always remains inside Atlas. Domain areas are destinations/filters within Atlas, not separate applications.

The everyday navigation is deliberately limited to four destinations:
1. **Home** — a calm daily starting point: important items, a short briefing and recent work worth resuming.
2. **Ask Atlas** — the universal place to ask, plan, research and delegate. It can open a focused workspace when a task needs one.
3. **Explore** — a single, curated place for things the owner follows, such as AI and technology, science, markets and sports. Topic switches live inside this destination; they are not permanent navigation items.
4. **Library** — one searchable place for authorised documents, mail, pictures and other personal knowledge.

Settings is a restrained utility entry in the app chrome, not a peer destination in the everyday navigation. Task progress and recent outcomes appear in context; a complete activity history is reachable from a secondary “All activity” affordance when needed.

**Life capabilities are not navigation categories.** Investing, home and energy, fitness, nutrition, travel, Olympics, cricket statistics, politics/current affairs and other capabilities open contextually from Ask Atlas, relevant Home/Explore items, Library evidence or global search. A capability may use a focused workspace for a complex task, but it must not automatically earn a permanent sidebar item. Related capabilities should be grouped by the user's goal, not by internal service or data-source boundaries.

Use progressive disclosure throughout: start with the simplest useful view; reveal filters, charts, detailed statistics, technical controls and configuration only when the user asks or the task genuinely requires them. Never expose unavailable capabilities as working features. Do not add empty destinations or placeholder navigation to advertise a roadmap.

The sidebar may collapse. Its selection, keyboard shortcuts and window restoration must behave predictably. On narrow windows, it must adapt to a compact navigation presentation without clipping or hiding essential actions.

### 3.2 Global frame

Every main screen shares:
- A stable window title and navigation context.
- A single global search/command entry point where implemented.
- A clear page title and concise contextual description when needed.
- A consistent content column and spacing grid.
- A predictable location for transient notices and task progress.
- A single account/device identity context; no multi-user switcher.

Do not duplicate global controls inside every domain screen.

## 4. Screen specifications

### 4.1 Home

**Purpose:** a fast, calm briefing—not an analytics wall.

Content order:
1. A simple greeting or “Good morning/afternoon/evening” only when local time is available; otherwise a neutral “Your Atlas”.
2. One prominent “Ask Atlas” input/action.
3. A short “Needs your attention” group containing only material deadlines, risks, unresolved tasks or decisions. Hide the group when empty.
4. A concise “Recent updates” stream of meaningful source changes and completed work, with source/time context.
5. “Continue where you left off” for a small number of active or recent tasks/conversations.

Rules:
- No fabricated scores, productivity ratings or arbitrary charts.
- No more than three simultaneously prominent content groups at the initial viewport.
- Empty state explains how to begin and does not simulate activity.
- Each item opens the relevant evidence, task or conversation.
- Prioritisation must be based on real events and deterministic policy, not decorative ranking.

### 4.1.1 Home dashboard — adaptive daily briefing

Home is the only default dashboard. It should feel composed for this moment, not like a fixed grid of widgets. Its content is assembled from a small set of reusable modules and changes only when there is a meaningful reason.

**Default composition (top to bottom):**
1. A quiet greeting and one natural-language Ask Atlas entry point.
2. At most one lead item: the most useful timely insight, reminder, decision or ongoing task. Omit it when nothing qualifies; never manufacture a headline to fill the space.
3. A compact “For you today” briefing, normally a short digest of followed subjects or meaningful personal updates. It may combine different domains into one readable group rather than separate cards for each domain.
4. A small “Pick up where you left off” continuation when there is genuinely unfinished or recently active work.

The initial viewport should contain no more than three content groups in addition to the greeting/composer. The user should be able to scan it in a few seconds. Below the fold, optional recent items may appear in a simple chronological list; do not create a second dashboard of charts.

**Adaptive relevance rules:**
- Rank candidates using transparent signals: explicit user priorities and pinned items first; deadlines and time sensitivity; direct relevance to active tasks; material changes in followed subjects; recency; source reliability; and whether the item has already been seen or dismissed.
- Explicit owner instructions always outrank inferred interests. A muted topic, dismissed item or quiet period must be respected.
- Combine duplicates and related updates. Prefer one useful synthesis with links to evidence over several near-identical alerts.
- Avoid repeating unchanged information. Show what changed since the last visit, not the same generic briefing every day.
- Keep the mix balanced over time when several followed interests are active; do not let one high-volume topic crowd out everything else. Balance must never promote low-value content just to meet a quota.
- Personal deadlines, safety-relevant device alerts and explicitly requested reminders may outrank general-interest stories. Do not infer emergencies from weak signals.
- Every surfaced item must have a clear reason it is shown and a route to inspect its source, dismiss it, mute the topic or ask Atlas about it.
- Do not use click-through, time-on-screen, streaks, outrage or engagement maximisation as ranking objectives. “Engaging” means useful, fresh, understandable and worth returning to—not addictive.

**Personalisation and user control:**
- Learn from explicit follows/mutes, pins, corrections and dismissals. Treat passive clicks as weak evidence only; do not silently redefine the owner's priorities.
- Provide lightweight controls such as “More like this”, “Less like this”, “Mute topic” and “Why am I seeing this?” in context, not a permanent settings panel.
- Allow a small number of owner-pinned shortcuts or priorities, but keep the default layout uncluttered and make all capabilities discoverable through Ask Atlas/search.
- Respect quiet hours and notification preferences. A dashboard update is not automatically a push notification.

**States:**
- First run: explain the value of the briefing and invite one simple first question; do not display fake cards or demand a long interest-setup form.
- No connected sources: remain useful through Ask Atlas and clearly explain that personal updates/briefings need authorised sources.
- Nothing important today: say so calmly and leave the space quiet; do not fill it with generic content.
- Stale or partial sources: label freshness/coverage and exclude unsupported claims from confident summaries.
- Loading/error: preserve the rest of Home, show a small inline state and allow retry; never blank the whole dashboard.
- Returning visit: prioritise genuinely new or changed items and preserve dismissed/pinned choices.

### 4.1.2 Explore dashboard — curated, interest-led discovery

Explore is not a second Home dashboard or an infinite feed. It is a deliberate reading and discovery space for followed subjects. Its first view is a compact briefing; subject filters and search refine it without adding navigation complexity.

- Start with a small editorial-style “What matters” list: a few high-signal developments, grouped duplicates and a concise “why it matters”. Do not enforce a fixed number when evidence is sparse.
- Offer simple subject chips/filters (for example AI & technology, science, markets, sport and current affairs) that the owner can change. Do not render a permanent multi-column wall of categories.
- Let the user switch between a concise briefing and a deeper chronological/topic view. Search and “Ask Atlas about this” should be obvious; advanced filters stay collapsed until requested.
- Sports content can lead into fixtures, results, Olympics coverage, player/team profiles or historical Statsguru-style queries. Those are focused workspaces launched from Explore or Ask Atlas, not extra dashboard panels permanently shown together.
- Markets content is explanatory and clearly separates public market context from the owner's personal holdings. Portfolio-specific analysis opens the Investments workspace contextually.
- Every story carries publisher/source, publication time, original-source link where available, and clear distinction between confirmed reporting, analysis, opinion and unverified claims.
- The owner can follow/mute topics and adjust emphasis. The ranking must favour relevance, reliability, novelty and materiality—not outrage, popularity alone or endless engagement.
- Empty, stale, unavailable and disconnected-source states must be honest and useful. Never fabricate stories, scores, prices or trend signals.

### 4.1.3 Focused workspace dashboards — only when the task needs them

Some tasks genuinely benefit from a purpose-built workspace. These are opened contextually and designed around one user goal, not exposed as permanent dashboards. Examples include a portfolio review, a home energy diagnosis, a cricket statistics comparison, an Olympics schedule, a nutrition review or a training plan.

Each workspace follows the same hierarchy:
1. **Answer the immediate question first** — a plain-language conclusion or current status, with date/time and key caveat where needed.
2. **Show only the few decision-relevant facts** — the small set of figures, records or options needed for the current task.
3. **Offer one clear next action** — compare, refine, save, ask a follow-up or take an authorised action.
4. **Progressive detail** — expandable filters, tables, charts, methodology, history and source coverage.
5. **Evidence on demand** — every material claim or figure can be traced to its source or deterministic calculation.

Do not force the same dashboard template onto every domain. A cricket comparison needs a well-designed statistical table; home energy needs understandable consumption trends; a fitness plan needs a practical schedule. Reuse typography, spacing, controls, evidence and state patterns, while tailoring the information layout to the task. Never put unrelated domains side by side just to demonstrate Atlas breadth.


### 4.2 Ask Atlas / Conversation

**Purpose:** the universal interface for questions, instructions and cross-domain work.

Layout:
- Conversation history in a readable central column with a comfortable maximum line length.
- Composer anchored at the bottom, with text entry, send, stop/cancel when work is active, and voice entry only when supported.
- Context/source scope is visible and understandable; users can see which authorised source categories are in scope.
- Conversation list/history is available through navigation or a collapsible history surface, not a permanently dominant sidebar competing with the conversation.
- New conversation is easy to start; returning to an existing one preserves context.

Message presentation:
- Distinguish owner messages from Atlas responses clearly but subtly.
- Render structured answers with headings, lists, tables and links where useful.
- Keep citations adjacent to the claims they support.
- Provide a “Sources”/“Show evidence” affordance that reveals the exact source passage and locator, plus source metadata.
- Clearly label verified, partially verified and unverified results; explain what was not checked.
- Show the local model identity only in the transparent, non-intrusive place specified by the PRD; never expose prompts or private model context.
- Never display an unsupported answer as verified.

Composer behaviour:
- Enter sends; Shift+Enter inserts a newline; provide accessible alternatives and do not trap keyboard users.
- Disable duplicate submission while an identical task is being submitted; allow cancellation where the contract supports it.
- Preserve typed content on recoverable failure.
- Explain unavailable source/model states in plain language with a useful next step.
- No attachment upload affordance until attachment ingestion is actually implemented and accepted.

### 4.3 Task progress and result lifecycle

A task must have a visible, understandable lifecycle without exposing internal event names:
- Received.
- Checking access.
- Waiting (when queued).
- Working.
- Searching sources.
- Preparing an answer.
- Checking the answer and citations.
- Completed, completed with limitations, failed, cancelled or expired.

Show only meaningful progress supported by actual task events. Never invent a percentage or countdown. Avoid rapid flicker; coalesce transient events. Long-running work must not freeze the window or composer. Provide a clear cancel action while cancellation is possible and a truthful terminal explanation.

For partial results, state what completed, what did not, why, and whether the user can retry. For failure, preserve the question and any safe recoverable state.

### 4.4 Evidence and source inspection

Evidence is a first-class part of Atlas, not a technical debug panel.

A source detail view or inspector must show:
- Human-readable source name and type.
- Relevant date/time and available author/sender metadata.
- Exact passage or excerpt supporting the answer.
- Stable locator (page, section, message, attachment locator, or equivalent) in human language.
- Open/reveal-in-source action when supported.
- Clear indication when source access is unavailable, stale or incomplete.

Do not expose internal database IDs, absolute paths, raw payloads or parser traces by default. Do not imply an attachment was read when it was not.

### 4.5 Library

**Purpose:** discover and inspect indexed material across source types.

Required structure:
- Search field with clear scope.
- Source-type filters for available categories.
- Sort options with explicit labels and stable ordering.
- Results with title, type, useful date and concise matched context.
- A source detail/preview surface with provenance and indexing/coverage status.
- Clear empty, loading, unsupported, denied and indexing states.

The Library must communicate the difference between “not found”, “not indexed yet”, “unsupported” and “not authorised”. Never present an incomplete index as a complete search.

### 4.6 Life-area views

Each delivered life area uses a common template:
- A short area summary grounded in available data.
- The most useful domain-specific records or trends.
- A way to ask Atlas about that area.
- Evidence/provenance on every material figure or claim.
- Clear unavailable/stale/incomplete data states.

Finance must distinguish balances, transactions, investments and projections; never imply an estimated value is a verified balance. Travel must distinguish plans, bookings and suggestions. Health, when introduced, requires its own privacy/access presentation and must not be exposed before its product and permission gates are accepted.

Do not invent domain widgets or metrics merely to fill a page. If there is not enough reliable data, show a useful empty state.

### 4.7 Activity and notifications

One chronological activity surface for:
- Active and recently completed tasks.
- Meaningful source updates.
- Important deadlines or detected risks.
- Decisions awaiting owner attention.
- Consequential actions and their outcomes.

Notifications must be material, deduplicated and actionable. No noisy “Atlas is alive” notifications. Every notification explains why it matters and opens the relevant task, evidence or decision. User controls for notification categories and quiet behaviour belong in Settings when implemented.

### 4.8 Approval and action confirmation

Only the PRD's closed list of consequential external/destructive actions can require approval. The confirmation surface must show the exact action, destination/recipient, payload or item, amount/terms where relevant, and consequences. Any material change invalidates the approval. No blanket “approve all”, no approval inferred from email/document content, and no prompt for ordinary read-only or reversible local work.

### 4.9 Settings

Organise settings into clear sections:
- Sources and access.
- Privacy, memory and retention.
- Local models and runtime.
- Connected devices and security.
- Notifications.
- Appearance and accessibility.
- Diagnostics and support.

Settings must distinguish current state from actions. Revocation and deletion are explicit, understandable and auditable. Do not display controls that are not implemented. Avoid repeating onboarding prompts; source access follows the one-time Get Started consent and OS permission model defined in the PRD.

### 4.10 First-run Get Started

A single, short onboarding flow that explains:
1. Atlas runs locally and what that means.
2. Which source categories can be enabled.
3. What access is being granted and how to change/revoke it later.
4. The choice to continue without enabling sources.

Use one clear decision point plus the necessary macOS permission prompts. No per-folder consent wizard, repeated prompts or preselected permissions. Empty selection is a valid path and must remain useful.


### 4.11 Explore — followed subjects and current intelligence

**Purpose:** make Atlas a useful intelligence destination for the subjects the owner follows, without turning it into an endless social feed.

Explore is one destination with a small, switchable set of subject views. AI & technology, science, markets and sports are grouped here; politics/current affairs and other followed subjects appear as topics or briefing filters, not as extra navigation destinations:
- **AI & Technology:** a concise, personalised briefing on meaningful AI, software, hardware and science developments. Each story shows publisher, time, primary-source link where available, a short explanation of what happened, why it matters and what remains uncertain. Cluster duplicate coverage and separate confirmed announcements from commentary, speculation and rumour.
- **Markets:** market context and watchlist movements that help explain what changed. This is not a substitute for the owner's personal portfolio; links from market stories into Investments must preserve the distinction between public market information and personal holdings.
- **Sports:** fixtures, live scores (only where a reliable live source is connected), results, tables, player/team profiles and statistics. Include a natural-language Stats query workspace with filters for competition, season, team and player, designed for deeper historical/statistical questions rather than just score tiles.

Interaction:
- A compact top-level selector switches among AI & Technology, Markets and Sports; avoid three permanent columns or a wall of cards.
- Briefing items are ranked by owner-selected topics, materiality, recency and source quality—not engagement bait. The owner can follow, mute or reprioritise topics.
- Offer “Ask Atlas about this” on every item, carrying the source and context into conversation.
- Support a short daily briefing and on-demand deep research. Do not send routine notifications for every new item; notify only for owner-configured material events.
- Show “updated at” time and source coverage. Distinguish live, delayed, final, scheduled, historical and unavailable states.
- Empty states invite the owner to choose topics or ask a question; never populate with fabricated sample headlines, scores or market movements.
- No infinite scroll by default. Prefer a finite, prioritised briefing with “show more” and search.

### 4.12 Investments — contextual personal portfolio workspace

Investments is a focused workspace opened when the owner asks about their portfolio or follows an investment-related link. It is not a permanent navigation destination, a separate application or a requirement to browse a Finance section first. It should help the owner understand what they own and the risks they are taking, not encourage constant trading.

Primary hierarchy:
1. **Portfolio summary:** total value and day/period change only when supported by current, timestamped holdings and prices; clearly label currency and as-of time.
2. **Allocation:** asset-class, region, sector and holding weights, with a simple readable visual and an accessible table alternative.
3. **Risk & overlap:** concentration, top holdings, sector/country exposure, fund overlap, volatility/drawdown context and bond/cash balance where data permits.
4. **Performance & contributions:** time-weighted or money-weighted method stated explicitly; contributions, income and fees kept distinct from market return.
5. **Research & scenarios:** compare funds/assets, fees, structure, liquidity, tracking, historical drawdowns and hypothetical allocation changes with assumptions and uncertainty visible.

Rules:
- Separate verified account/holding records, delayed market prices, derived calculations, forecasts and opinions.
- Every value has currency, timestamp, source and calculation method available through Show evidence.
- Never show a projected return as a promised return or treat a short historical period as a reliable forecast.
- Keep watchlists and research available without mixing them into owned holdings.
- No trading, payment or transfer without the exact approval required by the PRD.
- Default to calm periodic understanding, not flashing tickers, red/green alarmism or gamified performance.


### 4.13 Contextual capability workspaces

A capability workspace is a temporary, task-focused presentation—not another permanent section of the app. Use it only when a task benefits from a dedicated layout (for example, a cricket statistics comparison, an investment allocation review, a home-energy analysis or a fitness plan).

- Open the workspace from the originating question, briefing item, search result or relevant evidence. Preserve the user's context and provide a clear route back to the originating conversation or view.
- Keep the workspace focused on the current goal. Do not combine unrelated domains merely because they share a data source or internal implementation.
- Show a concise result or summary first. Put detailed filters, historical tables, charts, methodology, source coverage and configuration behind progressive disclosure.
- Reuse shared patterns for search, filters, date ranges, evidence, empty states, unavailable data and “Ask Atlas about this”. Do not create a bespoke visual language for each capability.
- A Statsguru-style cricket query, Olympics lookup, investment analysis, nutrition plan or home-automation task must be usable through natural language even if its advanced workspace has not yet been opened.
- Return to the same task and preserve filters/results when the owner navigates away and back, subject to normal privacy and retention rules.
- Never create a new top-level navigation item solely because a workspace has its own screen, API, specialist agent or integration.


## 5. Shared interaction and component patterns

Build a reusable SwiftUI component library for:
- App shell, sidebar and page header.
- Search and command field.
- Conversation turn, composer and message content.
- Task status/progress and terminal-state notice.
- Citation chip, evidence row and source inspector.
- Source list/result row and filters.
- Empty, loading, unavailable, denied, partial and error states.
- Notification/activity row.
- Approval summary and confirmation.
- Settings row, toggle, permission status and destructive confirmation.
- Inline help, tooltip, banner and non-blocking toast.

Each component must define supported variants, accessibility labels, keyboard behaviour, loading/disabled states and semantic colours. Reuse patterns; do not create near-duplicate components per domain.

### Interaction rules
- Prefer direct manipulation and standard macOS controls.
- Keep primary actions obvious and secondary actions quiet.
- Use confirmation only for destructive or consequential actions, not routine navigation.
- Provide undo for reversible local changes where feasible.
- Avoid modal dialogs for ordinary progress or information.
- Use sheets for focused decisions, popovers for brief contextual controls, and inspectors for persistent supporting detail.
- Maintain selection and scroll position when returning from detail views.
- Use explicit labels; icon-only controls require accessible labels and tooltips.
- All actions must have visible feedback and a recoverable error path.

## 6. Responsive macOS behaviour

The application must be usable at common Mac window sizes and when resized:
- At wide sizes, use the sidebar plus a readable main content column; optional evidence inspector may occupy a trailing column.
- At medium sizes, collapse secondary inspectors before compressing body text.
- At narrow sizes, switch to compact navigation and single-column content.
- No horizontal scrolling for normal conversation, settings or source lists.
- Tables may scroll horizontally only when the data genuinely requires it and an accessible alternative is provided.
- Respect system text-size/accessibility settings and avoid fixed heights that clip content.

The design must not assume a single screenshot-sized window.

## 7. Accessibility and inclusive interaction

Accessibility is a release requirement, not polish:
- Full keyboard navigation and visible focus.
- VoiceOver names, roles, values, grouping and logical reading order.
- Dynamic Type/system text scaling where supported.
- Sufficient text and non-text contrast in light and dark appearances.
- Status communicated without colour alone.
- Reduce Motion support.
- No time-limited interaction without a way to extend or disable it.
- Controls large enough for reliable interaction.
- Meaningful labels for progress, errors, charts and evidence.
- Localisation-ready layouts; no hard-coded assumptions that break with longer text.

Claude must run automated accessibility checks where available and complete a manual VoiceOver/keyboard walkthrough on a real Mac. A passing build is not an accessibility audit.

## 8. Content design and terminology

Voice: calm, direct, respectful, plain language. Atlas should sound capable without being cute, theatrical, sales-like or overconfident.

Use consistent terms:
- “Atlas” for the product/assistant.
- “Ask Atlas” for the universal conversational workspace.
- “Library” for indexed source material.
- “Sources” for connected/authorised categories and their evidence.
- “Activity” for tasks, updates and outcomes.
- “Needs your attention” for material decisions or issues.
- “Show evidence” / “Sources” for claim provenance.

Avoid internal terms such as Core, worker, contract, API, policy gate, event envelope, vector index, provider adapter or task state in user-facing copy unless shown in a clearly labelled developer diagnostics view.

Every empty state should explain what the space is for and the next useful action. Every error should state what happened, whether data was changed or sent, and what the user can do next. Do not claim “private”, “local”, “verified”, “complete” or “done” unless the underlying state supports it.

## 9. Privacy and trust in the interface

The UI must reinforce, not merely describe, the product's privacy architecture:
- Show which source categories are enabled and their access status.
- Make denied, unavailable, stale and incomplete sources distinguishable.
- Explain local processing and never imply cloud inference.
- Do not expose private content in notifications or lock-screen previews by default.
- Keep diagnostics redacted; never surface prompts, secrets, private source content or raw exception traces.
- Show provenance for important facts, conclusions and actions.
- Make memory review, correction, expiry and deletion understandable and owner-controlled when implemented.
- Do not make privacy controls visually obscure or bury revocation.

## 10. Design tokens and implementation architecture

Create one canonical design-token layer for colour, typography, spacing, sizing, radii, borders, elevation and motion. Tokens must support light/dark appearances and accessibility contrast. Avoid view-local magic numbers.

Use reusable SwiftUI views and view models with clear separation between:
- Presentation and navigation.
- Core API/client state.
- Domain content.
- Accessibility and localisation labels.

The UI must render only states supported by the versioned Core contracts. Presentation must not infer permission, completion, verification or source coverage from missing fields. Unknown future contract values must fail safely into a plain-language unavailable state rather than crash or display raw values.

The two copies of `ux_catalogue.json` must remain synchronised and contract-complete. The catalogue is user-facing copy, not a substitute for a complete screen design system.

## 11. Required screen and state inventory

The implementation must account for each of these states, not just the happy path:

| Surface | Required states |
|---|---|
| App launch | first launch, returning launch, Core starting, Core unavailable |
| Get Started | no source selected, one/multiple selected, OS permission granted/denied, consent completed |
| Home | populated, no activity, attention item, loading, partial source availability |
| Conversation | empty, composing, submitted, queued, running, completed, partial, failed, cancelled, expired |
| Evidence | available, missing, stale, source denied, unsupported locator |
| Library | initial, loading, results, no results, not indexed, unsupported, denied, partial coverage |
| Life area | populated, empty, stale, unavailable, partial data |
| Activity | active tasks, no activity, completed, failure, notification |
| Approval | pending, exact details changed/invalidated, approved, declined, expired, completed |
| Settings | current values, saving, saved, failed, permission revoked, destructive confirmation |
| Global | light/dark, resized window, offline/Core unreachable, accessibility/large text |

No screen may silently render an empty blank panel for an unhandled state.

## 12. Visual quality bar

A screen is not accepted because it compiles. Each implemented screen must pass:
1. **Hierarchy:** first glance reveals the screen's purpose and primary action.
2. **Focus:** no unnecessary card, metric, badge or persistent panel competes for attention.
3. **Completeness:** all relevant states in §11 have intentional UI.
4. **Consistency:** shared tokens and components are used; no one-off visual language.
5. **Legibility:** readable at normal and enlarged system text sizes.
6. **Evidence:** material claims and figures have a clear source path.
7. **Truthfulness:** no fabricated data, fake progress or misleading status.
8. **Resilience:** resize, unavailable Core, denied access and partial data remain understandable.
9. **Accessibility:** keyboard, VoiceOver, contrast and Reduce Motion are checked.
10. **Finish:** spacing, alignment, truncation, focus, animation and error recovery feel deliberate.

Screenshots must be captured from the running application on the target Mac at a documented window size, in both light and dark appearance. Capture the core flows and important failure/empty states. Review them against this spec, fix defects, and attach before/after evidence to PR #8.

## 13. Delivery sequence, ownership and acceptance gates

### Documentation gate — COMPLETE

- Product experience direction and anti-goals documented.
- Information architecture and global navigation documented.
- Home, conversation, progress, evidence, Library, life-area, Activity, approval, Settings and onboarding surfaces specified.
- Shared components and interaction rules specified.
- Responsive behaviour, accessibility, content design and privacy presentation specified.
- Required state inventory and visual acceptance rubric specified.
- Claude implementation handoff and evidence requirements recorded.

### Implementation gate — NOT COMPLETE

Claude owns:
1. Review this document together with PRD, target architecture, use-case register, accepted Stage 3 plan and the current app code.
2. Produce a screen-by-screen implementation map: existing view/component → target screen/requirement → gap → planned change.
3. Implement the reusable design-token layer and app shell/navigation before expanding individual screens.
4. Implement the approved screen hierarchy and shared components; do not add unapproved product scope.
5. Keep all existing policy, privacy, contract and consent guarantees intact.
6. Add automated UI/component/state tests and synchronisation/completeness tests for the UX catalogue.
7. Build and launch the app on a real Mac; do not treat hosted CI launch as owner-machine verification.
8. Capture actual screenshots and run the manual design/accessibility walkthrough.
9. Report exact commit SHA, commands, test results, machine/environment, screenshots, known gaps and any decision requiring owner input.

### Architect review gate — NOT COMPLETE

ChatGPT reviews the implementation against this specification and the exact commit, checks traceability and evidence, records findings, and re-reviews fixes. One consolidated review should identify all known defects; do not create repeated review loops for already documented issues.

### Owner visual acceptance gate — NOT COMPLETE

The owner must see and use the real running app, review the key screens and flows, and explicitly accept the visual/interaction result. No proxy, CI run or architect opinion substitutes for this acceptance.

### Final UI/UX completion rule

The UI/UX phase may be called **fully complete** only when the documentation, implementation, architect review and owner visual acceptance gates are all complete. Until then, report the exact gate completed and the remaining gates without calling the phase finished.

## 14. Claude handoff — execution instructions

This specification is now the canonical UI/UX contract. Do not ask the owner to restate the visual direction or relay this handoff.

Work within the existing single PR #8 and branch `genesis-stage2-foundation`. Do not create another PR, merge, alter Stage 3 scope, or claim owner acceptance. Documentation ownership remains with ChatGPT; Claude owns implementation and reproducible evidence.

First response on PR #8 must:
- Acknowledge this specification and identify the exact commit containing it.
- Provide the screen-by-screen implementation map requested in §13.
- Identify which current app screens already satisfy the spec and which do not, with file paths and evidence.
- Propose the smallest coherent implementation sequence, starting with tokens and app shell.
- State what can be verified in CI versus what requires the owner's Mac.
- Then implement, test and report in the same PR; do not stop at another plan-only response.

Do not mark a gate complete because code exists. Attach test evidence and actual running-app screenshots. Keep one-PR discipline and exact-commit review discipline.
