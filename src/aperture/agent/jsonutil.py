"""Tolerant JSON extraction for LLM output.

Even with schema-constrained decoding, models sometimes wrap JSON in markdown
fences, add chatter, use smart quotes, leave trailing commas or get cut off
mid-object.  :func:`extract_json` handles all of that and raises a single,
well-defined :class:`JSONExtractError` when nothing usable is there.
"""

from __future__ import annotations

import json
import re
from typing import Any

_FENCE = re.compile(r"```[a-zA-Z0-9_-]*\s*(.*?)```", re.DOTALL)
_TRAILING_COMMA = re.compile(r",\s*([}\]])")
_SMART_QUOTES = str.maketrans({"“": '"', "”": '"', "‘": "'", "’": "'"})
_PY_LITERALS = ((re.compile(r"\bTrue\b"), "true"), (re.compile(r"\bFalse\b"), "false"), (re.compile(r"\bNone\b"), "null"))


class JSONExtractError(ValueError):
    """No valid JSON object could be recovered from the text."""


def _balanced_slice(text: str, start: int) -> str:
    """From ``start`` (an opening brace/bracket) to its match - or to the end,
    with missing closers appended, when the text was truncated."""
    stack: list[str] = []
    in_string = escaped = False
    for pos in range(start, len(text)):
        ch = text[pos]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch in "{[":
            stack.append("}" if ch == "{" else "]")
        elif ch in "}]":
            if stack:
                stack.pop()
            if not stack:
                return text[start : pos + 1]
    tail = '"' if in_string else ""
    return text[start:] + tail + "".join(reversed(stack))


def _repair(candidate: str) -> str:
    candidate = candidate.translate(_SMART_QUOTES)
    for pattern, replacement in _PY_LITERALS:
        candidate = pattern.sub(replacement, candidate)
    return _TRAILING_COMMA.sub(r"\1", candidate)


def extract_json(text: str) -> Any:
    """Return the first JSON object/array found in ``text``."""
    if not isinstance(text, str) or not text.strip():
        raise JSONExtractError("empty response")
    cleaned = text.lstrip("﻿").strip()
    fenced = _FENCE.search(cleaned)
    haystacks = [fenced.group(1)] if fenced else []
    haystacks.append(cleaned)
    for hay in haystacks:
        for match in re.finditer(r"[{\[]", hay):
            candidate = _balanced_slice(hay, match.start())
            for attempt in (candidate, _repair(candidate)):
                try:
                    return json.loads(attempt)
                except ValueError:
                    continue
            break  # first brace failed even after repair; try the next haystack
    raise JSONExtractError("no valid JSON found in the model response")
