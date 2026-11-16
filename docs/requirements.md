# Requirements

Status as of branch `atlas` at the head of this pull request. Each requirement has an ID so that review comments can point at it (`R-F3`, `R-Q2`). "Verified by" names the test or check that proves it; "Not verified" says what only the owner's Mac can show.

## Purpose

One private personal app for one owner, running on their own Mac. It reads their files, mail, pictures, travel documents and bank statements, and answers questions about them with a local AI model. Nothing is sent to a cloud service while it runs.

## Users and context

- One owner, on one Mac (Apple silicon, 8–24 GB memory), using Docker Desktop and Ollama on the host.
- Reviewers (friends) read the code, the documents and the screenshots and comment on the pull request. They have read access only.

## Functional requirements

| ID | Requirement | Verified by |
|---|---|---|
| R-F1 | **Documents**: read files and Apple Mail, extract text (OCR for scans), keep it whole, sort each file (what it is, which app it is for, its facts), group related files. | `library/tests` (217), `test_whole_read.py` |
| R-F2 | **Finance**: import bank statements, prove every month ties to the cent, categorise payments, show income, spending, savings, investments, net worth, budgets, goals. | `finance/tests` (619) |
| R-F3 | **Health**: lab values and medicines exactly as printed, no interpretation; say when a document was read only in part. | `kit/tests/test_extract_whole_document.py`, `library/tests/test_health_travel.py` |
| R-F4 | **Travel**: trips from tickets and bookings with the dates the documents print, booked totals, calendar file. | `library/tests/test_health_travel.py` |
| R-F5 | **Pictures**: index pictures, places, people, quality; changes to pictures only after the owner confirms in a window. | `images/tests` (96), `library/tests` |
| R-F6 | **Atlas**: one address, one menu, one search box, one chat, one Update button over all apps. Atlas holds no data. | `atlas/tests` (92) |
| R-F7 | **Assistant**: answers about the owner's data by calling tools of the apps; every figure in an answer must have come from a tool. | `atlas/tests/test_assistant.py` |
| R-F8 | **Changes to money records** by the assistant are only prepared; the owner's own next message ("yes") makes them, once. | `finance/tests/test_assistant_changes.py`, `atlas/tests/test_assistant_safety.py` |
| R-F9 | **Update** is one button / one command (`./update.sh`); starting is `./up.sh`, stopping `./down.sh`; autostart at login. | scripts; not run in CI |

## Quality requirements

| ID | Requirement | Verified by |
|---|---|---|
| R-Q1 | **Numbers exactly right.** Money is whole minor units (cents); amounts are read as the decimal written and rounded once. | `finance/tests/test_money_exact.py` |
| R-Q2 | **The model does no arithmetic or logic.** Code computes and verifies; the model reads, labels and quotes. Amounts, dates, parties, entities are checked against the whole source text. | `kit/tests/test_extract*.py` |
| R-Q3 | **Private and offline.** No outbound network from the apps (guard in `kit`); the model server must be this computer or its private network. | `finance/tests/test_privacy.py`, `atlas/tests/test_assistant_safety.py` |
| R-Q4 | **Encrypted at rest** (SQLCipher); refuse to run unencrypted when encryption is required; converting a plain database leaves no plain copy unless asked. | `kit/tests/test_db_safety.py`, `finance/tests/test_secure_by_default.py` |
| R-Q5 | **No limits on what is kept.** Mail is kept whole; every limit lives in `limits.json` with effectively unlimited defaults; a cut is recorded and the file is read again when the limit changes. | `library/tests/test_limits_config.py` |
| R-Q6 | **Nothing is silently lost or half-done.** Incomplete reads say what was not read; migrations are all-or-nothing and can be retried. | `kit/tests/test_db_safety.py`, `test_extract_whole_document.py` |
| R-Q7 | **Honest and plain UI.** No code or error text on screen; one-line plain answers; WCAG 2.1 AA in both themes; keyboard focus visible. | `kit/tests/test_design.py`, `scripts/check-pages.js` (axe) |
| R-Q8 | **No hardcoded words.** Categories, kinds, thresholds and limits are data or decided by the model. (Known exception: `kit/consent.py` word lists for the owner's own yes/delete words — see O-8.) | `kit/tests/test_architecture.py` (kind words) |
| R-Q9 | **Maintainable.** Layers enforced by test; functions ≤ 50 lines; ruff limits (args ≤ 7, branches ≤ 15, complexity ≤ 15, no magic values); mypy; prettier. | CI |
| R-Q10 | **The AI never edits its own source.** | design (read-only tools); not separately tested |

## Constraints and rules from the owner

No hardcoding; fixes must work in all scenarios; never claim fixed or verified without proof; the assistant never sees the owner's real finance data or private output; do not make unrequested changes; one-line plain answers; no printed code or error text in the UI.

## Out of scope

Cloud AI; multi-user access; mobile native apps; currencies with other than two decimals (stored in hundredths: see O-1 in `defects.md`).

## Platform

Python ≥ 3.11 (Docker images use 3.12), SQLite/SQLCipher, Ollama (`ministral-3:3b` by default; `ATLAS_MODEL` to change), Docker Desktop on macOS; Apple Vision for OCR with Tesseract as fallback.
