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
| Voice | Nothing to plug in | Allow the microphone and speech recognition once, the first time you press the microphone button | A microphone button in the composer; speech stays on the Mac |
| Web reading | Off until the browser worker runs under OS confinement; then the Web screen, and the packaged app carries the browser when built with `ATLAS_BUNDLE_BROWSER=1` | Allow the sites you want; read a page | Page text marked untrusted, with its source and time |
| The iPhone | The iPhone app (`ios/`, built with `xcodegen`) and the pairing invite; the remote channel is your choice (G-O14): save a private or VPN address in the Mac's Settings (for example your Tailscale address and a port) | On the Mac: Settings, enter the address your phone will use, Show pairing code. On the phone: scan or paste it | The phone's Ask and Areas; Devices in the Mac's Settings, where you can remove it |

Rules that hold for everything above: the owner connects and disconnects only from the owner's own enrolled client; credentials live only in the Keychain; a service that does not answer is shown as needing attention, never as connected; disconnecting refuses everything it could do and deletes its credentials.
