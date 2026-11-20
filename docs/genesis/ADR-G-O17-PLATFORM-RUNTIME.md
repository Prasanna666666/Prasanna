# ADR G-O17 — macOS/iOS Application Runtime and Core API Boundary

**Status:** ACCEPTED BY OWNER — 2026-11-20  
**Stage 2 authority:** AUTHORISED BY OWNER — 2026-11-20; ChatGPT package-acceptance gate waived by owner  
**Decision owner:** Atlas owner  
**Prepared by:** ChatGPT, Architect / Integrator  
**Technical challenge:** Claude review recorded in PR #7 comment 7035425400; reconciled by ChatGPT  
**Scope:** macOS/iOS application language and UI runtime, shared application-code boundary, Core API boundary and packaging direction. The language/runtime of the Mac-host Core is explicitly deferred to G-O20. The owner's later MLX inference-runtime direction and benchmark-led ~27B model strategy are recorded separately in G-020; this ADR does not select an exact model, quantisation, database, vector store, or remote-access topology.

## 1. Decision to make

Choose the application technology that best delivers one Atlas application on macOS first and iOS second, with one shared codebase as the owner's highest criterion, while preserving local-only inference, native Apple integration, responsive interaction, security boundaries and a safe migration path from the current Python/Docker implementation.

## 2. Owner constraints and non-negotiables

