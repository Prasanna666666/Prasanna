# Atlas

One private, offline app for everything personal: **Documents, Mails, Pictures, Travel and Finance** (Health next), with one chat and one Update button. Nothing in it talks to a cloud service while it runs; everything stays on this computer, encrypted.

```
./up.sh      # start everything, then open http://atlas.localhost:8000 and press Update
./down.sh    # stop (nothing is deleted)
```

**Start by itself at every login** (once): `./scripts/install-autostart.sh`. It starts Docker, Ollama and Atlas when you log in, and puts an **Atlas** app in `~/Applications` that opens http://atlas.localhost:8000 (drag it to the Dock). Undo with `./scripts/uninstall-autostart.sh`.

Needs Docker Desktop and Ollama on the Mac. Without Apple Mail: `ATLAS_NO_MAIL=1 ./up.sh`.

## How it is built (for developers)
| Folder | What it is |
|---|---|
| `atlas/` | The front door: one address, one menu, one chat and one Update button over everything below. See `atlas/README.md` |
| `library/` | Documents, Mails, Pictures and Travel: the one reader and store for every file, mail and picture. See `library/README.md` |
| `finance/` | The money part: income, expenses, savings, investments, net worth. See `finance/README.md` |
| `images/` | Everything that understands a picture, in one place; `library/` runs it. See `images/README.md` |
| `kit/` | What every part shares: encrypted database, local model client, no-network guard, retrieval |

Decisions and architecture: `docs/decisions.md`, `docs/architecture.md`. Work happens on the `orbit` branch.
