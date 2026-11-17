# UI review

All screenshots are of the real apps running locally with **invented data** (an "Example Employer", "Alex Example", dummy shops, dummy documents). No real personal data appears anywhere. The AI model was not running, so the assistant shows "AI model not running"; chat answers are not shown.

Generated with Playwright at 1280×900 (desktop), 1280×900 dark, and 390×844 (phone), at 2× pixel density. Reproduce: start Finance (`ATLAS_ALLOW_PLAIN=1 finance ui`), Documents (`library serve`) and Atlas (`python -m atlas`) with a throw-away `ATLAS_HOME`, then run a script that opens `http://atlas.localhost:8000/#/…`.

**How to comment:** open the pull request, go to "Files changed", find the image under `docs/screenshots/`, and comment on it (GitHub allows comments on images in the diff). Start the comment with the screenshot number, e.g. `UI-3`.

## Desktop, light

### UI-1 Overview
![Overview](screenshots/01-overview.png)

### UI-2 Finance dashboard
![Finance dashboard](screenshots/02-finance-dashboard.png)

### UI-2b Finance dashboard, scrolled
![Finance dashboard scrolled](screenshots/02b-finance-dashboard-scrolled.png)

### UI-3 Health
![Health](screenshots/03-health.png)

### UI-4 Travel
![Travel](screenshots/04-travel.png)

### UI-5 Photos (no photo drive is connected in this demo, so this is the "not connected" state)
![Photos](screenshots/05-photos.png)

### UI-6 Calendar (the demo's events are in December, so November is empty)
![Calendar](screenshots/06-calendar.png)

Documents has no page of its own: it is a hidden module that feeds Health, Travel, Photos and Calendar. Its stand-alone address only says "These pages belong inside Atlas".

### UI-8 First run (an empty database)
![First run](screenshots/08-finance-first-run-empty.png)

## Dark (re-taken after the contrast fix: active controls now use dark text on the light accent)

![Overview, dark](screenshots/01-overview-dark.png)
![Finance, dark](screenshots/02-finance-dashboard-dark.png)
![Health, dark](screenshots/03-health-dark.png)

## Phone

<img src="screenshots/01-overview-phone.png" width="260"> <img src="screenshots/02-finance-dashboard-phone.png" width="260"> <img src="screenshots/03-health-phone.png" width="260">

## What the author sees (to start the discussion)

| ID | Where | Observation | Rule it touches |
|---|---|---|---|
| UI-A | Travel hero | A green gradient. The design rule is "no gradients, one accent"; the Finance sparkline also fades | design.md |
| UI-B | Health | Reference ranges and values use the document's decimal comma (`8,4`), the chart axis uses a point (`9.3`) | R-Q1 plain, consistent numbers |
| UI-C | Health | "1 reports" (plural not handled); "0 medicines" shown though none were expected | plain words |
| UI-D | Phone | The floating **Ask** button covers part of the card behind it | usability |
| UI-E | Finance dashboard | "↑ 142% monthly vs before" is shown with no explanation of what "before" is | plain words |
| UI-F | Finance dashboard | "Due in 3 weeks €0 / 0 payments" cards that say nothing take the same space as cards with content | density |
| UI-G | Overview | The top bar has six status pills plus the Update button; on narrower widths the pill text wraps ("AI model not / running", "Read new / files") | layout |
| UI-H | All | Apps opened outside Atlas show a stub page for Documents ("These pages belong inside Atlas") and an empty-looking Finance shell; intended, but is it clear? | first run |
| UI-I | Photos | The sidebar dot and top pill for Photos are green while the page says "Photos are not connected" | honest status |
| UI-L | First run | The empty Finance dashboard shows a welcome card and an "Add my files" button, then a "Today / Nothing today." card; does the first step feel obvious? | first run |
| UI-K | Calendar | An empty month is a grid of large blank boxes; "Coming up" is below the fold | density |
| UI-J | All | A pending change ("Waiting for your yes: …") is shown as a note under the answer, not as a card with a button; the owner must type "yes". Pictures use a window with a Confirm button | consistency of confirmation |

## One bug the screenshots found

Before this branch's last commit, every card on every page was invisible (`defects.md` D-12). The Finance dashboard looked like a greeting and an empty page. Please look at screenshots 02 and 02b, which show the fixed state, and tell me if anything still looks wrong or empty.


## Changes made after the review of this round (screenshots were retaken)

| ID | State |
|---|---|
| UI-A Travel gradient | **Fixed**: a plain place colour, dark enough for white text in every hue (axe, light and dark) |
| UI-B decimal separators | **Fixed**: the chart axis uses the report's decimal comma |
| UI-C "1 reports" | **Fixed** (`1 report`, `2 tests`, `0 medicines`) |
| UI-D floating Ask button | **Fixed**: 120 px of room at the bottom on phones (measured, 120 px); not visually verified by a scrolled phone screenshot |
| UI-I Photos dot | **Fixed**: red when the photo drive is not connected (`03`/`04`/`05` show it) |
| Finance "Cash €0" | **Fixed**: "no statements read yet" |
| UI-17 date source | **Done**: screenshot `09-finance-documents-with-date-source.png` |
| Fixed after `80562da` (UI-J on the owner's decision: a pending change shows "Yes, do it" and "No, leave it" buttons that send the person's own `yes` or `no`, see screenshot 16) |
| Fixed after `80562da` | UI-E "142% vs before" now names its month (`631130b`); UI-F empty tile hidden (`631130b`); UI-G one summary chip, "Read new files" stays in view (`aec2230`); UI-K empty month is one line with a jump (`aec2230`); UI-A gradients now flat tints (`40d023b`) |
| Still open | UI-H apps opened outside Atlas show a stub page; UI-J a pending change is a note, not a card with a button (the typed yes is the consent design; a button is a design decision); UI-L first-run guidance (roadmap) |

A regression of mine (a hero card's headline turning white on white) passed `scripts/check-pages.js` and was caught only by looking at the screenshot (D-42).
