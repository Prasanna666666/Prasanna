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

KINDS = ("bank_statement", "payslip", "annual_statement", "invoice", "receipt", "tax", "insurance", "contract", "ticket", "booking", "medical", "other")
MONEY_FIELDS = ("total", "vat", "gross", "net", "tax", "pension", "holiday_pay")
_STR = {"type": ["string", "null"]}
KIND_SCHEMA = {
    "type": "object",
    "properties": {
        "kind": {"type": "string", "enum": list(KINDS)},
        "title": {"type": "string"},
        "summary": {"type": "string"},
        "party": {"type": "string"},  # who it is from / to: the shop, supplier, employer, insurer, tax office ...
        "date": {"type": "string"},
        "due_date": {"type": "string"},
        "reference": {"type": "string"},  # YYYY-MM-DD; invoice / policy / case number
        "currency": {"type": "string"},
        "period": {"type": "string"},  # YYYY-MM for a payslip
        "start_date": {"type": "string"},  # a ticket or booking: departure or check-in, YYYY-MM-DD
        "end_date": {"type": "string"},  # return, arrival or check-out, YYYY-MM-DD
        "place": {"type": "string"},  # where to: the destination or the hotel's city
        **dict.fromkeys(MONEY_FIELDS, _STR),  # each amount exactly as printed in the document, e.g. "3.500,00"
    },
    "required": ["kind"],
}
KIND_PROMPT = (
    "You read the start of a personal finance document. It may be in Dutch or English. Say what it is: bank_statement (a list of account "
    "transactions), payslip (salary slip / loonstrook), annual_statement (a yearly income statement / jaaropgave: gross, tax and net for a whole year), invoice (factuur), receipt (bon / kassabon), tax (belasting: aanslag, aangifte), insurance "
    "(verzekering: polis, premie), contract (agreement, lease, loan), ticket (a flight, train or event ticket or boarding pass), booking (a hotel, rental or "
    "reservation confirmation), medical (a medical report, prescription, lab result or appointment letter), or other. A payment confirmation or order confirmation is a receipt. Then give: title (a few words), summary (one short sentence), party "
    "(who it is from or to: shop, supplier, employer, insurer, tax office), date and due_date as YYYY-MM-DD, reference (invoice / policy / case "
    'number), currency (EUR, INR ...). Give each amount EXACTLY AS PRINTED in the document, as text, character for character (for example "3.500,00"): '
    "total and vat for invoices and receipts; for a payslip also period as YYYY-MM and gross = bruto, net = netto paid out, tax = loonheffing, "
    "pension = pensioen, holiday_pay = vakantiegeld; for an annual_statement give period as the year YYYY and gross, tax and net the same way. For a ticket or booking also give start_date and end_date as YYYY-MM-DD and place (the destination), only as printed. Leave out or use null what is not there. Never invent or recalculate."
)


class Unclear(Exception):
    """The model answered, but not with anything usable (twice). The document is not 'other': it is not understood yet and is tried again later."""


def _ask(client, model: str, system: str, text: str, schema: dict) -> dict:
    for _ in range(2):
        msg = client.chat(model, [{"role": "system", "content": system}, {"role": "user", "content": text}], schema=schema)
        try:
            data = json.loads(msg.get("content") or "")
        except ValueError:
            continue  # once more: a small model sometimes returns a broken answer the first time
        if isinstance(data, dict) and data:
            return data
    raise Unclear("the model gave no usable answer")


def _squash(s: str) -> str:
    return re.sub(r"\s+", "", s)


def verify_amounts(info: dict, text: str) -> dict:
    """Keep an amount only if it appears in the document exactly as quoted; replace the quote by the number read from it."""
    haystack = _squash(text)
    checked = dict(info)
    dropped = []
    for f in MONEY_FIELDS:
        quoted = info.get(f)
        if quoted in (None, ""):
            checked[f] = None
            continue
        minor = money_from_printed(str(quoted)) if _squash(str(quoted)) in haystack else None
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


