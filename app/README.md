# Atlas macOS app (SwiftUI) — UNBUILT, UNVERIFIED

**Status: written on Linux, never compiled or run.** This environment has no Swift toolchain, no macOS and no SwiftUI. Nothing in this folder is evidence of anything until it is built and run on a Mac. It exists so that the Mac step is *build, run, fix* rather than *start*.

What it is: a Swift package with `AtlasKit` (signing, catalogue, Unix-socket HTTP client, view models) and `AtlasApp` (Get Started, conversation, progress, cancel, citations with "show the source passage", model line, coverage and notices). It speaks the same signed API 1.1 as the verified Python reference client (`core/client/atlas_client.py`) and reads the same `ux_catalogue.json` (copy of `core/client/ux_catalogue.json`; keep in sync).

## On a Mac
1. `cd app && swift build && swift test`. The tests pin the signing message to the known-answer vectors in `core/docs/CONTRACT_1_1.md`; if they pass, the Swift signing equals the Core's.
2. Start a Core (the composition root is `core/src/atlas_core/app.py`) with the owner client's public key enrolled as an **owner** client (`ClientRegistry.register(id, public_key, owner=True)`); the app creates its Ed25519 key in the Keychain on first run (`KeyStore`). The enrolment hand-off is not built.
3. `swift run AtlasApp`. Walk the owner acceptance brief in `core/docs/STAGE3_HANDOVER.md`.

## Known gaps
Key enrolment UI, macOS permission (TCC) prompts, app packaging/signing/notarisation, settings, localisation, accessibility audit beyond the labels set here, and SSE streaming (the app polls task state every 0.3 s).
