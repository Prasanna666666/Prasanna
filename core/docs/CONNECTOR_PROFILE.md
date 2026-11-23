# The Atlas connector profile

A service, bridge or device hub that implements these three calls can be connected from **Connections** in the app with no code change in Atlas. Everything below is plain HTTP with JSON.

| Call | Purpose | Success | Atlas shows |
|---|---|---|---|
| `GET /atlas/v1/ping` | Is this the right service, and does it accept the token? | `200` | Connected. `401` or `403`: "did not accept the access token" (nothing is stored). Anything else or no answer: "did not answer" |
| `GET /atlas/v1/read/{scope}` | Read one scope the catalogue lists (for example `device_state`) | `200` and a JSON object | The data, marked with when it was fetched |
| `POST /atlas/v1/act/{action}` | Do one change the catalogue lists (for example `control_device`) | `200` and `{"done": true}` | Done. Any other answer is reported as **not done**; Atlas never assumes a command worked |

Rules:
- Every request carries `Authorization: Bearer <token>` and `Content-Type: application/json`.
- A reversible action must return `"previous"`: the state it replaced (for example `{"light": "off"}`). Atlas sends that back as the action's undo.
- Use `https`. Plain `http` is accepted only for loopback, private-range and `.local` addresses (your home network). Redirects are never followed.
- Replies are limited to 1 MB; Atlas waits 15 seconds.
- The token is stored in the Mac's Keychain and is never shown, logged or put in an audit entry again.

What needs your approval is not decided by the service. It comes from the catalogue entry's effect for each action, which is the closed list in PRD 4.4: sending or publishing outside the Mac, spending money, an irreversible delete or overwrite, physical access or safety systems. Everything else is prompt-free and undoable.
