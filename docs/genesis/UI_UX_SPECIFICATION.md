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

## 3. Information architecture and navigation

### 3.1 One application, one navigation model

The user always remains inside Atlas. Domain areas are destinations/filters within Atlas, not separate applications.

The primary macOS navigation is a compact sidebar with:
1. **Home** — current priorities, meaningful changes and resume points.
2. **Ask Atlas** — unified conversation and task workspace.
3. **Library** — searchable, unified access to owner-authorised Documents, Mail, Pictures and other indexed material, with source-type filters.
4. **Life areas** — a single grouped section for enabled domains such as Finance, Travel and (when authorised and delivered) Health. These are views over shared Atlas context, not independent apps.
5. **Activity** — ongoing/recent work, completed tasks, notifications and action history.
6. **Settings** — sources and permissions, models and local runtime, privacy/memory controls, devices, appearance and diagnostics.

Navigation must not expose unavailable or not-yet-implemented domains as if they work. Use progressive disclosure: show a domain only when its product surface is available or explicitly show a clear “not available yet” state where discovery is necessary.

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
