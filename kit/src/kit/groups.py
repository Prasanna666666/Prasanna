"""Union-find: put things that belong together into one group, however the links between them are found."""

from __future__ import annotations

from collections.abc import Hashable, Iterable
from typing import Generic, TypeVar

T = TypeVar("T", bound=Hashable)


class Groups(Generic[T]):
    """Start with every item alone; `join(a, b)` makes their groups one; `find(x)` names the group x is in."""

    def __init__(self, items: Iterable[T]) -> None:
        self._parent: dict[T, T] = {item: item for item in items}

    def find(self, item: T) -> T:
        while self._parent[item] != item:
            self._parent[item] = self._parent[self._parent[item]]
            item = self._parent[item]
        return item

    def join(self, a: T, b: T) -> None:
        self._parent[self.find(a)] = self.find(b)

    def same(self, a: T, b: T) -> bool:
        return self.find(a) == self.find(b)
