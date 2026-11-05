"""Pure pagination maths (no UI imports, fully unit-tested).

Aperture never truncates a result set.  A query that matches 40,000 photos
keeps all 40,000 ids in memory (a few hundred kilobytes) and only the ids of
the *current page* are turned into thumbnails.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class Page:
    number: int  # 1-based, always valid
    size: int
    total: int  # total number of items
    pages: int  # total number of pages (>= 1)

    @property
    def start(self) -> int:
        return (self.number - 1) * self.size

    @property
    def end(self) -> int:
        return min(self.start + self.size, self.total)

    @property
    def has_prev(self) -> bool:
        return self.number > 1

    @property
    def has_next(self) -> bool:
        return self.number < self.pages

    @property
    def label(self) -> str:
        if self.total == 0:
            return "0 photos"
        return f"{self.start + 1:,}-{self.end:,} of {self.total:,}"


def make_page(total: int, size: int, number: int) -> Page:
    """Build a valid :class:`Page`, clamping nonsense input instead of raising."""
    size = max(1, int(size))
    total = max(0, int(total))
    pages = max(1, -(-total // size))
    return Page(number=min(max(1, int(number)), pages), size=size, total=total, pages=pages)


def page_slice(items: Sequence[T], page: Page) -> Sequence[T]:
    return items[page.start : page.end]


def page_window(page: Page, radius: int = 2) -> list[int | None]:
    """Page numbers to show in a selector; ``None`` marks an ellipsis.

    ``1 ... 7 8 [9] 10 11 ... 40``"""
    wanted = {1, page.pages}
    wanted.update(range(max(1, page.number - radius), min(page.pages, page.number + radius) + 1))
    out: list[int | None] = []
    previous = 0
    for n in sorted(wanted):
        if n - previous > 1:
            out.append(None)
        out.append(n)
        previous = n
    return out
