"""A payslip (loonstrook / salarisspecificatie) as a few facts. The local model reads the file (see extract.classify); this checks its answer."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Payslip:
    period: str  # YYYY-MM, or '' if not found
    gross_minor: int
    net_minor: int
    tax_minor: int | None = None
    pension_minor: int | None = None
    holiday_minor: int | None = None


def from_model(info: dict) -> Payslip | None:
    """A payslip from the model's reading, after every amount was verified against the document. Gross and net must both be present and net cannot exceed gross."""
    def minor(key: str) -> int | None:
        v = info.get(key)
        return round(abs(float(v)) * 100) if isinstance(v, (int, float)) and not isinstance(v, bool) and v else None

    gross, net = minor("gross"), minor("net")
    if not gross or not net or net > gross:
        return None
    period = str(info.get("period") or "")
    return Payslip(period if re.fullmatch(r"20\d{2}-(0[1-9]|1[0-2])", period) else "", gross, net, minor("tax"), minor("pension"), minor("holiday_pay"))
