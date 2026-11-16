# Architecture: layers

Everything reusable lives in the common layer. An app holds only what is specific to it.

| Layer | Package | Holds | May import |
|---|---|---|---|
| 1. Common | `kit` | database, encryption, signing, local HTTP, the model client, extraction and verification of amounts and dates, search, **concepts** (what a kind of file means to an app), audit, modules | nothing |
| 2. Documents | `library` | reads every file and mail, sorts (what it is, which apps), groups (what belongs together), the plain names of kinds | `kit`, `images` |
| 3. Apps | `finance`, `atlas` (the shell), `images` (photos) | their own pages, their own concepts, their own rules | `kit` |

Apps never import each other: they talk over HTTP (`/api/documents?app=…`). `kit/tests/test_architecture.py` enforces this and fails on a fixed kind word (`kind = 'invoice'`) in any code or page.

## What each layer decides

- **The model describes** each file freely (kind, which declared apps it is about, the distinctive things in it, details checked against the text). No list of kinds is in code.
- **Plain names** (Documents layer): the model merges every wording and language of a kind into a few short names.
- **Concepts** (`kit.concepts`): an app declares the concepts it needs in its own `concepts.json` (a name and a plain description). The model decides once, per kind, which concept it means; the answer is stored; code and queries ask for the concept (`concepts.clause("invoice")`), never for a word.
- **Grouping** links files that share a rare thing (a code, an amount, something the model found in them), and the model confirms every pair with a quote.
- **Apps show** what is marked for them, plus what grouping put with it. Nothing by date or word coincidence.

## Adding an app

1. Declare it in `library/src/library/apps.json` (name, what it is about, optional words).
2. If it needs to tell kinds of file apart, add its `concepts.json` and use `kit.concepts.Concepts`.
3. Ask the Documents layer for its files over HTTP. Do not read files yourself and do not re-describe them.

## Words live in data, not in code

What a spending category or a note tag is known by (merchant names, words) is in `finance/src/finance/categories.json` and `tags.json`, with the list of routine categories. Teaching Finance a new merchant is an edit of that file, not of code. The person's own corrections come before it and the local model decides what it does not cover. Small helpers every layer needs (`squash`, `clean`, `day`) are in `kit.text`; the request checks, error boundary and file serving of every service are in `kit.http.ModuleHandler`.

## How the Documents service is divided

`store` (what is kept), `judging` (what the model makes of each file), `healthdata` and `tripdocs` (views over what was read), `casebook` (grouping), `reading` (an Update), `scanstatus` (where it stands), `appstate` (server state), `web` (routes only). The reader is `parser` (entry point) over `extraction` (one file), `batch` (many files), `mailread` and `bulkmail` (mail), `control` (pause and stop) and `rounds`. Finance is divided the same way: `money` (the ledger and its tools), `statement_import` (reading statements) and `reports`.

## Checks that run

`ruff` and `mypy` in every package, `pytest` (Finance also needs 85% coverage), prettier on the web code, `kit/tests/test_architecture.py` (layers, no kind words, no copied function, no function over 50 lines), `kit/tests/test_design.py` (one design, readable colours, visible focus). By hand against running apps: `node scripts/check-pages.js` (every page in a real browser, WCAG 2.1 AA with axe-core) and `python scripts/scale-check.py 300000` (the status counts and lists on 300,000 documents take under 0.3 s).

## Limits the tools enforce

At most seven arguments per function (related ones travel together as a record: `Hooks`, `Where`, `Narrow`, `Budget`, `ClipLimits`), no bare numbers in comparisons (a named constant says what the number means; shared units are in `kit.units`), at most 50 lines per function, 15 branches, complexity 15. These are in each package's `pyproject.toml` and in `kit/tests/test_architecture.py`; none is switched off.
