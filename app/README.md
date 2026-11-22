# Atlas macOS app (SwiftUI) — UNBUILT, UNVERIFIED

**Status: written on Linux, never compiled or run.** This environment has no Swift toolchain, no macOS and no SwiftUI. Nothing in this folder is evidence of anything until it is built and run on a Mac. It exists so that the Mac step is *build, run, fix* rather than *start*.

What it is: a Swift package with `AtlasKit` (signing, catalogue, Unix-socket HTTP client, view models) and `AtlasApp` (Get Started, conversation, progress, cancel, citations with "show the source passage", model line, coverage and notices). It speaks the same signed API 1.1 as the verified Python reference client (`core/client/atlas_client.py`) and reads the same `ux_catalogue.json` (copy of `core/client/ux_catalogue.json`; keep in sync).

## On a Mac
1. `cd app && swift build && swift test`. The tests pin the signing message to the known-answer vectors in `core/docs/CONTRACT_1_1.md`; if they pass, the Swift signing equals the Core's.
2. Start a Core (the composition root is `core/src/atlas_core/app.py`). On first run the app creates a random client id and an Ed25519 key in the Keychain (`KeyStore`) and enrols the public key as the **owner** client (`POST /v1/enrol`, unsigned, accepted once while no owner client exists, over the owner-only socket; `core/docs/ENROLMENT.md`). The Python reference client does the same (`AtlasClient.enrol_self`) and is tested; the Swift side is not.
3. `swift run AtlasApp`. Walk the owner acceptance brief in `core/docs/STAGE3_HANDOVER.md`.

## Known gaps
Enrolment of further devices from the app, macOS permission (TCC) prompts, app packaging/signing/notarisation, settings, localisation, accessibility audit beyond the labels set here, and SSE streaming (the app polls task state every 0.3 s).
