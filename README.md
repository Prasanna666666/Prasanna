# Prasanna

Two private, offline apps live in this repository, one per branch:

| Branch | App | What it is |
|---|---|---|
| `orbit` | Finance (folder `orbit/`) | A private, offline finance and personal assistant. Start with `orbit/README.md` |
| `orbit` | Documents (folder `library/`) | The one reader and store for every file and mail; Finance, Health, Travel ask it for what is relevant. Start with `library/README.md` |
| `orbit` | Photos (folder `photos/`), picture engine (folder `images/`) | The Photos app, and the picture engine every app shares. Start with `images/README.md` and `photos/README.md` |
| `orbit` | Shared kit (folder `kit/`) | What every app shares: encrypted database, local model client, no-network guard, retrieval. Both Finance and Documents depend on it |

Nothing in either app talks to a cloud service while it runs.

## Atlas
`atlas/` is the one address for the private apps in this repository family (Finance for money, Photos for photos, more to come): `http://atlas.localhost:8000`. See `atlas/README.md`.
