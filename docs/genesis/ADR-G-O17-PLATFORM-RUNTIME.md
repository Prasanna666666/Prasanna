# ADR G-O17 — macOS/iOS Core Language, UI Runtime and Packaging Boundary

**Status:** PROPOSED — not owner-accepted  
**Stage 2 authority:** NOT AUTHORISED; this ADR and the accompanying package are review-only  
**Decision owner:** Atlas owner  
**Prepared by:** ChatGPT, Architect / Integrator  
**Technical challenge requested from:** Claude  
**Scope:** Application language, UI framework, shared-code boundary and packaging direction. This ADR does not select the local LLM/inference engine, database, vector store, or remote-access topology.

## 1. Decision to make

Choose the application technology that best delivers one Atlas application on macOS first and iOS second, with one shared codebase as the owner's highest criterion, while preserving local-only inference, native Apple integration, responsive interaction, security boundaries and a safe migration path from the current Python/Docker implementation.

## 2. Owner constraints and non-negotiables

- One Atlas product/application; no separate Finance, Documents or Images apps.
- Target platforms: macOS first, then iOS. Android is out of scope.
- One shared codebase across macOS and iPhone is the top technology criterion.
- Native macOS delivery and one-click integrity-verified updates are target requirements.
- Atlas Core and inference remain under owner control. No cloud inference or silent remote fallback.
- Worldwide iOS access is through a secure channel to the owner's host; it does not move inference or private data processing to a third-party AI service.
- 32 GB Apple-silicon Mac mini is a planning profile, not a benchmark result.
- Existing Python capabilities and tests are valuable migration assets. Do not discard or rewrite them without a requirement-level justification and parity/rollback evidence.
- The current app is Python services plus Docker/HTTP boundaries, web UI, SQLCipher SQLite, and Ollama integration (Stage 1 audit, PR #7 comments 7022436618 and 7022456916). Stage 1 evidence was code inspection and scratch-environment tests, not target-Mac verification.
- All exact calculations remain deterministic. Finance stays outside model/general-agent context under G-015. Health remains locked by default.

## 3. Keep these technology decisions separate

This ADR concerns the application runtime (language, UI framework, client/core boundaries and packaging). It does not decide:
- Which local model or inference runtime Atlas uses (G-O01).
- Storage/search/encryption/key architecture (G-O02).
- Backup, restore and key recovery (G-O05).
- Secure worldwide remote access, device identity or offline sync (G-O14/G-O15).
- Native update/signing implementation details beyond the chosen application boundary (G-O12).

Do not select Ollama, llama.cpp, MLX, a model family or a database merely because an application framework supports it.

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

## 6. Preliminary recommendation

**Recommend A: Swift + SwiftUI + shared Swift packages**, subject to Claude's technical challenge and the owner's explicit acceptance.

Reason: the committed platform set is macOS+iOS only. SwiftUI offers one shared Apple-native application codebase without adding a cross-platform rendering framework. It aligns best with native macOS delivery, iOS distribution, Apple security APIs and the future iOS client. Android portability is no longer a requirement and should not drive framework selection.

**Migration strategy:** do not rewrite the existing Python system as part of this ADR or Stage 2. Keep the existing host-side Atlas Core and proven Python capabilities behind a narrow, versioned, authenticated local API while the shared SwiftUI application layer is established. Treat Python services as hidden technical workers under the single Atlas product, not as separate apps. Define contracts so the Core can be ported incrementally later if profiling, reliability or packaging evidence justifies it. The iOS client connects securely to the owner-controlled Mac Core; it does not run cloud inference.

This recommendation is not a final runtime selection until the owner accepts it. If the owner interprets one codebase as requiring all application and Core logic to use one language, rather than a shared macOS/iOS app codebase with a host-side Core, that distinction must be settled before ADR acceptance.

## 7. Required technical challenge / proof before acceptance

Claude must assess the recommendation against the actual repository and provide evidence for:

1. Shared SwiftUI/Xcode project structure for macOS and iOS, including what can genuinely be shared and what must be platform-specific.
2. A minimal spike plan (not implementation yet) proving Swift client ↔ existing local Python Core API on macOS and secure iOS client ↔ Mac Core API.
3. The native API and security boundary: authentication, device enrolment/revocation, transport, local-only inference and no public database/model ports. Detailed remote-access design remains G-O14 and is not decided here.
4. Feasibility of local inference/native library integration on the Mac host without coupling the UI framework to the model runtime.
5. Preservation/reuse strategy for Python capabilities and tests; identify any blockers to the API-boundary approach.
6. Native packaging, signing, update and rollback implications (G-O12); do not claim implementation.
7. Expected memory/footprint/startup/latency risks and a repeatable benchmark plan on the 32 GB target profile.
8. A like-for-like comparison against Flutter and Compose, identifying any factual error or material omitted cost in this ADR.

If Claude finds a material blocker, revise the recommendation rather than defend it. No code spike is authorised by this review request.

## 8. Acceptance and consequences

Owner acceptance of this ADR resolves G-O17 and satisfies only the runtime/platform decision gate. It does not authorise Stage 2 by itself.

After acceptance:
- Keep domain contracts independent of SwiftUI views and OS-specific adapters.
- Use a single shared SwiftUI app project/source tree for macOS and iOS, with narrow platform adapters.
- Keep the Mac-host Core behind a versioned API; no cloud inference.
- Require architecture tests for dependency direction and platform leakage.
- Revisit the Core language only through a separate evidence-backed ADR if necessary.

Rejected alternatives remain technically viable, but are not preferred for the current Apple-only target.

## 9. Sources

Official platform documentation consulted 2026-11-20:
- Apple, [Configuring a multiplatform app target](https://developer.apple.com/documentation/Xcode/configuring-a-multiplatform-app-target) — Apple platforms can share a target; SwiftUI projects can share substantial code.
- Apple, [SwiftUI](https://developer.apple.com/documentation/swiftui/) — declarative UI and adaptive views across Apple platforms.
- Flutter, [Supported deployment platforms](https://docs.flutter.dev/reference/supported-platforms) — macOS and iOS support.
- Flutter, [Platform channels](https://docs.flutter.dev/platform-integration/platform-channels) — native Swift/Objective-C integration.
- Flutter, [Pigeon](https://docs.flutter.dev/interop/pigeon) — generated native bindings; native interop currently preview.
- JetBrains, [Kotlin Multiplatform FAQ](https://kotlinlang.org/docs/multiplatform/faq.html) — iOS, desktop and shared Compose UI support.
- JetBrains, [Compose Multiplatform compatibility](https://kotlinlang.org/docs/multiplatform/compose-compatibility-and-versioning.html) — supported platform/version matrix.
- Tauri, [Prerequisites](https://v2.tauri.app/start/prerequisites/) — macOS/iOS development toolchain requirements.