KIND_ONLY_SCHEMA = {"type": "object", "properties": {"kind": {"type": "string", "enum": list(KINDS)}, "title": {"type": "string"}}, "required": ["kind"]}
KIND_ONLY_PROMPT = "Say what kind of document this is (one of the allowed kinds) and give it a short title. Nothing else."


def _classify_fully(client, model: str, name: str, text: str) -> dict:
    data = _ask(client, model, KIND_PROMPT, f"File name: {name}\n\n{sample_of(text)}", KIND_SCHEMA)
    if data.get("kind") not in KINDS:
        raise Unclear("the model named a kind that does not exist")
    checked = verify_trip_fields(verify_amounts(data, text), text)
    party = str(checked.get("party") or "").strip()
    if party and _squash(party.lower()) not in _squash(text.lower()):
        checked["party"] = ""  # a name the document does not contain is the model's invention
    return checked


def _classify_briefly(client, model: str, name: str, text: str) -> dict:
    """The second look: a much smaller question (only the kind and a title, about a shorter piece), for a document the full question got no usable answer for."""
    data = _ask(client, model, KIND_ONLY_PROMPT, f"File name: {name}\n\n{text[:1200]}\n[...]\n{text[-400:] if len(text) > 1600 else ''}", KIND_ONLY_SCHEMA)
    if data.get("kind") not in KINDS:
        raise Unclear("the model named a kind that does not exist")
    return {
        "kind": data["kind"],
        "title": str(data.get("title") or "")[:120],
        "partial": True,
    }  # a partial reading: no amounts or dates are kept without the full one


def classify(client, model: str, name: str, text: str) -> dict:
    """What the file is and its key facts. The model is shown the beginning and the end; every amount, date and party is then checked against the WHOLE text and dropped if the
    document does not say it. When the full question gets no usable answer, a smaller one is asked about a shorter piece. If that fails too, Unclear is raised: the
    document is never turned into 'other' because the model failed."""
    try:
        return _classify_fully(client, model, name, text)
    except Unclear:
        return _classify_briefly(client, model, name, text)


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
    return bool(quoted) and (quoted in text_lower or _squash(quoted) in squashed_lower)


WINDOW, OVERLAP, MAX_WINDOWS = 5500, 500, 12


def _windows(text: str) -> list[str]:
    """The whole document in pieces the model can hold, each overlapping the one before so a row is never cut in two."""
    if len(text) <= WINDOW:
        return [text]
    step = WINDOW - OVERLAP
    return [text[i : i + WINDOW] for i in range(0, min(len(text), step * MAX_WINDOWS), step)]


def _health_window(client, model: str, name: str, body: str) -> dict:
    data = _ask(client, model, HEALTH_PROMPT, f"File name: {name}\n\n{body}", HEALTH_SCHEMA)
    lower, squashed = body.lower(), _squash(body.lower())
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


def medical_details(client, model: str, name: str, text: str) -> dict:
    """Lab values and medicines of a medical document, read over the WHOLE document (a long report is read in overlapping pieces, not cut off after the first pages).
    The model quotes; code keeps a value only when its test name, its result, its unit and its range are printed in the piece it came from, a date only when it is written
    there, and reads the number from the printed result itself. Nothing is interpreted. The same row seen in two pieces is kept once."""
    values: list[dict] = []
    medicines: list[dict] = []
    follow_up = None
    for body in _windows(text):
        got = _health_window(client, model, name, body)
        for v in got["values"]:
            if not any((v["test"].lower(), v["value"], v["unit"]) == (o["test"].lower(), o["value"], o["unit"]) for o in values):
                values.append(v)
        for m in got["medicines"]:
            if not any(m["name"].lower() == o["name"].lower() for o in medicines):
                medicines.append(m)
        follow_up = follow_up or got["follow_up"]
    return {"values": values[: MAX_VALUES * 4], "medicines": medicines[: MAX_MEDICINES * 2], "follow_up": follow_up}
