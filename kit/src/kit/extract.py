"""What kind of finance file is this, and what are its key facts? The local model reads; code verifies.

The model says what a file is (bank statement, payslip, invoice, receipt, tax, insurance, contract, other) and quotes its key amounts EXACTLY AS
PRINTED. Code then accepts an amount only if that exact text appears in the document, and reads the number from the printed text itself. So an amount
the model made up, or mis-copied, is dropped instead of stored. Bank statements are not read here: see tables.py (layout by the model, figures by code).
"""

from __future__ import annotations

import json
import re
from datetime import date

from .amounts import money_from_printed
from .text import clean, squash

MONEY_FIELDS = ("total", "vat", "gross", "net", "tax", "pension", "holiday_pay")
_STR = {"type": ["string", "null"]}
FACT_FIELDS = {
    "title": {"type": "string"},
    "summary": {"type": "string"},
    "party": {"type": "string"},  # who it is from / to: the shop, supplier, employer, insurer, tax office, hospital ...
    "date": {"type": "string"},
    "due_date": {"type": "string"},
    "reference": {"type": "string"},  # an invoice / policy / case number
    "currency": {"type": "string"},
    "period": {"type": "string"},  # the month or year a statement or slip covers
    "start_date": {"type": "string"},  # a stay or trip: departure or check-in, YYYY-MM-DD
    "end_date": {"type": "string"},  # return, arrival or check-out, YYYY-MM-DD
    "place": {"type": "string"},  # where to: the destination or the hotel's city
    "entities": {
        "type": "array",
        "items": {"type": "string"},
    },  # the distinctive things the file is about, as written: people, organisations, places, reference numbers, products
    **dict.fromkeys(MONEY_FIELDS, _STR),  # each amount exactly as printed in the document, e.g. "3.500,00"
}


def kind_schema(apps: dict[str, str] | None) -> dict:
    """What the model may answer: what the file is in its own words (no list to choose from), the apps it is about (only the ones declared), and the facts."""
    props: dict = {"kind": {"type": "string"}, **FACT_FIELDS}
    if apps:
        props["apps"] = {"type": "array", "items": {"type": "string", "enum": list(apps)}}
    return {"type": "object", "properties": props, "required": ["kind"]}


def kind_prompt(apps: dict[str, str] | None) -> str:
    """The question: describe the file freely, say which of the declared apps it is about (none if none), and give the facts exactly as printed."""
    about = "".join(f"\n- {name}: {text}" for name, text in (apps or {}).items())
    marks = f" Then say which of these apps it is about, if any (none if it is about none of them):{about}\n" if about else " "
    return (
        "You read the start of a personal document. It may be in any language. Say what it is in a few words, as a person would name it (kind)."
        + marks
        + "Then give: title (a few words), summary (one short sentence), party (who it is from or to), entities (at most eight distinctive things the file is about, each exactly as written: "
        "people, organisations, places, reference numbers, products), date and due_date as YYYY-MM-DD, reference (any reference or case "
        'number), currency (EUR, INR ...). Give each amount EXACTLY AS PRINTED in the document, as text, character for character (for example "3.500,00"): '
        "total (the main amount) and vat, and where the document states them period (the month or year it covers) and gross, net, tax, pension, holiday_pay. For a stay or trip "
        "also give start_date and end_date as YYYY-MM-DD and place (the destination), only as printed. Leave out or use null what is not there. Never invent or recalculate."
    )


class Unclear(Exception):
    """The model answered, but not with anything usable (twice). The document is not 'other': it is not understood yet and is tried again later."""


def _ask(client, model: str, system: str, text: str, schema: dict, max_tokens: int | None = None) -> dict:
    """Ask the model twice at most. Raises Unclear with the reason (never with anything from the text): nothing came back, the answer was cut off or not valid, or it was empty.
    An answer that was cut off is asked for again with room for a longer one, not with the same limit that cut it off."""
    reason = "the model gave no usable answer"
    room = max_tokens
    for attempt in range(2):
        extra = {"max_tokens": room} if room else {}  # a short answer is capped: the model stops as soon as it has said it
        msg = client.chat(model, [{"role": "system", "content": system}, {"role": "user", "content": text}], schema=schema, **extra)
        content = str((msg or {}).get("content") or "")
        if not content.strip():
            reason = "the model returned nothing"
            continue
        try:
            data = json.loads(content)
        except ValueError:
            reason = "the model's answer was cut off or not valid"
            room = (room or 600) * 2 if attempt == 0 else room  # once more, with twice the room
            continue
        if isinstance(data, dict) and data:
            return data
        reason = "the model's answer was empty"
    raise Unclear(reason)


