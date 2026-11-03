"""Register new features here. Add a module file, append it to ALL - the UI chat and tools pick it up.

Rule: no module may use the network. The egress guard (netguard.py) enforces this at run time and
tests/test_privacy.py checks it at build time.
"""

from ..module import Module, Tool
from . import clock, money, notes, people, tasks
from .today import MODULE as today

ALL: list[Module] = [people.MODULE, tasks.MODULE, notes.MODULE, money.MODULE, clock.MODULE, today]


def tools(modules: list[Module] | None = None) -> dict[str, Tool]:
    return {t.name: t for m in (modules or ALL) for t in m.tools}
