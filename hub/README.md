# Home

One address, one menu, one search box and one chat button for every private app. **Orbit** (money) and **Lumo** (photos) stay two separate
sub-systems, each with its own database, container and rules. Home is only the front door: it holds no data and never reads yours.

```
 http://home.localhost:8000          the one address
        |
        +-- Home (menu, search, chat button, theme)
        +-- finance.home.localhost  -> Orbit   (its own container and database)
        +-- photos.home.localhost   -> Lumo    (its own container and index)
        +-- health.home.localhost   -> whatever comes next
```

`*.localhost` always means this computer, so there is nothing to install or configure. Each app is shown inside the Home page under its own
name, which keeps the apps' own addresses and security rules exactly as they are.

## Start it

```bash
cd hub && ./up.sh        # then open http://home.localhost:8000
./down.sh                # stop Home only; the apps keep running and keep their data
```

Start the apps as before (`orbit/scripts/up.sh`, Lumo's `scripts/up.sh`). Home shows each one as running or not; an app that is down
shows a plain "not running" page and never blocks the others.

## What the shared page gives you
- **One menu** with every app and its pages, a green dot for "running", and each app tints the page with its own colours.
- **One search** (`Ctrl/⌘ K`, or `/`): it asks every app at once (payments and files in Orbit, places, people and trips in Lumo), lists the pages, and can
  hand your question to an app's assistant.
- **One chat button** (`Ctrl/⌘ J`): it opens the assistant of the app you are looking at.
- **One theme**: dark, light or automatic for everything.

## Add an app (health, documents, anything)
1. Build the app so it follows the contract below.
2. Drop a file in `modules.d/`, for example `modules.d/health.json`:

```json
{
  "id": "health",
  "name": "Health",
  "app": "Vital",
  "tagline": "Appointments, prescriptions and measurements",
  "icon": "M12 21s-7-4.4-7-10a4 4 0 0 1 7-2.6A4 4 0 0 1 19 11c0 5.6-7 10-7 10Z",
  "accent": ["#f43f5e", "#f59e0b"],
  "upstream": "http://host.docker.internal:8601",
  "health": "/api/health",
  "search": "/api/search",
  "home": "#/today",
  "pages": [{"id": "today", "label": "Today", "icon": "M12 8v4l3 2"}]
}
```

3. `./up.sh`. It appears in the menu, the overview, the search and the chat button. Nothing else changes.

| Field | Meaning |
|---|---|
| `id` | lowercase letters, digits, dashes; becomes `<id>.home.localhost` |
| `upstream` | `http://` address on this computer or its private network (anything else is refused at start-up) |
| `health` | a path that answers 200 when the app is up (default `/api/health`) |
| `search` | optional path for the search box (see the contract); leave out if the app has no search |
| `home` | the page the app opens on (`#/route`) |
| `pages` | menu entries; each `id` is a route of the app (`#/<id>`) |
| `auth` | only if the app's API needs a token the app prints into its own page: `{"meta": "<meta name>", "header": "<header>"}` |
| `host` | rarely needed: the `Host` the app expects (default `127.0.0.1:<port>`) |

Point a module somewhere else on one machine without editing the file: `HUB_UPSTREAM_HEALTH=http://127.0.0.1:9000`.

## The contract an app follows
- `GET /api/health` answers 200 when the app is up.
- `GET /api/search?q=text` (optional) answers `{"results": [{"title", "subtitle", "kind", "link"}]}`. `link` is a route inside the app, such as `#/library?place=Lisbon`.
- The app keeps its own routes as `#/<page>` (a hash), so Home can send you to a page and follow where you go.
- When it is shown inside Home (`window.self !== window.top`) the app hides its own menu, top bar and chat button, and listens for messages from Home:
  `{hub: 1, type: "navigate", hash}`, `"theme", mode`, `"toggle-chat"` and `"ask", text`. It tells Home about itself with
  `{hub: 1, type: "route", hash}`, `"palette"` (the user pressed `⌘K`), `"chat", open` and `"ready"`.
- It needs no change to its security: Home permits only its own page to frame the app, checks `Host` and `Origin` itself, and
  presents each app with the local name it already accepts.

Orbit (`orbit/src/orbit/static/app.js`, `web.py`) and Lumo (`src/aperture/web`) are the two reference implementations.

## What it will not do
- Merge the apps' data or databases, or read them. The only things Home asks an app for are its health and the results of a search you typed.
- Reach the internet: it connects only to the addresses in `modules.d`, and refuses any that are not on this computer or its private network.
- Rewrite the apps' pages. They are passed through unchanged.

## Developing
`pip install -e ".[dev]"`, then `pytest`, `ruff check .`, `mypy src`. The code is the Python standard library only; the page is plain
JavaScript with `eslint` and `prettier`. Tests run Home against real fake apps over real sockets (`tests/fake_app.py`).

Untested: building and running the Home container on a real Mac (written without a Docker engine; the code itself is tested natively), and
Safari's handling of `*.localhost` (Chrome and Firefox treat every `*.localhost` as this computer).
