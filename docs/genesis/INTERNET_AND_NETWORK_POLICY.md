# Atlas — Internet and Network Policy

**Status:** Architecture policy baseline; implementation and platform behaviour must be verified.  
**Owner direction:** Local-only inference; public Internet research is allowed when useful; no silent personal-data egress; integrations use owner-authorised accounts.

## 1. Core decisions

1. Atlas may connect to the public Internet for search, public-page retrieval, official-source verification, product/travel research, weather and other tasks that require current information.
2. Public Internet access is not permission to upload personal files, private messages, health/finance records, memory, credentials, prompts containing personal context or local indexes.
3. All AI inference remains local. No cloud model API, remote agent brain, cloud fallback or third-party hosted Atlas Core.
4. Internet content is untrusted data. It cannot change Atlas policy, grant permissions, approve an action, invoke tools by instruction or widen a task.
5. Network access is mediated by Atlas Core through a purpose-specific, typed and observable boundary: public research uses the egress gateway; owner-authorised integrations use connector transport; paired devices use the private/VPN relay; and page reading uses the isolated browser engine. These paths have separate allowlists, credentials, trust boundaries and acceptance gates. Domain capabilities and agents do not open arbitrary sockets or bypass policy.
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

Before a network request, Core determines purpose, destination, data class, minimum necessary fields, whether the request can be anonymised, whether a connector grant exists, and whether the request has an external side effect. Ask the owner only if no safe useful request can be formed and the missing detail is essential; otherwise do not send the request and continue locally or report the online step unavailable.

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

Approval is required only for the closed list in PRD §4.4: sending/sharing/publishing/uploading outside the Mac; spending/paying/trading/purchasing/paid bookings; deletion/overwrite without reliable undo or destructive migration; and unlocking external physical access or disabling safety/security systems. Everything else never triggers an Atlas approval prompt.

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
- Every network connection must use its approved Core-mediated path and its purpose-specific policy, destination, credential and audit controls; no model or agent may open an arbitrary socket.
- Tokens are stored in Keychain and absent from logs/crash reports.
- Revocation blocks subsequent reads/writes and invalidates caches.
- Malicious pages and files cannot cause tool calls, policy changes or external actions.
- Upload/send flows require exact-payload approval and cannot reuse stale approvals.
- Offline operation is clear and useful.

Target-Mac Keychain, sandbox, firewall, network monitoring and app entitlements remain unverified until tested on the target Mac. This policy is a design requirement, not evidence that enforcement already exists.

## 10. Egress taint, URL safety and network isolation

### 10.1 Taint rule for private context
A task that has read private owner data (especially Finance or Health) or untrusted content is tainted for network egress. It cannot pass free-form model context into a public request.

- Public search is exposed only as a typed Core tool with a fixed schema. Query text is generated from the public task objective and declassified constraints, not copied from private passages, email bodies, prompts or memory.
- If a task combines private data and untrusted content, the coordinator creates a separate public-research subtask containing only the minimum non-sensitive question. It receives no private passages, source text, identifiers or secrets.
- The egress gateway checks outgoing URL, query, path, subdomain and headers for exact/near substring matches against private-context spans, HMAC/n-gram fingerprints, common encodings (URL/base64/hex) and suspicious high-entropy payloads. Blocked requests are audited locally without logging the private string.
- When private context is present, custom headers, cookies, arbitrary model-composed URLs and free-form request bodies are prohibited. Query and URL lengths are capped. Redirects are revalidated at every hop.
- Fetch is limited to an explicit owner-provided URL or a URL returned by the current task's approved search results. The gateway blocks loopback, private, link-local, multicast, reserved and metadata-service IP ranges; DNS is resolved and validated at connection time to mitigate rebinding; redirects repeat the same checks.
- A leak scanner cannot reliably detect every semantic paraphrase. Therefore private-context tasks use templated public queries and never allow arbitrary free-text egress. If a safe query cannot be constructed, skip web search; do not ask routinely or upload private context.

### 10.2 Rendering and OAuth callbacks
- Atlas never auto-loads remote images, avatars, tracking pixels, link previews or other network resources embedded in model output or retrieved content. Links open only after an owner click and display the destination first.
- OAuth callback listeners bind only to loopback addresses or a Unix-domain socket, use a short-lived unpredictable state/PKCE flow and close immediately after callback. Never bind to 0.0.0.0 or a LAN/public interface.

### 10.3 Host allowlists and model isolation
- Maintain separate host allowlists for the selected search provider, each explicitly connected provider, signed application-update manifests and approved model-weight distribution. No other process inherits those allowlists.
- The model worker has no outbound network entitlement and no connector credentials. It communicates with Core only through a local authenticated IPC boundary. Enforce with the strongest supported macOS sandbox/firewall controls; target-Mac verification is mandatory.
- App updates and model weights are fetched only from approved publisher hosts and accepted only after signature/manifest verification and pinned hash checks. No downloaded executable or model runs before verification.

### 10.4 Search-provider decision
Default public search provider recommendation: **Brave Search API**, behind a replaceable provider adapter. It offers a dedicated search API and an independent index. Its published Search plan is currently listed at USD $5 per 1,000 requests with monthly credits; this is a paid third-party dependency, not a guaranteed free service. The owner must not be silently enrolled or billed. Default it off until the owner explicitly enables the provider and sets a budget; keep a no-cost/manual fallback available where technically feasible. Search queries are transmitted to Brave and are visible to the provider; Brave's privacy notice treats Search Query Data separately from its data-processing addendum. Atlas therefore sends only sanitised public queries, never owner-private context. This is a deliberate, limited third-party disclosure for public search—not local-only networking. Search results are transient by default; do not build a persistent copy of the provider result corpus. Re-check current pricing, privacy notice and licence terms before release.

Primary references:
- https://api-dashboard.search.brave.com/documentation
- https://api-dashboard.search.brave.com/privacy-policy
- https://api-dashboard.search.brave.com/documentation/resources/terms-of-service

### 10.5 Gmail connector risk
Apple Mail's local store is the preferred first Mail integration. A direct Gmail API connector is deferred until its OAuth lifecycle and scope/verification requirements are accepted. Google's official OAuth documentation states that external apps in Testing status generally receive refresh tokens that expire after seven days; Gmail read-only scopes are classified as restricted and can require verification. Personal-use exceptions exist but must not be assumed to remove all warnings or lifecycle constraints.

References:
- https://developers.google.com/identity/protocols/oauth2
- https://developers.google.com/workspace/gmail/api/auth/scopes
- https://developers.google.com/identity/protocols/oauth2/production-readiness/restricted-scope-verification

### 10.6 Operational and cost controls
- Set a per-task request budget, global daily cap and rate limit; expose provider usage and estimated cost in local diagnostics.
- No background polling without an owner-visible purpose, cadence and stop condition.
- Provider failure must not trigger fallback to a provider with weaker privacy/contract terms without an explicit architecture decision.
