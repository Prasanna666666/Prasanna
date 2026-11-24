"""The check that a figure in an answer was really returned by a tool.

Figures are compared as exact signed decimals: no float, no rounding tolerance and no absolute value, so 1250.49 does not prove 1250.50 (or 1250.5, or 1,250), and -250.00 does not prove 250.00. A figure
a tool returned only in accounting brackets, `(250.00)`, proves the negative value and nothing else. Dates and years are ignored.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

_MINUS = "-−"  # hyphen-minus and the Unicode minus sign
_NUM = re.compile(rf"(?<![\w.])(?P<sign>[{_MINUS}])?(?P<num>\d{{1,3}}(?:,\d{{3}})+(?:\.\d+)?|\d+\.\d+|\d{{3,}})")
_TOOL_NUM = re.compile(rf"(?<![\w.])(?P<open>\()?(?P<sign>[{_MINUS}])?(?P<num>\d+(?:\.\d+)?)(?P<close>\))?")


def _signed(sign: str | None, num: str) -> Decimal | None:
    try:
        value = Decimal(num.replace(",", ""))
    except InvalidOperation:
        return None
    return -value if sign else value


def _numbers(text: str) -> list[Decimal]:
    found = (_signed(m.group("sign"), m.group("num")) for m in _NUM.finditer(text))
    return [v for v in found if v is not None]


def _proven(outputs: list[str]) -> set[Decimal]:
    seen: set[Decimal] = set()
    for out in outputs:
        for m in _TOOL_NUM.finditer(out):
            value = _signed(m.group("sign") or (m.group("open") and m.group("close") and "-"), m.group("num"))
            if value is not None:
                seen.add(value)
    return seen


def unproven_figures(reply: str, tool_outputs: list[str]) -> list[float]:
    """Figures in the agent's reply (amounts with decimals or thousands, and any number of 3+ digits) that no tool returned, exactly and with the same sign. Dates and years are ignored.
    Empty if the agent used no tool: it then states no data of yours."""
    if not tool_outputs:
        return []
    seen = _proven(tool_outputs)
    text = re.sub(r"\b(?:19|20)\d{2}(?:-\d{2}){0,2}\b", " ", reply)
    return sorted({float(n) for n in _numbers(text) if n not in seen})
