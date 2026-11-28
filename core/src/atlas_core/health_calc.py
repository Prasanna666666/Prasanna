"""Exact Health summaries by code (Stage 5; G-021: the local model may read authorised Health data, but every figure it is given or may state is computed here, never by the model).

Values are `Decimal` (no float anywhere). Readings are grouped by (measure, unit) and never converted between units. Each reading says whether it was `measured` (by a device or the owner) or
`estimated`; a reading with no label is shown as `unlabelled`, never promoted to measured. An average is rounded half-up to two places and labelled as rounded. Nothing here gives medical advice,
diagnoses, or reaches a network.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from .records import Record
from .rules import load_rules

HEALTH_DOMAIN = next(
    name for name, schema in load_rules().raw["records"].items() if schema.get("numbers")
)  # the one domain whose records carry measured numbers: named by the policy data, not here
TWO_PLACES = Decimal("0.01")
BASES = ("measured", "estimated", "unlabelled")


def _plain(value: Decimal) -> str:
    """A decimal as plain digits, never in exponent form."""
    return format(value, "f")


def summarise(records: Iterable[Record]) -> list[dict[str, Any]]:
    """One entry per (measure, unit): how many readings, the latest, the exact minimum and maximum, the rounded average, and how many were measured, estimated or unlabelled."""
    groups: dict[tuple[str, str], list[tuple[str, Decimal, str]]] = defaultdict(list)
    for r in records:
        if r.domain != HEALTH_DOMAIN:
            continue
        groups[(r.fields["measure"], r.fields["unit"])].append((r.date, Decimal(r.fields["value"]), r.fields.get("basis", "unlabelled")))
    out = []
    for (measure, unit), rows in sorted(groups.items()):
        rows.sort(key=lambda row: row[0])
        values = [v for _d, v, _b in rows]
        mean = (sum(values, Decimal(0)) / len(values)).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
        date, value, basis = rows[-1]
        out.append(
            {
                "measure": measure,
                "unit": unit,
                "count": len(rows),
                "latest": {"date": date[:10], "value": _plain(value), "basis": basis},
                "minimum": _plain(min(values)),
                "maximum": _plain(max(values)),
                "average": _plain(mean),
                "average_is_rounded": True,
                "bases": {b: sum(1 for _d, _v, x in rows if x == b) for b in BASES},
            }
        )
    return out
