# Plugging things in (hardware, services, accounts)

Atlas is complete without any of these. Each one connects through a fixed seam, so adding it later changes configuration, not the app. This is the whole list.

| What | Where it plugs in | What you do | What you see |
|---|---|---|---|
| A home hub, travel, work, shopping, messaging or cloud-storage service | **Connections** in the app; `connectors.json` (catalogue) and the connector profile (`CONNECTOR_PROFILE.md`) | If the service speaks the profile: open Connections, press Connect, enter its address and token. If it has its own API: add an adapter (`Adapter`: `check`, `read`, `act`) and install it under the integration's id with `ConnectorHub.install`; or add a new entry to `connectors.json` for a new kind of service | The integration with what it can read, what it can change, which changes ask you first, what happens offline; Connect, Check, Disconnect |
| Calendar, Contacts, Notes, Photos on the Mac | Settings, turn the source on | Allow the macOS prompt once | The source in Settings; its content in answers and the Library |
| Finance and Health records | `maintenance import-finance` and Settings | Import once, turn the source on | The Finance and Health areas |
| The local model | `models/` folder with the signed manifest and `manifest.pub` (G-O12) | Copy the model and the key | Answers instead of "the local model is unavailable" |
| App updates | Put the release-signing public key at `~/Library/Application Support/Atlas/release.pub` | Place the key | **Updates** in Settings: Install an update, Go back |
| Signing and notarisation | `scripts/sign_and_notarize.sh` with `DEVELOPER_ID` and `NOTARY_PROFILE` | Run it with your Apple Developer ID | A notarised app |
| The browser engine's allowed hosts | Core option for the browser workflow | Provide the hosts and the steps | Browser workflows through the Core |
| A phone or other client (G-O14) | Device pairing (built) and the remote channel (open decision) | Pair from Settings; choose the channel | Devices in Settings |

Rules that hold for everything above: the owner connects and disconnects only from the owner's own enrolled client; credentials live only in the Keychain; a service that does not answer is shown as needing attention, never as connected; disconnecting refuses everything it could do and deletes its credentials.
