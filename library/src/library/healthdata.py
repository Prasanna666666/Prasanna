"""Health: the medical documents, their values, medicines and follow-ups, from what was read."""

from __future__ import annotations

import json
import re
from typing import Any

from . import apps, judging, store


# ---- Health: the person's own medical documents, only when unlocked; values and medicines exactly as the documents print them --------------------
def _medical_documents(conn) -> list[dict]:
    clause, args = judging._apps_clause(apps.with_reading("medical"))
    out = []
    for r in conn.execute(f"SELECT id, name, kind, facts FROM documents WHERE judged=1 AND facts<>'' AND {clause}", args):
        facts = json.loads(r["facts"])
        out.append(
            {
                "id": r["id"],
                "name": r["name"],
                "file_kind": r["kind"],
                "title": store.proper_name(facts, r["name"], facts.get("kind", "")),
                "date": facts.get("date") or "",
                "party": facts.get("party") or "",
                "health": facts.get("health") or {},
            }
        )
    return sorted(out, key=lambda d: (d["date"], d["id"]))


def health_funnel(conn) -> dict[str, int]:
    """Why Health may be empty, in counts: how many health documents there are, how many the model has understood, how many hold lab values, and where the rest is stuck."""
    where, args = judging._apps_clause(apps.with_reading("medical"))

    def count(extra: str = "") -> int:
        return int(conn.execute(f"SELECT COUNT(*) FROM documents WHERE {where}{extra}", args).fetchone()[0])

    docs = _medical_documents(conn)
    return {
        "found": count(),
        "understood": len(docs),
        "with_values": sum(1 for d in docs if d["health"].get("values")),
        "read_in_part": sum(1 for d in docs if d["health"] and not d["health"].get("complete")),
        "waiting_for_the_model": count(" AND judged=0"),
        "not_understood": count(" AND judged=3"),
        "no_readable_text": count(" AND TRIM(text)='' AND kind<>'email'"),
    }


def health_documents(conn) -> dict[str, Any]:
    """Every medical document in date order, newest first: what it is, who it is from, how many values and medicines it holds, and any follow-up it states."""
    docs = [
        {
            "id": d["id"],
            "name": d["name"],
            "title": d["title"],
            "date": d["date"],
            "party": d["party"],
            "values": len(d["health"].get("values") or []),
            "medicines": len(d["health"].get("medicines") or []),
            "follow_up": d["health"].get("follow_up"),
            "complete": bool(d["health"].get("complete")),
            "not_read": d["health"].get("unprocessed") or [],
        }
        for d in reversed(_medical_documents(conn))
        if d["file_kind"] != "email"  # the documents, never a whole email
    ]
    return {"documents": docs}


# The common blood and health tests, by the names reports use (English and Dutch). A reading is filed under the common name when its test name matches.
COMMON_TESTS: tuple[tuple[str, str], ...] = (
    ("Hemoglobin", r"\bhemoglobin\w*|\bhaemoglobin\w*|^hb$"),
    ("HbA1c", r"hba1c|hb a1c|geglycosyleerd"),
    ("Glucose", r"\bglucose|\bnuchter"),
    ("Cholesterol (total)", r"cholesterol(?!.*(ldl|hdl))"),
    ("LDL cholesterol", r"\bldl"),
    ("HDL cholesterol", r"\bhdl"),
    ("Triglycerides", r"triglyc\w*"),
    ("Creatinine", r"creatinin\w*|kreatinin\w*"),
    ("eGFR", r"\begfr\b|\bgfr\b"),
    ("TSH", r"\btsh\b"),
    ("Vitamin D", r"vitamin\w* d|25-?oh"),
    ("Vitamin B12", r"vitamin\w* b ?12|\bb12\b"),
    ("Ferritin", r"ferritin\w*"),
    ("CRP", r"\bcrp\b|c-reactiev\w*|c-reactive\w*"),
    ("ALT", r"\balat\b|\balt\b"),
    ("AST", r"\basat\b|\bast\b"),
    ("GGT", r"\bggt\b|gamma-?gt"),
    ("Sodium", r"\bnatrium\b|\bsodium\b"),
    ("Potassium", r"\bkalium\b|\bpotassium\b"),
    ("White blood cells", r"leukocyt\w*|\bwbc\b|white blood"),
    ("Platelets", r"trombocyt\w*|\bplatelet\w*"),
    ("Hematocrit", r"hematocriet|haematocrit|hematocrit"),
)
_NUM = r"[-+]?\d+(?:[.,]\d+)?"
_BETWEEN = re.compile(rf"^\s*({_NUM})\s*(?:-|–|—|tot|to)\s*({_NUM})\s*[a-zA-Zµ%/ ]*$")
_BELOW = re.compile(rf"^\s*(<|≤|<=)\s*({_NUM})")
_ABOVE = re.compile(rf"^\s*(>|≥|>=)\s*({_NUM})")