- One Atlas product/application; no separate Finance, Documents or Images apps.
- Target platforms: macOS first, then iOS. Android is out of scope.
- One shared codebase across macOS and iPhone is the top technology criterion.
- Native macOS delivery and one-click integrity-verified updates are target requirements. Distribution assumption recorded from the owner (2026-11-19): direct download, Developer ID signed and notarised; not Mac App Store sandbox distribution. Exact packaging, helper signing, update and rollback implementation remains G-O12.
- Atlas Core and inference remain under owner control. No cloud inference or silent remote fallback.
- Worldwide iOS access is through a secure channel to the owner's host; it does not move inference or private data processing to a third-party AI service.
- 32 GB Apple-silicon Mac mini is a planning profile, not a benchmark result.
- Existing Python capabilities and tests are migration assets, not constraints. Reuse them where they are the best choice; replace or rewrite components when requirement-level evidence supports doing so, with parity, data-preservation and rollback evidence.
- The current app is Python services plus Docker/HTTP boundaries, web UI, SQLCipher SQLite, and Ollama integration (Stage 1 audit, PR #7 comments 7022436618 and 7022456916). Stage 1 evidence was code inspection and scratch-environment tests, not target-Mac verification.
- All exact calculations remain deterministic. Finance stays outside model/general-agent context under G-015. Health remains locked by default.

## 3. Keep these technology decisions separate

This ADR resolves the application layer and the boundary to the Mac-host Core. It does **not** select the Core's implementation language/runtime; that is a separate open decision, G-O20. G-O17 is therefore explicitly scoped to the application layer, Core API boundary and packaging direction. It does not decide:
- The exact local model family, quantisation, context length and fallback behaviour (G-O01). The owner has selected Apple MLX as the inference-runtime direction and a benchmark-led ~27B main-model class (G-020); this does not decide the Mac-host Core language (G-O20).
- Storage/search/encryption/key architecture (G-O02).
- Backup, restore and key recovery (G-O05).
- Secure worldwide remote access, device identity or offline sync (G-O14/G-O15).
- Native update/signing implementation details beyond the chosen application boundary (G-O12).
- The Mac-host Core language/runtime (G-O20); the current Python Core is an interim implementation choice, not a permanent commitment.

Do not select Ollama, llama.cpp, a model family or a database merely because an application framework supports it. **Apple MLX was selected separately by the owner as the local inference-runtime direction (G-020);** this ADR does not reopen that owner decision.

## 4. Shortlist

### A. Swift + SwiftUI + shared Swift packages

One Xcode project and shared Swift source for the macOS and iOS applications; SwiftUI for adaptive UI; shared Swift packages/modules for client state, domain contracts, validation and API clients; narrow platform adapters for macOS/iOS-only capabilities.

**Strengths**
- Best fit for the committed Apple-only platform set and the native macOS/iOS product requirement.
- One language and one shared application codebase; Apple supports multiplatform targets and shared SwiftUI code across iOS and macOS.
- Direct access to Apple platform APIs, Keychain, sandboxing, background execution, notifications, file access and native UI without a cross-framework bridge for ordinary app work.
- Natural boundary for a Mac-hosted Atlas Core and an iOS remote client; the same client/domain contracts can be used by both.
- Native app packaging, signing and distribution align with Xcode and Apple platform tooling.

**Costs / risks**
- Apple-platform lock-in is deliberate; this is acceptable only while Android remains out of scope.
- Some APIs and UX must still be platform-specific; shared codebase does not mean every view or OS capability is identical.
- The current Python services cannot simply be imported into iOS. Preserve them behind a narrow, versioned local Core API initially; port only when justified and after parity tests. This means the repository may temporarily contain Swift client code and Python host services, even though the Mac/iOS application layer is shared.
- SwiftUI and native inference integration still require target-device profiling; no performance result is assumed.

### B. Flutter + Dart

One Dart/Flutter UI and application layer targeting iOS and macOS, with native Swift/Objective-C adapters for Apple-specific APIs and native libraries.

**Strengths**
- Strong single-codebase story across iOS and macOS; both platforms are officially supported.
- Mature cross-platform UI framework and clear native integration mechanisms.
- Can integrate with existing native applications or native modules.

**Costs / risks**
- Flutter renders its own widget UI rather than using the operating system's native widgets. Cupertino styling is available, but native behaviour/accessibility and macOS interaction details need deliberate validation.
- Apple-specific capabilities and low-level inference libraries require platform plugins/FFI. Flutter's current Pigeon native-interop path is documented as preview; platform channels remain the established alternative.
- Adds a UI engine/runtime and a Dart/native boundary despite the product targeting only Apple's platforms.
- It does not remove the need for a separate Mac-host Core API or the Python migration question.

### C. Kotlin Multiplatform + Compose Multiplatform

Shared Kotlin logic and optionally shared Compose UI for iOS and macOS, with Swift/Objective-C interop and platform adapters.

**Strengths**
- Officially stable Compose Multiplatform targets include iOS and desktop/macOS.
- Can share both business logic and UI; can also retain native SwiftUI integration where appropriate.
- Strong typed shared-code model and a route to a common Kotlin core.

**Costs / risks**
- macOS desktop uses the JVM while iOS uses Kotlin/Native; build, packaging, runtime and native integration are not identical across targets.
- Compose UI is rendered by the framework rather than being the system's native SwiftUI controls; native platform fidelity needs validation.
- Adds Kotlin/Gradle and Swift/Xcode toolchains for an Apple-only product.
- It does not avoid the Python service migration or host-Core boundary.

### D. Rust core + Tauri 2 (web UI)

Shared Rust core and web UI packaged in Tauri for macOS and iOS, with platform plugins for native functionality.

**Strengths**
- Rust offers strong memory-safety properties for core components and a useful FFI boundary.
- Tauri documents both macOS desktop and iOS development paths.
- Could reuse web UI skills and share Rust logic across platforms.

**Costs / risks**
- The UI is web content inside platform web views, not a native SwiftUI interface.
- iOS requires Xcode and additional mobile-target setup; native Apple integrations require plugins/bridges.
- Rust plus web UI plus Swift host/plugin code creates multiple implementation layers.
- Higher integration and packaging complexity for a product whose committed platforms are exclusively Apple's.

## 5. Comparative assessment

Qualitative assessment against this product's constraints; not benchmark results.

| Criterion | Swift / SwiftUI | Flutter / Dart | Kotlin / Compose | Rust / Tauri |
|---|---|---|---|---|
| Shared macOS+iOS application code | Excellent | Excellent | Excellent | Good |
| Native Apple UX and APIs | Excellent | Good; native bridges | Good; native bridges | Fair–Good; plugins |
| Native macOS app and Apple packaging fit | Excellent | Good | Good | Good |
| Local native library / inference integration | Excellent | Good; FFI/plugin boundary | Good; Kotlin/Native interop | Excellent at core level; host plugins |
| Simplicity for Apple-only target | Excellent | Good | Fair–Good | Fair |
| Existing Python capability reuse | Requires API boundary | Requires API boundary | Requires API boundary | Requires API boundary |
| Long-term Apple-platform maintenance | Excellent | Good | Good | Good |
| Additional framework/toolchain burden | Lowest | Medium | Medium–High | High |

No framework can be selected responsibly from marketing claims alone. The actual proof must build the same small vertical slice on macOS and iOS and measure packaging, startup, responsiveness, native integration, memory and maintenance cost.

## 6. Recommendation for owner decision

**Recommend A: Swift + SwiftUI + shared Swift packages**, subject to Claude's technical challenge and the owner's explicit acceptance.

Reason: the committed platform set is macOS+iOS only. SwiftUI offers one shared Apple-native application codebase without adding a cross-platform rendering framework. It aligns best with native macOS delivery, iOS distribution, Apple security APIs and the future iOS client. Android portability is no longer a requirement and should not drive framework selection.

**Migration strategy:** keep the existing Mac-host Core behind a narrow, versioned API while the shared SwiftUI application layer is established. Python is the current implementation baseline, not a permanent language decision. Reuse existing capabilities where they are the best choice; replace them when requirements and evidence justify it. No big-bang rewrite is proposed. The iOS client connects securely to the owner-controlled Mac Core; it does not run cloud inference.

**Owner's interpretation of “one codebase”:** the owner previously answered “not sure, decide on evidence.” The evidence-based interpretation adopted here is one shared macOS/iOS application codebase, with a separately hosted Core behind a language-neutral API. This preserves the shared app codebase criterion without forcing a Core rewrite before its own evidence-based decision (G-O20).

## 7. Migration cost and interim option

Claude's repository inspection found approximately 11,800 lines of existing JS/HTML/CSS across the Atlas, Finance and Library interfaces, plus approximately 1,200 lines of shared design code. A SwiftUI choice means a staged UI migration; it is not UI reuse. Treat these counts as repository-inspection estimates, not independently measured product scope. Do not rewrite all screens in one step.

A temporary native macOS shell hosting the existing web UI in WKWebView is a viable migration option to compare during a later implementation plan. It may reduce time-to-first-native-shell but trades off native interaction and does not remove the eventual iOS UI work. It is not selected or authorised by this ADR.

## 8. API, security and packaging consequences

- The current chat endpoint returns a single JSON response and has no streaming/cancellation contract. A sub-two-second first-useful-output target cannot be responsibly assessed until progress/token streaming and cancellation are designed and measured.
- Current browser Origin/header checks are not native client or device authentication. “Localhost” is not an identity boundary. The Core must authenticate each client; Claude recommends per-client keys/signatures and local Unix-domain-socket peer-credential checks. The exact mechanism belongs in the contract/security design and must not be mistaken for the G-O14 remote-access design.
- Direct-download distribution requires a signed/notarised Mac app and careful signing of nested binaries/helpers. Embedding Python and ML dependencies may materially affect footprint, startup, update and notarisation complexity. This is a G-O12 implementation risk, not proven solved by this ADR.
- The Core API must support streaming/progress, cancellation, version negotiation and user-safe errors. A local API hop is not assumed to be a material latency problem; model and retrieval time must be measured separately.
- Migration temporarily involves the shared Swift app, Mac-host Core and existing web UI until screens are ported. Keep the boundary contract-first and reversible.

## 9. Required technical challenge / proof before acceptance

Claude must assess the recommendation against the actual repository and provide evidence for:

1. Confirm the shared SwiftUI/Xcode project boundary and list genuinely shared versus platform-specific code.
2. Review the contract-first proof approach: versioned OpenAPI 3.1/JSON Schema, Python reference implementation/tests, and generated Swift client validation when a Mac/Xcode runner is available. No code spike is authorised by this ADR.
3. Assess per-client authentication, signed requests, local IPC/transport and the distinction between local authentication and the separately gated G-O14 remote-access design.
4. Assess streaming/progress, cancellation, version negotiation and user-safe errors against the current single-response chat endpoint.
5. Assess Python/Core reuse, packaging/notarisation risks, UI migration cost and the WKWebView interim option.
6. Compare SwiftUI against Flutter and Compose using the current repository, not a greenfield assumption.
7. Identify risks, dependencies and any material technical correction. Do not request another owner questionnaire unless genuinely new evidence makes a reserved decision necessary.

If Claude finds a material blocker, revise the recommendation rather than defend it. No code spike is authorised by this review request.

## 10. Verification status and evidence limits

| Claim / comparison | Status in Claude review |
|---|---|
| Flutter iOS/macOS support; Pigeon native interop preview; platform channels established | Verified from official documentation/search evidence reported by Claude |
| Compose iOS and desktop stability; JVM desktop vs Kotlin/Native iOS | Verified from JetBrains documentation reported by Claude |
| Tauri 2 macOS/iOS support and Xcode requirement | Verified from Tauri documentation/search evidence reported by Claude |
| Apple shared SwiftUI multiplatform target | Not independently verified by Claude; platform claim remains documented but not independently checked in that review |
| Apple `swift-openapi-generator` availability and platform support | Verified from Apple/Swift project sources reported by Claude |
| Current Atlas UI size, API response shape, browser-oriented auth, CI environment and container footprint | Code-inspected by Claude at implementation baseline `7a3b447`; not target-Mac benchmark evidence |
| Embedded Python signing/notarisation feasibility and exact footprint | Not fully verified; treat as an open packaging risk under G-O12 |

No target-Mac build, benchmark or packaging proof has been performed. These are future validation requirements, not implied acceptance evidence.

## 11. Acceptance and consequences

The owner accepted this ADR on 2026-11-20, resolving G-O17 (application layer, Core API boundary and packaging direction). The owner separately authorised Stage 2 on the same date and waived the ChatGPT package-acceptance gate (recorded in PR #7 comment 7037299974 and subsequent owner instructions). This does not decide G-O20 (Core language/runtime), does not accept the Stage 2 implementation, and does not authorise Stage 3. PR #8 remains under independent implementation review.

After acceptance:
- Keep domain contracts independent of SwiftUI views and OS-specific adapters.
- Use a single shared SwiftUI app project/source tree for macOS and iOS, with narrow platform adapters.
- Keep the Mac-host Core behind a versioned API; no cloud inference.
- Require architecture tests for dependency direction and platform leakage.
- Decide the Mac-host Core language/runtime separately through G-O20; do not infer permanent Python selection from this ADR.

Rejected alternatives remain technically viable, but are not preferred for the current Apple-only target.

## 12. Sources

Official platform documentation consulted 2026-11-20:
- Apple, [Configuring a multiplatform app target](https://developer.apple.com/documentation/Xcode/configuring-a-multiplatform-app-target) — Apple platforms can share a target; SwiftUI projects can share substantial code.
- Apple, [SwiftUI](https://developer.apple.com/documentation/swiftui/) — declarative UI and adaptive views across Apple platforms.
- Flutter, [Supported deployment platforms](https://docs.flutter.dev/reference/supported-platforms) — macOS and iOS support.
- Flutter, [Platform channels](https://docs.flutter.dev/platform-integration/platform-channels) — native Swift/Objective-C integration.
- Flutter, [Pigeon](https://docs.flutter.dev/interop/pigeon) — generated native bindings; native interop currently preview.
- JetBrains, [Kotlin Multiplatform FAQ](https://kotlinlang.org/docs/multiplatform/faq.html) — iOS, desktop and shared Compose UI support.
- JetBrains, [Compose Multiplatform compatibility](https://kotlinlang.org/docs/multiplatform/compose-compatibility-and-versioning.html) — supported platform/version matrix.
- Tauri, [Prerequisites](https://v2.tauri.app/start/prerequisites/) — macOS/iOS development toolchain requirements.
