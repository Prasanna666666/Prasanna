# Owner acceptance and final-stage checklist

Everything the developer can build and test without hardware, accounts or a real model is built and tested (Linux CI = L, hosted macOS runner = R). This list holds the rest. None of it is outstanding developer work: each item needs a person, an account, a device or the real model, and is sequenced to the final stage by owner direction. Each stays release-blocking until done.

## A. Needs an Apple Developer ID
1. Run `scripts/sign_and_notarize.sh` with the real identity (script and dry run are tested, `test_signing_script.py`).
2. Staple and check Gatekeeper on a clean Mac.

## B. Needs the real model on suitable hardware (about 14 GB)
3. Injection resistance of the selected model (S3-4) and accept a threshold.
4. Latency, memory, quality and thermal numbers (S3-12); accept thresholds.
5. Agent-versus-single-model benchmark (Stage 6).
6. Model isolation under the least-privilege macOS profile.

## C. Needs an owner's Mac (a person at a screen)
7. First launch: Get Started consent, the OS permission prompts as a person sees them.
8. Walk each screen in `UI_IMPLEMENTATION_MAP.md`: VoiceOver, keyboard, Dynamic Type, reduced motion, light and dark, screenshots and visual acceptance (UI_UX_SPECIFICATION.md).
9. Reboot with FileVault on, locked Keychain, LaunchAgent install (files and exit paths are tested).
10. Power-loss behaviour; update-and-restart on a real install.
11. Real Apple Mail store run; real Calendar, Contacts, Notes access (adapters need real OS frameworks and permissions).
12. Restore drill with a real backup on the owner's disk.

## D. Product scope that needs an owner decision or account first (not started by design)
13. G-O14: the remote channel (relay or VPN) and the iOS client. The Core side (pairing, signed requests, sync, revocation, no public ports) is built and tested.
14. G-O02 and G-O05, and the Stage 6 connector and voice scope (home, travel, shopping, work connectors need accounts and devices; voice needs the client).
15. Photos adapter, Playwright browser engine, isolated automation workers and real specialist agents. The policy layer, stubs and fakes are built and tested; the real engines need a machine that can run them.
16. Update channel: where signed releases are published (needs hosting and your release-signing key; the signed install and rollback from a chosen folder, and the Settings screen, are built and tested). Put the public key at `~/Library/Application Support/Atlas/release.pub` and the screen appears.
17. Attachment processing (G-O18, separate package).

## E. For the architect
18. Docs wording listed in `PROGRAMME_AUDIT.md` ("Discrepancies") and the PR description.
19. Review of this branch as a whole; decision on PR state. The PR stays draft.