def _to_float(text: str) -> float:
    return float(text.replace(",", "."))


def range_flag(number: float | None, printed: str) -> str:
    """Whether a result lies inside the reference range the report itself prints: in_range, below_range, above_range, or no_range when there is no number or no
    range that can be read. Only a comparison with the printed range: not a judgement about health."""
    if number is None or not printed:
        return "no_range"
    if m := _BETWEEN.match(printed):
        low, high = sorted((_to_float(m.group(1)), _to_float(m.group(2))))
        return "below_range" if number < low else "above_range" if number > high else "in_range"
    if m := _BELOW.match(printed):
        limit = _to_float(m.group(2))
        return "in_range" if (number < limit if m.group(1) == "<" else number <= limit) else "above_range"
    if m := _ABOVE.match(printed):
        limit = _to_float(m.group(2))
        return "in_range" if (number > limit if m.group(1) == ">" else number >= limit) else "below_range"
    return "no_range"


def _common_name(test: str) -> str:
    lower = " ".join(test.lower().split())
    for name, pattern in COMMON_TESTS:
        if re.search(pattern, lower):
            return name
    return ""


def health_values(conn, test: str = "") -> dict[str, Any]:
    """Each measurement over time exactly as the documents print it, grouped (the common tests under their common names), with for each: the latest result, whether
    it lies inside the reference range printed on that report, and how it changed since the reading before. Never interpreted."""
    groups: dict[str, dict[str, Any]] = {}
    for d in _medical_documents(conn):
        for v in d["health"].get("values") or []:
            common = _common_name(v["test"])
            name = common or " ".join(v["test"].split())
            if test and test.lower() not in name.lower() and test.lower() not in v["test"].lower():
                continue
            group = groups.setdefault(name.lower(), {"test": name, "common": bool(common), "unit": "", "readings": []})
            group["unit"] = group["unit"] or v.get("unit") or ""
            group["readings"].append(
                {
                    "date": d["date"],
                    "value": v["value"],
                    "number": v.get("number"),
                    "unit": v.get("unit") or "",
                    "range": v.get("range") or "",
                    "flag": "unverified" if v.get("check") else range_flag(v.get("number"), v.get("range") or ""),
                    "check": v.get("check") or "",
                    "document": d["name"],
                    "id": d["id"],
                }
            )
    for g in groups.values():
        g["readings"].sort(key=lambda r: (r["date"], r["id"]))
        latest = g["readings"][-1]
        g["latest"], g["flag"] = latest, latest["flag"]
        g["change"] = None
        before = next((r for r in reversed(g["readings"][:-1]) if r["number"] is not None and not r["check"]), None)
        if before is not None and latest["number"] is not None and not latest["check"]:
            diff = round(latest["number"] - before["number"], 4)
            g["change"] = {
                "since": before["date"],
                "absolute": round(diff, 2),
                "percent": round(diff / before["number"] * 100, 1) if before["number"] else None,
                "direction": "up" if diff > 0 else "down" if diff < 0 else "same",
            }
    ordered = sorted(groups.values(), key=lambda g: g["test"].lower())
    order = {name: i for i, (name, _p) in enumerate(COMMON_TESTS)}
    common_list = sorted((g for g in ordered if g["common"]), key=lambda g: order[g["test"]])
    return {
        "tests": ordered,
        "attention": [g for g in ordered if g["flag"] in ("above_range", "below_range")],
        "common": common_list,
        "other": [g for g in ordered if not g["common"]],
        "note": "A flag only compares a result with the reference range printed on that report. It is not a diagnosis or advice.",
    }


def health_medicines(conn) -> dict[str, Any]:
    """Every medicine a document prescribes, newest first, with the dose and duration as printed."""
    meds = [
        {"name": m["name"], "dose": m.get("dose") or "", "duration": m.get("duration") or "", "date": d["date"], "document": d["name"], "id": d["id"]}
        for d in reversed(_medical_documents(conn))
        for m in d["health"].get("medicines") or []
    ]
    return {"medicines": meds}


def health_followups(conn, today: str) -> dict[str, Any]:
    """Follow-up or next-appointment dates the documents state, from today on."""
    ups = sorted(
        (
            {"date": d["health"]["follow_up"], "document": d["name"], "title": d["title"], "id": d["id"]}
            for d in _medical_documents(conn)
            if d["health"].get("follow_up", "") and d["health"]["follow_up"] >= today
        ),
        key=lambda x: x["date"],
    )
    return {"follow_ups": ups}
