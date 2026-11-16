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
