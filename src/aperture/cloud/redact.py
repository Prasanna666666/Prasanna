"""Hide the names from your library before a question leaves the Mac, and put them back in the answer.

"photos of Anna in Nagoya" is sent as "photos of <PERSON_1> in <PLACE_1>". The placeholders come back in the search plan and are replaced with the
real names here, on your Mac. The cloud never learns who or where.
"""

from __future__ import annotations

import re
from typing import Any


class Redactor:
    def __init__(self, people: list[str], places: list[str]) -> None:
        self._names = [(n.strip(), "PERSON") for n in people if len(n.strip()) >= 2] + [
            (n.strip(), "PLACE") for n in places if len(n.strip()) >= 3
        ]
        self._names.sort(key=lambda item: -len(item[0]))  # the longest name first: "New York" before "York"
        self.mapping: dict[str, str] = {}

    def redact(self, text: str) -> str:
        """Swap every library name in `text` for a placeholder, numbered in the order the names appear."""
        spans: list[tuple[int, int, str, str]] = []  # start, end, kind, canonical name
        taken: list[tuple[int, int]] = []
        for name, kind in self._names:  # the longest first, so "New York" wins over "York"
            for match in re.finditer(rf"(?<![\w<]){re.escape(name)}(?![\w>])", text, re.IGNORECASE):
                if any(match.start() < e and s < match.end() for s, e in taken):
                    continue
                taken.append((match.start(), match.end()))
                spans.append((match.start(), match.end(), kind, name.lower()))
        counters = {"PERSON": 0, "PLACE": 0}
        placeholders: dict[tuple[str, str], str] = {}
        out, last = [], 0
        for start, end, kind, canonical in sorted(spans):
            key = (kind, canonical)
            if key not in placeholders:
                counters[kind] += 1
                placeholders[key] = f"<{kind}_{counters[kind]}>"
            self.mapping.setdefault(placeholders[key], text[start:end])  # the name as the person typed it
            out += [text[last:start], placeholders[key]]
            last = end
        out.append(text[last:])
        return "".join(out)

    def restore(self, value: Any) -> Any:
        """Put the real names back into anything the cloud returned (strings, lists, dictionaries)."""
        if isinstance(value, str):
            for placeholder, original in self.mapping.items():
                value = value.replace(placeholder, original)
            return value
        if isinstance(value, list):
            return [self.restore(v) for v in value]
        if isinstance(value, dict):
            return {k: self.restore(v) for k, v in value.items()}
        return value
