"""The check that a figure in an answer was really returned by a tool."""

from __future__ import annotations

import re

_NUM = re.compile(r"(?<![\w.])\d{1,3}(?:,\d{3})+(?:\.\d+)?|(?<![\w.])\d+\.\d+|(?<![\w.])\d{3,}")


def _numbers(text: str) -> set[float]:
    return {float(m.replace(",", "")) for m in _NUM.findall(text)}


def unproven_figures(reply: str, tool_outputs: list[str]) -> list[float]:
    """Figures in the agent's reply (amounts with decimals or thousands, and any number of 3+ digits) that no tool returned. Dates and years are ignored.
    A figure counts as proven if a tool returned it, or its rounded or whole-number form. Empty if the agent used no tool: it then states no data of yours."""
    if not tool_outputs:
        return []
    seen: set[float] = set()
    for out in tool_outputs:
        for v in re.findall(r"-?\d+(?:\.\d+)?", out):
            x = abs(float(v))
            seen |= {x, round(x), round(x, 1), round(x, 2)}
    text = re.sub(r"\b(?:19|20)\d{2}(?:-\d{2}){0,2}\b", " ", reply)
    return sorted(n for n in _numbers(text) if n not in seen and round(n) not in seen)