def verify_amounts(info: dict, text: str) -> dict:
    """Keep an amount only if it appears in the document exactly as quoted; replace the quote by the number read from it."""
    haystack = squash(text)
    checked = dict(info)
    dropped = []
    for f in MONEY_FIELDS:
        quoted = info.get(f)
        if quoted in (None, ""):
            checked[f] = None
            continue
        minor = money_from_printed(str(quoted)) if squash(str(quoted)) in haystack else None
        checked[f] = minor / 100 if minor is not None else None
        if minor is None:
            dropped.append(f)
    checked["unverified_fields"] = dropped
    return checked


_MONTHS = {
    **{
        m: i
        for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"], 1)
    },
    **{
        m: i
        for i, m in enumerate(["januari", "februari", "maart", "april", "mei", "juni", "juli", "augustus", "september", "oktober", "november", "december"], 1)
    },
    **{m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)},
    "mrt": 3,
    "sept": 9,
    "okt": 10,
}
_MONTH = "|".join(sorted(_MONTHS, key=len, reverse=True))
_DATE_PATTERNS = (
    (re.compile(r"\b(20\d{2})-(\d{1,2})-(\d{1,2})\b"), (0, 1, 2)),  # 2026-01-12
    (re.compile(r"\b(\d{1,2})[./-](\d{1,2})[./-](20\d{2})\b"), (2, 1, 0)),  # 12-01-2026, day first
    (re.compile(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?[ .-]*({_MONTH})\b[ .,-]*(20\d{{2}})\b", re.IGNORECASE), (2, 1, 0)),  # 12 January 2026, 12 jan 2026
    (re.compile(rf"\b({_MONTH})\b[ .]+(\d{{1,2}})(?:st|nd|rd|th)?,?[ ]+(20\d{{2}})\b", re.IGNORECASE), (2, 0, 1)),  # January 12, 2026
)


def dates_in(text: str) -> set[str]:
    """Every calendar date written in the text, as YYYY-MM-DD (day first for numbers, English and Dutch month names)."""
    found: set[str] = set()
    for pattern, (y, m, d) in _DATE_PATTERNS:
        for match in pattern.finditer(text):
            parts = match.groups()
            month = parts[m]
            month_no = int(month) if month.isdigit() else _MONTHS.get(month.lower(), 0)
            try:
                found.add(date(int(parts[y]), month_no, int(parts[d])).isoformat())
            except ValueError:
                continue
    return found


def verify_trip_fields(info: dict, text: str) -> dict:
    """A ticket's or booking's dates and place are kept only if the document itself says them: the dates must be written in it, the end not before the start."""
    checked = dict(info)
    written = dates_in(text)
    for field in ("start_date", "end_date"):
        value = str(info.get(field) or "")
        checked[field] = value if value in written else None
    if checked["start_date"] and checked["end_date"] and checked["end_date"] < checked["start_date"]:
        checked["end_date"] = None
    place = str(info.get("place") or "").strip()
    checked["place"] = place[:80] if place and place.lower() in text.lower() else ""
    return checked


HEAD_CHARS, TAIL_CHARS = 3000, 1500


def sample_of(text: str) -> str:
    """What the model is shown of a long document: its beginning (who, what, when) and its end (totals, signatures, due dates), not only the first pages."""
    if len(text) <= HEAD_CHARS + TAIL_CHARS:
        return text
    return text[:HEAD_CHARS] + "\n[...]\n" + text[-TAIL_CHARS:]


def _classify_fully(client, model: str, name: str, text: str, apps: dict[str, str] | None) -> dict:
    data = _ask(client, model, kind_prompt(apps), f"File name: {name}\n\n{sample_of(text)}", kind_schema(apps))
    checked = verify_trip_fields(verify_amounts(data, text), text)
    checked["kind"] = str(checked.get("kind") or "").strip()[:60]
    checked["apps"] = [a for a in (checked.get("apps") or []) if a in (apps or {})]
    party = str(checked.get("party") or "").strip()
    if party and squash(party.lower()) not in squash(text.lower()):
        checked["party"] = ""  # a name the document does not contain is the model's invention
    whole = squash(text.lower())
    listed = checked.get("entities")
    given = listed if isinstance(listed, list) else []
    checked["entities"] = list(dict.fromkeys(str(e).strip() for e in given if str(e).strip() and squash(str(e).lower()) in whole))[
        :8
    ]  # only what the file really says
    return checked


def _classify_briefly(client, model: str, name: str, text: str, apps: dict[str, str] | None) -> dict:
    """The second look: a much smaller question (only what it is, a title and the apps), about a shorter piece, for a file the full question got no usable answer for."""
    schema = kind_schema(apps)
    schema = {**schema, "properties": {k: v for k, v in schema["properties"].items() if k in ("kind", "title", "apps")}}
    prompt = kind_prompt(apps).split(" Then give:")[0] + " Then give a short title. Nothing else."
    data = _ask(client, model, prompt, f"File name: {name}\n\n{text[:1200]}\n[...]\n{text[-400:] if len(text) > 1600 else ''}", schema, max_tokens=160)
    return {
        "kind": str(data.get("kind") or "").strip()[:60],
        "title": str(data.get("title") or "")[:120],
        "apps": [a for a in (data.get("apps") or []) if a in (apps or {})],
        "partial": True,
    }  # a partial reading: no amounts or dates are kept without the full one


def _classify_tiny(client, model: str, name: str, text: str, apps: dict[str, str] | None) -> dict:
    """The smallest question: only what it is (and the apps), about the first lines of the file. Used when the larger questions got no usable answer."""
    schema = kind_schema(apps)
    schema = {**schema, "properties": {k: v for k, v in schema["properties"].items() if k in ("kind", "apps")}}
    prompt = kind_prompt(apps).split(" Then give:")[0] + " Nothing else."
    data = _ask(client, model, prompt, f"File name: {name}\n\n{text[:600]}", schema, max_tokens=60)
    return {"kind": str(data.get("kind") or "").strip()[:60], "title": "", "apps": [a for a in (data.get("apps") or []) if a in (apps or {})], "partial": True}


def classify(client, model: str, name: str, text: str, apps: dict[str, str] | None = None) -> dict:
    """What the file is, in the model's own words, which of the declared `apps` it is about, and its key facts. The model is shown the beginning and the end; every amount, date and
    party is then checked against the WHOLE text and dropped if the document does not say it. When the full question gets no usable answer, a smaller one is asked about a shorter
    piece. If that fails too, Unclear is raised: the file is never turned into 'about nothing' because the model failed."""
    text = clean(text)
    try:
        return _classify_fully(client, model, name, text, apps)
    except Unclear:
        pass
    try:
        return _classify_briefly(client, model, name, text, apps)
    except Unclear:
        return _classify_tiny(client, model, name, text, apps)  # the last, smallest look: only a few lines of the file and a few words of answer


# ---- health: lab values and medicines, only what the document itself prints -------------------------------------------------------------------
HEALTH_SCHEMA = {
    "type": "object",
    "properties": {
        "values": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "test": {"type": "string"},  # the name of the measurement, as printed (Hemoglobine, Cholesterol totaal ...)
                    "value": {"type": "string"},  # the result exactly as printed, e.g. "8,4"
                    "unit": {"type": "string"},  # as printed, e.g. "mmol/L"
                    "range": {"type": "string"},  # the reference range, only if the document prints one, e.g. "7,5 - 10,0"
                },
                "required": ["test", "value"],
            },
        },
        "medicines": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"name": {"type": "string"}, "dose": {"type": "string"}, "duration": {"type": "string"}},
                "required": ["name"],
            },
        },
        "follow_up": {"type": "string"},  # a follow-up or next appointment date, YYYY-MM-DD, only if the document states one
    },
}
HEALTH_PROMPT = (
    "You read a medical document (a lab result, report, prescription or appointment letter), in Dutch or English. List every measured value in it: test = the "
    'name as printed, value = the result EXACTLY as printed (character for character, for example "8,4"), unit as printed, range = the reference range ONLY if the '
    "document prints one. List every prescribed medicine: name as printed, dose and duration as printed. If the document states a follow-up or next appointment date, "
    "give it as YYYY-MM-DD. Copy only what is written. Never interpret, diagnose, estimate, convert or invent anything; leave out what is not there."
)
MAX_VALUES, MAX_MEDICINES = 60, 30
_NUMBER = re.compile(r"^-?\d+(?:[.,]\d+)?$")


