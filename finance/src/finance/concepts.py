"""What Finance means by the kinds of file it works with: its concepts are in concepts.json; everything else is the shared `kit.concepts`."""

from __future__ import annotations

from pathlib import Path

from kit.concepts import MIGRATION, Concepts

C = Concepts(Path(__file__).with_name("concepts.json"))
CONCEPTS = C.items
clause = C.clause
of = C.of
__all__ = ["CONCEPTS", "MIGRATION", "clause", "of", "resolve"]


def resolve(conn, client, model, control=None) -> int:
    """Decide which concept each kind of file in Finance means (the model answers once per kind), then give every file its concept."""
    decided = C.resolve(conn, client, model, [r[0] for r in conn.execute("SELECT DISTINCT kind FROM finance_docs")], control)
    C.refresh(conn, "finance_docs")
    return decided
