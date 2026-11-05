# Standing decisions (from the owner)

Every change is checked against this list before it is called done. It records what the owner has already said, so it is never asked twice.
If something here is wrong, the owner says so once and it is changed here.

## The product
- One personal platform called **Atlas**, one address (`http://atlas.localhost:8000`), one look. Today it holds **Finance** and **Photos**; **health, travel, documents and more** are coming. No codenames on screen (not Orbit, not Lumo, not Aperture).
- Two (or more) sub-systems behind it. Each keeps its own data, rules and tools. Modules never read each other's database; cross-module requests go through the platform.
- **One chatbot for everything**, a general assistant the owner can simply talk to, which can also find information, browse, filter and find what things have in common, and give pictures or documents **only when asked**. No per-app chat buttons.
- **One button to read everything new** (documents, pictures, anything). Each kind of data is read in the way that suits it: photos get the extremely detailed indexing and stay on the external drive; PDFs and other documents keep their own reading and live on the Mac.
- **One document processor** in the end: whatever arrives goes through one intake and is handed to the right module, which verifies it.
- **One AI model**, one address, for input and output. Cross-queries must work ("expenses, pictures, health reports and tickets for my India trip 2026").

## How much AI, and where
- **AI is for understanding, routing, semantic search and explanation. The model decides what a message means, which part it is about and what to show. Do not decide that with word lists or regular expressions** (they are only a fallback when the model is down).
- **Code, SQL and specialised tools do the actual work**: every figure, filter, date and total; EXIF, CLIP, faces and OCR for photos.
- **Agents and RAG wherever they are the right tool** (open questions, several steps, documents and notes). Retrieval only for unstructured text, never for the ledger.
- **Simple, recognised requests bypass the AI for speed**, and still pass the same answer check. Recognition must be strict: code answers only when every word of the question is accounted for; anything with a condition it does not apply goes to the model, never to a wrong answer.
- Understanding runs on measured evidence: `python -m atlas.evaluate` scores the model by difficulty level and times each path; run it on the owner's Mac after any change to prompts or models.
- The AI never modifies or deletes source data. Deletes need the owner's own words. Original files stay read-only.
- **Everything offline.** The apps never connect to the internet or a mail server. The only online steps are ones the owner runs outside the apps (downloading the model once, the exchange-rate file, building the Docker images, and Apple Mail's own syncing). Email is read from local files: Apple Mail export, `.mbox` or `.emlx`; there is no live mail fetch unless the owner decides otherwise.
- **Mail is read by the same Update button** (Apple Mail's folder, read-only, in the sealed reader), and **what is found in mail and documents feeds the calculations** (bills due, invoice-against-bank, tax, insurance, trips), not only search. A cheap gate picks what is worth the model's time; code verifies every amount and date.
- Never connect to the cloud. Everything runs on the owner's machine. (The old optional cloud reader in Photos has been removed entirely.)

## Numbers and honesty
- **Numbers must be exactly right.** Business-critical. No excuses. A figure that cannot be proven is not shown as fact; say plainly what could not be proven.
- Do not hard-code bank formats: the model infers the layout, code reads the figures, balances prove them. A file that fails its proof is left out and flagged.
- No CSV files made for the owner. No manual add or edit for event grouping. Original currency by default.
- No "Proven" badge; make sure it is right instead.
- Reports say what was verified and what was not, with no overclaiming. Nothing has been run on the owner's real data or Mac unless stated.
- The assistant (Claude) never accesses the owner's finance data and never asks for it to be pasted; the owner reports counts and words only.

## The interface
- Few words. Simple, non-technical language. Easy terms.
- Modern, attractive, easy to find things in; the same design in every module with its own colours. Charts and cards, not walls of text.
- Monthly or one-time expenses, never "everyday".
- The latest month with data is the default view (statements arrive monthly).
- Pictures and documents appear **only when asked for** (a count or a question is answered in words).

## Security and operation
- Secure by design for sensitive personal data; structured, fast, reliable; strict, modern coding standards enforced by tests and CI (complexity limit, strict types, lint, formatting, architecture tests).
- Threat model: **theft or loss of the laptop is out of scope.** No login password, no FileVault requirement. Other programs and web pages reaching local ports, hostile files, prompt injection, leaks and bugs **are** in scope.
- Health data is locked until unlocked each session (default; change by decision).
- Docker by default for both apps; no internet for the apps; originals mounted read-only.
- The macOS launcher bundle and data folders keep their old internal names so nothing already on the machine breaks.

## How to work with the owner
- Do not make the owner explain things again. Check this list and `docs/architecture.md` first.
- Do the work; report briefly and honestly: what changed, what was verified, what was not.
- Ask only when a decision truly belongs to the owner.
