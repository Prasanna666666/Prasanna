# Owner acceptance and final-stage checklist

This checklist records owner-only and final-stage acceptance actions; it is **not** a statement that PR #8 has no outstanding developer work or that independent review is complete. For branch-wide rollback and recovery boundaries, see `BRANCH_ROLLBACK_AND_RECOVERY.md`; no complete owner-Mac recovery drill has been accepted. The 2026-11-24 path counts below are historical only. For the latest PR head, review-thread counts and current developer-review status, use `docs/genesis/REVIEW_COVERAGE_RECONCILIATION.md`. PR #8 remains open/draft/unmerged; Stage 3 is not accepted. Developer fixes and re-review may still be outstanding; see `docs/genesis/DEFECT_REGISTER.md` and `core/docs/STAGE3_ACCEPTANCE.md`. The items below are owner/final-stage gates, not a substitute for the complete developer and architect acceptance process.

## A. Needs an Apple Developer ID
1. Run `scripts/sign_and_notarize.sh` with the real identity (script and dry run are tested, `test_signing_script.py`).
2. Staple and check Gatekeeper on a clean Mac.

## B. Needs the real model on suitable hardware (about 14 GB)
3. Injection resistance of the selected model (S3-4) and accept a threshold.
4. Latency, memory, quality and thermal numbers (S3-12); accept thresholds.
5. Agent-versus-single-model benchmark (Stage 6).
6. **Developer/architect gate, not an owner action:** the current macOS model profile is allow-by-default with explicit denials and is not least privilege (`MODEL_RUNTIME.md`). It requires developer hardening or explicit architect/owner residual-risk acceptance before any release/public-research enablement.

## C. Needs an owner's Mac (a person at a screen)
7. First launch: Get Started consent, the OS permission prompts as a person sees them.
8. Walk each screen in `UI_IMPLEMENTATION_MAP.md`: VoiceOver, keyboard, Dynamic Type, reduced motion, light and dark, screenshots and visual acceptance (UI_UX_SPECIFICATION.md).
9. **Owner-Mac lifecycle check:** reboot with FileVault on and confirm Keychain lock/sign-in behaviour. The app currently starts/stops/reaps its Core child through `CoreLauncher`; `launchagent.py` only generates plist bytes and is not installed/loaded. Do not attempt a LaunchAgent install as an acceptance step.
10. Power-loss behaviour; update-and-restart on a real install.
11. Real Apple Mail store run, and your own Calendar, Contacts, Notes and Photos: the Calendar/Contacts/Notes/Photos adapters are exercised against the real macOS frameworks in hosted CI (including denied/no-permission paths); the Mail `.emlx` reader is exercised only on synthetic fixtures. No real Apple Mail store or owner data has been read. Only you can grant the real permissions and verify your own data.
12. Restore drill with a real backup on the owner's disk.

## D. Product scope that needs an owner decision or account first (not started by design)
13. G-O14: remote phone use is **not ready for owner acceptance yet**. Pairing, relay and iOS offline/sync code exist, but open developer/security findings remain: ATLAS-RELAY-063, ATLAS-IOS-051/053/061, ATLAS-DEV-041, ATLAS-SEC-087 and ATLAS-PHONE-072 (in-flight read can repopulate cache after Unpair). These require fixes, regression tests and review before you choose a VPN/channel, pair your phone or treat remote access as complete. After those gates, the owner chooses the private/VPN channel and signs the iOS app with their Apple team.
14. G-O02 and G-O05, and the Stage 6 connector and voice scope (home, travel, shopping, work connectors need accounts and devices; voice needs the client).
15. Web reading is built but OFF in the production host until the browser worker runs under OS-enforced confinement (architect review 6020108624, P1); interactions (click, form entry) do not exist and each would need a typed Action Gateway action with approval, which is the architect's design to give (the orchestrator is wired and serves the review with code agents and one model-backed highlights agent; only the agent-versus-single-model benchmark needs the real model). The policy layer, stubs and fakes are built and tested; the real engines need a machine that can run them.
16. Update channel: where signed releases are published (needs hosting and your release-signing key; the signed install and rollback from a chosen folder, and the Settings screen, are built and tested). Put the public key at `~/Library/Application Support/Atlas/release.pub` and the screen appears.
17. Attachment processing (G-O18, separate package).

## D2. Owner setup paths (only after their developer/security gates; see `PLUG_IN_GUIDE.md`)
An existing supported catalogue integration may be configured from Connections with its address and token. A new vendor adapter/catalogue entry requires developer work. The Health ingestion path is not implemented. Placing the release-signing key, installing a signed model and running the signing script are owner setup tasks only after the corresponding build, signing and acceptance requirements are met.

## E0. Network and authority changes for the architect to confirm
- `relay.py` is a fifth module allowed to open a listening socket (named in `test_only_the_egress_gateway_and_the_local_transport_can_open_a_network_connection`). It is off by default, refuses any address that is not private or VPN before opening a socket, forwards only `/v1/` and never `/v1/enrol`, and holds no key. It is the G-O14 channel; the choice of channel remains yours and the architect's.
- `web.py` is wired but OFF in the production host (see item 15). When it is on, it opens pages through the isolated browser worker for hosts the owner allowed; the worker can reach only that host. The worker connects to the public address the Core checked (no second DNS lookup, TLS verified against the host's name), so DNS rebinding is closed for reading pages. `browser_engine.py` is therefore a sixth module that opens a connection; the architecture test names it and says why.
- A paired device may read the owner's own Calendar, Contacts, Notes and Travel (see below).
- A paired device (an ordinary member client) may now READ the owner's own Calendar, Contacts, Notes and Travel through `GET /v1/records/{domain}`; before, only the owner client could. Finance and Health are not in that store and stay unreadable by any device. It is the intended phone use and is covered by `test_operations_api.py`; revocation ends it at the next request.

## E. For the architect
18a. `connector_transport.py` is a fourth module allowed to open network connections (owner-addressed connector traffic; `test_only_the_egress_gateway_and_the_local_transport_can_open_a_network_connection` now names it). This widens a rule you own, so it needs your decision.
18. Docs wording listed in `PROGRAMME_AUDIT.md` ("Discrepancies") and the PR description.
19. Review of this branch as a whole; decision on PR state. The PR stays draft.
