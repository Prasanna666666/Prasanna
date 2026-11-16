"""What the Travel part of Documents means by the kinds of file it shows: its concepts are in concepts.json; everything else is the shared `kit.concepts`."""

from __future__ import annotations

from pathlib import Path

from kit.concepts import MIGRATION, Concepts

C = Concepts(Path(__file__).with_name("concepts.json"))
CONCEPTS = C.items
of = C.of
__all__ = ["CONCEPTS", "MIGRATION", "of", "resolve"]


def resolve(conn, client, model, control=None) -> int:
    """Decide which concept each plain name of a kind means (the model answers once per name)."""
    kinds = [r[0] for r in conn.execute("SELECT DISTINCT name FROM kind_names")]
    return C.resolve(conn, client, model, kinds, control)
