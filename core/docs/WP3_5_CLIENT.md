# WP3.5 — Minimal experience: reference client, UX catalogue, end-to-end path

Status: implemented and tested on Linux CI with synthetic data. **The SwiftUI macOS app is not built here** (no Swift, Xcode or Mac in this environment); everything below that needs a Mac is listed as pending and is not claimed.

## What exists
| Piece | Where | What it fixes for the app |
|---|---|---|
| Reference client | `client/atlas_client.py` | The conversation path over the real signed Unix-socket contract: discover, ask, follow events (resumes), cancel, answer. Signs the applied version (API 1.1), refuses a response whose version echo is absent or different, and turns every failure into catalogue words. |
| UX catalogue | `client/ux_catalogue.json` | Every sentence for every task state, progress step, error, terminal reason, verification status, limitation, coverage state/pending/failed reason, language status, not-searched reason, model role, locator kind. Plain words; no codes, paths, traces or source content. |
| Completeness test | `tests/test_client.py::test_every_value_of_every_closed_vocabulary_has_a_message` | Fails if the 1.1 contract gains a value the catalogue lacks. |
| End-to-end tests | `tests/test_client.py` | Real Core (document index, policy gate, gateway with manifest-verified stub model, task service, API 1.1, Unix socket) driven only through the client. |

## Behaviour the tests pin (maps to PRD experience requirements)
- Progress is shown per step; the task can be cancelled while queued; a cancelled or failed task ends with a plain message.
- An answer shows: the text, how far to trust it (catalogue wording of the verification status), **which local model wrote it** ("Answered on this Mac by … Nothing left your computer."), what was searched (coverage line), every limitation as a sentence, what was not searched and why, and each citation as "Document, paragraph 0" with its exact quote. The evidence reference stays inside the view model for the app's "show the source passage" action and is never displayed.
- Unproven figures, a wrong quote, an injected instruction or a missing source are shown as *not confirmed*, never as checked.
- No model, no server, a wrong key, an unknown task, a missing version echo and a revoked source each give a catalogue message; none shows a stack trace, path or raw JSON.
- English, Dutch, Russian and Hindi questions round-trip through the whole path (UTF-8).
- A 1.0 client works unchanged against the same Core.

## Not done / Mac-pending (never to be claimed from Linux)
1. The SwiftUI app: **builds, passes its tests and is launched (Core start and stop) in hosted macOS CI; no person has walked through its UI** (`../../app/`, with signing known-answer tests that must pass on a Mac first; `tests/test_swift_app_sources.py` keeps its catalogue and vectors in sync with the verified code). Still to do: launch it and walk it, window, conversation view, progress, cancel, citation inspector, model line, accessibility (VoiceOver, keyboard, Dynamic Type), localisation of the catalogue (NL and others).
2. First-run **Get Started** consent (one screen) and macOS permission prompts (TCC): triggering, denial paths, and the `os_access_missing` experience.
3. Client private key in the Keychain, enrolment of the owner client, and macOS peer-credential check (`LOCAL_PEERCRED`) on the socket.
4. Source inspection: served as `GET /v1/tasks/{task_id}/citations/{index}` (API 1.1 `PassageText`, additive) and called by `AtlasClient.passage` (`tests/test_client.py::test_the_cited_passage_can_be_opened_exactly_and_stops_opening_when_the_source_changes_or_is_revoked`); the app's passage view is not built.
5. Real model behaviour, speed and memory (MLX): see `docs/genesis/INTELLIGENCE_AND_PERFORMANCE.md`; nothing in this package measures it.
6. The consent and index-status routes are served (`tests/test_consent_api.py`) and the reference client calls them (`consent`, `enable`, `withdraw`, `index_status`); the Get Started *screen* and the owner-client enrolment on a Mac are not built.
