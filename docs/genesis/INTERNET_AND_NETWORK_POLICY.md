# Atlas — Internet and Network Policy

**Status:** Architecture policy baseline; implementation and platform behaviour must be verified.  
**Owner direction:** Local-only inference; public Internet research is allowed when useful; no silent personal-data egress; integrations use owner-authorised accounts.

## 1. Core decisions

1. Atlas may connect to the public Internet for search, public-page retrieval, official-source verification, product/travel research, weather and other tasks that require current information.
2. Public Internet access is not permission to upload personal files, private messages, health/finance records, memory, credentials, prompts containing personal context or local indexes.
3. All AI inference remains local. No cloud model API, remote agent brain, cloud fallback or third-party hosted Atlas Core.
4. Internet content is untrusted data. It cannot change Atlas policy, grant permissions, approve an action, invoke tools by instruction or widen a task.
5. Network access is mediated by Atlas Core through a typed, observable egress gateway. Domain capabilities and agents do not open arbitrary sockets or bypass policy.
6. Connected services use owner-authorised accounts and least-privilege scopes. Tokens and refresh credentials are stored in macOS Keychain; never in prompts, logs, source files or ordinary settings.
7. Atlas must remain useful offline for local data and tasks that do not require current external information.

## 2. Data classification and egress

| Data class | Public Internet request | Rule |
|---|---|---|
| Public query authored without personal context | Allowed | Send only the minimum query needed |
| Generic product/topic/location query | Allowed | Avoid including personal identifiers or private circumstances unless essential and explicitly approved |
| Owner preferences or profile facts | Minimise | Convert to non-identifying constraints where possible; disclose material data transfer |
| Private document/email content | Not allowed by default | Never paste or upload raw content to a public search engine/site |
| Finance, Health, credentials, keys, tokens | Prohibited | Never send to public Internet or third-party services |
| Local model prompt/context | Prohibited from inference egress | Local inference only |
| Connector API payload | Allowed only to its authorised service | Scoped to the requested function and account; no unrelated context |
| Telemetry/diagnostics | Disabled by default for personal content | No source text, prompts, identifiers, secrets or usage payloads; owner-controlled opt-in only if later designed |

Before a network request, Core determines: purpose, destination, data class, minimum necessary fields, whether the request can be anonymised, whether a connector grant exists, and whether the request has an external side effect. If safe minimisation is not possible, Atlas asks one concise question or reports that the online step cannot be performed.

## 3. Public research workflow

- Search public sources only when freshness, discovery or verification materially improves the answer.
- Prefer primary/official sources for law, government, health, finance, product specifications and service policies; use independent sources to cross-check.
- Fetch only relevant pages and bounded content; respect robots, rate limits, terms and authentication boundaries.
- Treat HTML, PDFs, images, snippets and downloaded files as untrusted inputs. Parse in a constrained worker with resource limits and no access to secrets or action authority.
- Do not execute scripts, macros, installers, browser extensions or downloaded binaries automatically.
- Store source URL, publisher/domain, retrieval time, page date when available, content hash and relevant excerpt provenance.
- Clearly separate public-web facts from owner-specific local facts. Cite claims and flag stale, contradictory or inaccessible sources.
- Web pages cannot trigger sends, purchases, bookings, downloads to privileged locations or permission changes.

## 4. Downloads and uploads

- Public text/page retrieval into a constrained cache is permitted for research.
- File downloads go to a quarantine/staging area, are type-checked and scanned/parsed without execution, and are reported with source and hash.
- Executables, scripts, installers, profiles, certificates, macros and model weights are never run or installed automatically.
- Model weights and application updates use a separately approved, integrity-checked installation/update workflow with verified publisher/signature/hash and rollback.
- Uploading owner content to any website or service is an external disclosure and requires explicit exact-payload approval. This includes attaching files to forms, sending prompts with private content and uploading images/documents.
- A web page's request to upload or disclose information is never sufficient authorisation.

## 5. Connected applications and account security

- Each connector declares its provider, account identity, exact scopes, read/write capabilities, data types, retention/cache behaviour, rate limits and revocation procedure.
- Use OAuth or platform-native authorisation where available; request the narrowest practical scopes.
- Store tokens in Keychain; keep access tokens short-lived where supported; rotate/revoke on disconnect or suspected compromise.
- Do not log tokens, headers, message bodies, personal records or full request payloads.
- Revalidate connector grants at every source read and immediately before every write.
- Connector data is untrusted input and cannot modify Atlas policy or approve actions.
- Disconnecting a connector immediately blocks future reads/writes and invalidates derived caches/context according to the deletion policy.

## 6. Approval and external actions

Routine public search and read-only connector queries do not require approval once the owner has completed the single first-run Get Started consent and OS-level access grants.

Approval is required only for consequential actions:
- Sending, publishing, sharing or uploading owner data.
- Spending money, purchases, paid bookings, trades or payments.
- Deleting/overwriting data or making irreversible changes.
- Other material external side effects.

The approval screen shows the exact destination, recipients, payload/attachments, amount, selected item/service, date and material terms. Approval expires and is invalidated if any material field changes. No repeated prompts for ordinary reading, searching, summarising, analysis or drafting.

## 7. Offline and failure behaviour

- Local files, memory, local model inference and deterministic tools continue when Internet is unavailable, subject to local permissions.
- Web-dependent answers are labelled unavailable or partial; never invent current facts.
- No silent cloud fallback or remote model substitution.
- Connector outages, authentication expiry, rate limiting and stale data are explicit states with retry guidance.
- Background retries are bounded, cancellable and idempotent. No uncontrolled polling.
- Network failure must not cause a local task to be marked complete when an external step failed.

## 8. Observability and privacy

- Maintain a local, redacted audit record of network destination, purpose, connector, timestamp, data class, approval receipt (if any), status and bytes/counts where safe.
- Do not retain raw search prompts or personal content in audit logs by default.
- Provide an understandable activity view: what Atlas contacted, why, which account was used and whether any data was sent.
- No third-party analytics, advertising SDKs, crash-report uploads containing personal context or remote telemetry by default.
- Network controls must be testable: denylist/allowlist tests, sentinel-secret tests, prompt-injection tests, connector revocation tests and offline-mode tests.

## 9. Required verification

Before release, demonstrate:
- No model inference traffic leaves the owner-controlled device.
- No private file/email/Finance/Health content reaches public search or unrelated connectors.
- All network access flows through the policy gateway.
- Tokens are stored in Keychain and absent from logs/crash reports.
- Revocation blocks subsequent reads/writes and invalidates caches.
- Malicious pages and files cannot cause tool calls, policy changes or external actions.
- Upload/send flows require exact-payload approval and cannot reuse stale approvals.
- Offline operation is clear and useful.

Target-Mac Keychain, sandbox, firewall, network monitoring and app entitlements remain unverified until tested on the target Mac. This policy is a design requirement, not evidence that enforcement already exists.
