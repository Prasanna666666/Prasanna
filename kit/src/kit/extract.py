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
    "date_quote": {"type": "string"},  # the words of the document that carry the date, exactly as printed
    "due_date": {"type": "string"},
    "due_date_quote": {"type": "string"},  # the words of the document that carry the due date, exactly as printed
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
TINY_HEAD_CHARS = 1200  # the brief look at a document: its start, ...
TINY_TAIL_CHARS = 400  # ... and its end


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
        "people, organisations, places, reference numbers, products), date and due_date as YYYY-MM-DD (each with the words of the document that carry it, as date_quote and due_date_quote), reference (any reference or case "
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
    (re.compile(r"\b((?:19|20)\d{2})-(\d{1,2})-(\d{1,2})\b"), (0, 1, 2)),  # 2026-01-12
    (re.compile(r"\b(\d{1,2})[./-](\d{1,2})[./-]((?:19|20)\d{2})\b"), (2, 1, 0)),  # 12-01-2026, day first
    (re.compile(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?[ .-]*({_MONTH})\b[ .,-]*((?:19|20)\d{{2}})\b", re.IGNORECASE), (2, 1, 0)),  # 12 January 2026, 12 jan 2026
    (re.compile(rf"\b({_MONTH})\b[ .]+(\d{{1,2}})(?:st|nd|rd|th)?,?[ ]+((?:19|20)\d{{2}})\b", re.IGNORECASE), (2, 0, 1)),  # January 12, 2026
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


def _written_date(value: object, written: set[str]) -> str | None:
    """The date as YYYY-MM-DD if it is a real calendar date that the document itself writes; otherwise None (unknown, never a guess)."""
    text = str(value or "").strip()
    try:
        date.fromisoformat(text)
    except ValueError:
        return None
    return text if text in written else None


def verify_dates(info: dict, text: str) -> dict:
    """The document's date and due date are kept only if the document writes them (any layout, English or Dutch) and a due date is not before the date. The line that carries each is kept as its source
    when the model quoted it correctly; an unverified date becomes None, so it is unknown rather than a guess."""
    checked = dict(info)
    written = dates_in(text)
    squashed = squash(text.lower())
    for field in ("date", "due_date"):
        found = _written_date(info.get(field), written)
        quote = str(info.get(f"{field}_quote") or "").strip()
        checked[field] = found
        carried = bool(found) and bool(quote) and squash(quote.lower()) in squashed and found in dates_in(quote)
        checked[f"{field}_source"] = quote[:200] if carried else ""
        checked.pop(f"{field}_quote", None)
    if checked["date"] and checked["due_date"] and checked["due_date"] < checked["date"]:
        checked["due_date"], checked["due_date_source"] = None, ""
    return checked


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
MIDDLE_CHARS = 1500  # the most that is added from the middle of a long document
_AMOUNT = re.compile(r"\d[\d.,' ]*[.,]\d{2}\b")  # a number with two decimals: an amount, however the document writes it


def key_passages(middle: str, budget: int = MIDDLE_CHARS) -> str:
    """From the middle of a long document, the lines code finds carry figures (an amount or a date), each with the line before and after, in order, up to `budget` characters.
    Which lines they are is decided by their shape, never by words: the model then also sees totals and dates that are neither at the start nor at the end."""
    lines = middle.splitlines()
    wanted: set[int] = set()
    for i, line in enumerate(lines):
        if _AMOUNT.search(line) or dates_in(line):
            wanted.update(j for j in (i - 1, i, i + 1) if 0 <= j < len(lines))
    out, used = [], 0
    for i in sorted(wanted):
        piece = lines[i].strip()[:200]
        if not piece:
            continue
        if used + len(piece) + 1 > budget:
            break
        out.append(piece)
        used += len(piece) + 1
    return "\n".join(out)


def sample_of(text: str) -> str:
    """What the model is shown of a long document: its beginning (who, what, when), its end (totals, signatures, due dates) and, from the middle, the lines that carry figures."""
    if len(text) <= HEAD_CHARS + TAIL_CHARS:
        return text
    middle = key_passages(text[HEAD_CHARS:-TAIL_CHARS])
    gap = "\n[...]\n"
    return text[:HEAD_CHARS] + gap + (middle + gap if middle else "") + text[-TAIL_CHARS:]


def _classify_fully(client, model: str, name: str, text: str, apps: dict[str, str] | None) -> dict:
    data = _ask(client, model, kind_prompt(apps), f"File name: {name}\n\n{sample_of(text)}", kind_schema(apps))
    checked = verify_trip_fields(verify_dates(verify_amounts(data, text), text), text)
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
    data = _ask(
        client,
        model,
        prompt,
        f"File name: {name}\n\n{text[:TINY_HEAD_CHARS]}\n[...]\n{text[-TINY_TAIL_CHARS:] if len(text) > TINY_HEAD_CHARS + TINY_TAIL_CHARS else ''}",
        schema,
        max_tokens=160,
    )
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
_NUMBER = re.compile(r"^-?\d+(?:[.,]\d+)?$")


def _printed(text_lower: str, squashed_lower: str, quoted: str) -> bool:
    quoted = quoted.strip().lower()
    return bool(quoted) and (quoted in text_lower or squash(quoted) in squashed_lower)


WINDOW, OVERLAP, MIN_SPLIT, LOOKAROUND = 5500, 500, 1500, 300


def _line_start(text: str, pos: int) -> int:
    """`pos` moved back to the start of its line (or word, when the text has no line breaks nearby), so a row is not begun in the middle."""
    for mark in ("\n", " "):
        found = text.rfind(mark, max(0, pos - LOOKAROUND), pos)
        if found >= 0:
            return found + 1
    return pos


def _line_end(text: str, pos: int) -> int:
    """`pos` moved forward to the end of its line (or word), so a row is not cut off in the middle."""
    if pos >= len(text):
        return len(text)
    for mark in ("\n", " "):
        found = text.find(mark, pos, pos + LOOKAROUND)
        if found >= 0:
            return found + 1
    return pos


def _windows(text: str) -> list[tuple[int, str]]:
    """The whole document in pieces the model can hold (with where each starts). Pieces begin and end at line breaks and overlap the one before, so a row is never cut in two. There is no cap on how many."""
    if len(text) <= WINDOW:
        return [(0, text)]
    parts, start = [], 0
    while True:
        end = _line_end(text, min(len(text), start + WINDOW))
        parts.append((start, text[start:end]))
        if end >= len(text):
            return parts
        start = _line_start(text, end - OVERLAP)


def _health_window(client, model: str, name: str, body: str) -> dict:
    data = _ask(client, model, HEALTH_PROMPT, f"File name: {name}\n\n{body}", HEALTH_SCHEMA)
    lower, squashed = body.lower(), squash(body.lower())
    values = []
    for v in data.get("values") or []:
        if not isinstance(v, dict):
            continue
        test, result = str(v.get("test") or "").strip(), str(v.get("value") or "").strip()
        if not _printed(lower, squashed, test) or not _printed(lower, squashed, result):
            continue  # not in the document: dropped
        unit, rng = str(v.get("unit") or "").strip(), str(v.get("range") or "").strip()
        values.append(
            {
                "test": test,
                "value": result,
                "number": float(result.replace(",", ".")) if _NUMBER.match(result) else None,
                "unit": unit if _printed(lower, squashed, unit) else "",
                "range": rng if _printed(lower, squashed, rng) else "",
            }
        )
    medicines = []
    for m in data.get("medicines") or []:
        if not isinstance(m, dict):
            continue
        med = str(m.get("name") or "").strip()
        if not _printed(lower, squashed, med):
            continue
        dose, duration = str(m.get("dose") or "").strip(), str(m.get("duration") or "").strip()
        medicines.append(
            {"name": med, "dose": dose if _printed(lower, squashed, dose) else "", "duration": duration if _printed(lower, squashed, duration) else ""}
        )
    follow_up = str(data.get("follow_up") or "")
    return {"values": values, "medicines": medicines, "follow_up": follow_up if follow_up in dates_in(body) else None}


def _value_key(v: dict) -> tuple:
    return (v["test"].lower(), v["value"], v["unit"], v["range"])


def _medicine_key(m: dict) -> tuple:
    return (m["name"].lower(), m["dose"], m["duration"])


EMPTY_READING: dict = {"values": [], "medicines": [], "follow_up": None}


def _read_piece(client, model: str, name: str, body: str) -> tuple[dict, list[tuple[int, int, str]]]:
    """One piece, and the stretches of it nobody could read (offset, length, why). If the model cannot answer for a piece it is cut in two (overlapping) and each half is read, down to a
    small size; what was read from the good halves is kept, and only the stretch that still fails is reported."""
    try:
        return _health_window(client, model, name, body), []
    except Unclear as why:
        if len(body) <= MIN_SPLIT * 2:
            return EMPTY_READING, [(0, len(body), str(why))]
    half = len(body) // 2
    first, lost_first = _read_piece(client, model, name, body[: half + OVERLAP])
    second, lost_second = _read_piece(client, model, name, body[half:])
    seen = {_value_key(v) for v in first["values"]}
    meds = {_medicine_key(m) for m in first["medicines"]}
    shared = body[half : half + OVERLAP]
    merged = {
        "values": first["values"] + [v for v in second["values"] if not (_value_key(v) in seen and _printed_in(shared, v))],
        "medicines": first["medicines"] + [m for m in second["medicines"] if not (_medicine_key(m) in meds and _printed_in(shared, m))],
        "follow_up": first["follow_up"] or second["follow_up"],
    }
    return merged, lost_first + [(half + offset, length, why) for offset, length, why in lost_second]


def _printed_in(region: str, row: dict) -> bool:
    """True if the row's own words (test and result, or the medicine's name) are printed inside `region`: it was in the overlap, so the piece before saw it too."""
    lower, squashed = region.lower(), squash(region.lower())
    words = (row["test"], row["value"]) if "test" in row else (row["name"],)
    return all(_printed(lower, squashed, w) for w in words)


def _section(text: str, start: int, end: int, number: int, count: int, why: str) -> dict:
    """Which part of the document was not read, in words a person can use: part number, characters and (when the text has page breaks) pages."""
    out: dict = {"part": number, "of": count, "from_character": start, "to_character": end, "reason": why}
    if "\f" in text:
        out["from_page"], out["to_page"] = text.count("\f", 0, start) + 1, text.count("\f", 0, max(start, end - 1)) + 1
    return out


def medical_details(client, model: str, name: str, text: str, progress=None, max_parts: int | None = None) -> dict:
    """Lab values and medicines of a medical document, read over the WHOLE document in overlapping pieces; nothing is capped. The model quotes; code keeps a value only when its test
    name, result, unit and range are printed in the piece it came from, and a date only when it is written there. Text is kept exactly as printed. Nothing is interpreted.
    A row that is in the overlap of two pieces is kept once; the same test with the same result printed twice elsewhere is two rows.
    `complete` is true only if every piece was read; otherwise `unprocessed` says which parts were not (the model could not answer for them, or `max_parts` stopped the reading)."""
    values: list[dict] = []
    medicines: list[dict] = []
    follow_up = None
    unprocessed: list[dict] = []
    parts = _windows(text)
    before: dict = {"values": [], "medicines": []}
    previous_end = 0
    for n, (start, body) in enumerate(parts, 1):
        if max_parts is not None and n > max_parts:
            unprocessed.append(_section(text, start, start + len(body), n, len(parts), "stopped at the limit set for this reading"))
            continue
        if progress:
            progress(f"{name}: reading part {n} of {len(parts)}")
        got, lost = _read_piece(client, model, name, body)
        unprocessed += [_section(text, start + offset, start + offset + length, n, len(parts), why) for offset, length, why in lost]
        head = body[: max(0, previous_end - start)]  # what the piece before also saw
        previous_end = start + len(body)
        seen_values, seen_medicines = {_value_key(v) for v in before["values"]}, {_medicine_key(m) for m in before["medicines"]}
        values += [v for v in got["values"] if not (head and _value_key(v) in seen_values and _printed_in(head, v))]
        medicines += [m for m in got["medicines"] if not (head and _medicine_key(m) in seen_medicines and _printed_in(head, m))]
        follow_up = follow_up or got["follow_up"]
        before = got
    return {"values": values, "medicines": medicines, "follow_up": follow_up, "complete": not unprocessed, "unprocessed": unprocessed}
