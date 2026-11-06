# Prasanna

Two private, offline apps live in this repository, one per branch:

| Branch | App | What it is |
|---|---|---|
| `orbit` | Finance (folder `orbit/`) | A private, offline finance and personal assistant. Start with `orbit/README.md` |
| `orbit` | Documents (folder `library/`) | The one reader and store for every file and mail; Finance, Health, Travel ask it for what is relevant. Start with `library/README.md` |
| `orbit` | Picture engine (folder `images/`) | Everything that understands a picture, in one place: EXIF, places, text, faces, CLIP, the index and every kind of search. Documents runs it. Start with `images/README.md` |
| `orbit` | Shared kit (folder `kit/`) | What every app shares: encrypted database, local model client, no-network guard, retrieval. Both Finance and Documents depend on it |

Nothing in either app talks to a cloud service while it runs.

## Atlas
`atlas/` is the one address for the private apps in this repository family (Finance for money, Documents for files, mail and pictures, more to come): `http://atlas.localhost:8000`. See `atlas/README.md`.
