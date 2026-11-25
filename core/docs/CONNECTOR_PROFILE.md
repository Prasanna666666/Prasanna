# The Atlas connector profile

This profile applies to an existing integration ID in Atlas's fixed `connectors.json` catalogue. A compatible service/bridge can be configured for that supported entry from **Connections**; adding a new catalogue entry or a vendor-specific adapter requires a code/package change. The profile uses HTTP with JSON.

| Call | Purpose | Success | Atlas shows |
|---|---|---|---|
| `GET /atlas/v1/ping` | Is this the right service, and does it accept the token? | `200` | Connected. `401` or `403`: "did not accept the access token" (nothing is stored). Anything else or no answer: "did not answer" |
| `GET /atlas/v1/read/{scope}` | Read one scope the catalogue lists (for example `device_state`) | `200` and a JSON object | The data, marked with when it was fetched |
| `POST /atlas/v1/act/{action}` | Do one change the catalogue lists (for example `control_device`) | `200` and `{"done": true}` | Done. Any other answer is reported as **not done**; Atlas never assumes a command worked |

Rules:
- Every request carries `Authorization: Bearer <token>` and `Content-Type: application/json`.
- A reversible action must return `"previous"`: the state it replaced (for example `{"light": "off"}`). The Core now refuses to report successful undo if credentials are unavailable, `previous` is missing/not an object, or the provider does not confirm the compensating action. Regression coverage includes missing/malformed `previous` and disconnect-before-undo. This validates the failure boundary, not every vendor's compensation semantics.
- Prefer `https`. Plain `http` is accepted by the current implementation for loopback, private-range, `.local`, shared VPN address space and `.ts.net` names. The `.ts.net` shortcut is not DNS-resolved/pinned before a bearer token is sent and is tracked by ATLAS-CONN-083; ambient proxy inheritance is tracked by ATLAS-CONN-084. Do not use plain HTTP for `.ts.net` until both risks are closed. Redirects are never followed.
- Replies are limited to 1 MB; Atlas waits 15 seconds.
- The token is stored in the Mac's Keychain and is never shown, logged or put in an audit entry again.

What needs your approval is not decided by the service. It comes from the catalogue entry's effect for each action, which is the closed list in PRD 4.4: sending or publishing outside the Mac, spending money, an irreversible delete or overwrite, physical access or safety systems. Other actions do not prompt unless they fall within the exhaustive PRD §4.4 approval categories. Prompt-free does not itself prove that an action has a working undo; the connector's `previous` state and undo result must be validated.
