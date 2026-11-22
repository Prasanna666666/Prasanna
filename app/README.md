# Atlas macOS app (SwiftUI) — builds and passes its tests on a macOS CI runner; never launched

**Status: CI-verified to build and to pass `swift test` on a GitHub-hosted macOS runner (the `macos` job); never launched, so nothing about how it looks or behaves is verified.** The first compile on the runner found and fixed three real Swift errors (the Unix socket address code, a `@State` declaration, and a `self` capture before init); a Linux container cannot compile Swift. The app has not been run: no window, Keychain access, Get Started flow or accessibility behaviour has been seen.

What it is: a Swift package with `AtlasKit` (signing, catalogue, Unix-socket HTTP client, view models) and `AtlasApp` (Get Started, conversation, progress, cancel, citations with "show the source passage", model line, coverage and notices). It speaks the same signed API 1.1 as the verified Python reference client (`core/client/atlas_client.py`) and reads the same `ux_catalogue.json` (copy of `core/client/ux_catalogue.json`; keep in sync).

## On a Mac
1. `cd app && swift build && swift test`. The tests pin the signing message to the known-answer vectors in `core/docs/CONTRACT_1_1.md`; if they pass, the Swift signing equals the Core's.
2. Start a Core (the composition root is `core/src/atlas_core/app.py`). On first run the app creates a random client id and an Ed25519 key in the Keychain (`KeyStore`) and enrols the public key as the **owner** client (`POST /v1/enrol`, unsigned, accepted once while no owner client exists, over the owner-only socket; `core/docs/ENROLMENT.md`). The app now starts its own Core with `CoreLauncher` (a child process; the one-time code goes over the child's standard input, never argv, environment, a file or a log); the Python launcher (`core/src/atlas_core/launcher.py`) does the same and is tested with a real child process, the Swift side is not. Packaging the Core into the app, and the Mac providers a real Core needs (Keychain, anchor, TCC, Mail adapter, MLX), are not built.
3. `swift run AtlasApp`. Walk the owner acceptance brief in `core/docs/STAGE3_HANDOVER.md`.

## Known gaps
Enrolment of further devices from the app, macOS permission (TCC) prompts, app packaging/signing/notarisation, settings, localisation, accessibility audit beyond the labels set here, and SSE streaming (the app polls task state every 0.3 s).