def _printed(text_lower: str, squashed_lower: str, quoted: str) -> bool:
    quoted = quoted.strip().lower()
    return bool(quoted) and (quoted in text_lower or squash(quoted) in squashed_lower)


WINDOW, OVERLAP, MAX_WINDOWS = 5500, 500, 12


def _windows(text: str) -> list[str]:
    """The whole document in pieces the model can hold, each overlapping the one before so a row is never cut in two."""
    if len(text) <= WINDOW:
        return [text]
    step = WINDOW - OVERLAP
    return [text[i : i + WINDOW] for i in range(0, min(len(text), step * MAX_WINDOWS), step)]


def _health_window(client, model: str, name: str, body: str) -> dict:
    data = _ask(client, model, HEALTH_PROMPT, f"File name: {name}\n\n{body}", HEALTH_SCHEMA)
    lower, squashed = body.lower(), squash(body.lower())
    values = []
    for v in (data.get("values") or [])[:MAX_VALUES]:
        if not isinstance(v, dict):
            continue
        test, result = str(v.get("test") or "").strip(), str(v.get("value") or "").strip()
        if not _printed(lower, squashed, test) or not _printed(lower, squashed, result):
            continue  # not in the document: dropped
        unit, rng = str(v.get("unit") or "").strip(), str(v.get("range") or "").strip()
        values.append(
            {
                "test": test[:80],
                "value": result[:40],
                "number": float(result.replace(",", ".")) if _NUMBER.match(result) else None,
                "unit": unit[:30] if _printed(lower, squashed, unit) else "",
                "range": rng[:40] if _printed(lower, squashed, rng) else "",
            }
        )
    medicines = []
    for m in (data.get("medicines") or [])[:MAX_MEDICINES]:
        if not isinstance(m, dict):
            continue
        med = str(m.get("name") or "").strip()
        if not _printed(lower, squashed, med):
            continue
        dose, duration = str(m.get("dose") or "").strip(), str(m.get("duration") or "").strip()
        medicines.append(
            {
                "name": med[:80],
                "dose": dose[:60] if _printed(lower, squashed, dose) else "",
                "duration": duration[:60] if _printed(lower, squashed, duration) else "",
            }
        )
    follow_up = str(data.get("follow_up") or "")
    return {"values": values, "medicines": medicines, "follow_up": follow_up if follow_up in dates_in(body) else None}


def medical_details(client, model: str, name: str, text: str, progress=None) -> dict:
    """Lab values and medicines of a medical document, read over the WHOLE document (a long report is read in overlapping pieces, not cut off after the first pages).
    The model quotes; code keeps a value only when its test name, its result, its unit and its range are printed in the piece it came from, a date only when it is written
    there, and reads the number from the printed result itself. Nothing is interpreted. The same row seen in two pieces is kept once."""
    values: list[dict] = []
    medicines: list[dict] = []
    follow_up = None
    parts = _windows(text)
    for n, body in enumerate(parts, 1):
        if progress:
            progress(f"{name}: reading part {n} of {len(parts)}")
        got = _health_window(client, model, name, body)
        for v in got["values"]:
            if not any((v["test"].lower(), v["value"], v["unit"]) == (o["test"].lower(), o["value"], o["unit"]) for o in values):
                values.append(v)
        for m in got["medicines"]:
            if not any(m["name"].lower() == o["name"].lower() for o in medicines):
                medicines.append(m)
        follow_up = follow_up or got["follow_up"]
    return {"values": values[: MAX_VALUES * 4], "medicines": medicines[: MAX_MEDICINES * 2], "follow_up": follow_up}
