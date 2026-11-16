"""What a file is to an app, without the app fixing the words the model must use.

The model describes each file freely (`kind`: "Rekeningafschrift", "Bank statement (Dutch)", "payslip"). An app works with a few concepts of its own (declared in its own config: a name and
a plain description each). The model decides once, for each distinct kind, which concept it means; the answer is kept, and the app's code asks for the concept, never for a word the model
happened to use. A kind that is exactly a concept's name needs no model."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from . import extract

TABLE = "kind_concepts"
BATCH = 40
PROMPT = (
    "Each line below is a name that was given to a file, in some language or wording. For each one, say which of these concepts it means, or an empty string if it means none of them:\n"
    "{concepts}\nAnswer with every name unchanged and its concept, written exactly as it is in the list."
)
SCHEMA = {
    "type": "object",
    "properties": {
        "names": {
            "type": "array",
            "items": {"type": "object", "properties": {"given": {"type": "string"}, "concept": {"type": "string"}}, "required": ["given", "concept"]},
        }
    },
    "required": ["names"],
}
MIGRATION = f"CREATE TABLE IF NOT EXISTS {TABLE} (kind TEXT PRIMARY KEY, concept TEXT NOT NULL);"


def normal(kind: Any) -> str:
    return " ".join(str(kind or "").lower().replace("_", " ").split())


def concept_of(conn, concepts: dict[str, str], kind: Any) -> str:
    """The concept this kind of file means to the app, or '' (none, or not decided yet)."""
    key = normal(kind)
    if key in concepts:
        return key  # the kind is the concept's own name
    row = conn.execute(f"SELECT concept FROM {TABLE} WHERE kind=?", (key,)).fetchone()
    return row[0] if row else ""


def kinds_of(conn, concepts: dict[str, str], *wanted: str) -> list[str]:
    """Every kind (as the model wrote it, lower case) that means one of these concepts: for a query to ask for, instead of a fixed list of words."""
    marks = ",".join("?" for _ in wanted)
    found = {r[0] for r in conn.execute(f"SELECT kind FROM {TABLE} WHERE concept IN ({marks})", wanted)}
    return sorted(found | {w for w in wanted if w in concepts} | {w.replace(" ", "_") for w in wanted if w in concepts})


def resolve(conn, client, model: str, concepts: dict[str, str], kinds: Iterable[Any], control=None) -> int:
    """Decide, once each, which concept the kinds in `kinds` mean (the model answers; a name it makes up is not a concept and is read as none). Returns how many were decided."""
    done = {r[0] for r in conn.execute(f"SELECT kind FROM {TABLE}")}
    todo = sorted({normal(k) for k in kinds if normal(k)} - done - set(concepts))
    listed = "\n".join(f"- {name}: {about}" for name, about in concepts.items())
    decided = 0
    for i in range(0, len(todo), BATCH):
        if control is not None and control() == "stop":
            break
        batch = todo[i : i + BATCH]
        try:
            data = extract._ask(client, model, PROMPT.format(concepts=listed), "Names:\n" + "\n".join(batch), SCHEMA)
        except extract.Unclear:
            continue  # asked again next time: nothing is decided on a failure
        answered = {normal(n.get("given")): normal(n.get("concept")) for n in data.get("names", []) if isinstance(n, dict)}
        for kind in batch:
            concept = answered.get(kind, "")
            conn.execute(f"INSERT OR REPLACE INTO {TABLE} (kind, concept) VALUES (?,?)", (kind, concept if concept in concepts else ""))
            decided += 1
    conn.commit()
    return decided


class Concepts:
    """An app's concepts (its own config file: a name and a plain description each) and everything an app needs to work with them: what a kind of file means, a query condition, the model's one-time
    decision for new kinds, and giving each stored file its concept. Written once here: an app only declares what its concepts are."""

    def __init__(self, path) -> None:
        import json
        from pathlib import Path

        raw = json.loads(Path(path).read_text())
        self.items: dict[str, str] = {normal(k): str(v) for k, v in raw.items() if not k.startswith("_")}

    def __contains__(self, name: str) -> bool:
        return normal(name) in self.items

    def of(self, conn, kind: Any) -> str:
        return concept_of(conn, self.items, kind)

    def clause(self, *wanted: str, column: str = "concept", kind_column: str = "kind", negate: bool = False) -> tuple[str, tuple[str, ...]]:
        """A query condition and its values: the stored concept is one of these, or the kind is one of their own names (a file nobody has decided about yet). Only the app's own concepts can be
        asked for."""
        unknown = [w for w in wanted if w not in self.items]
        if unknown:
            raise KeyError(f"not a concept of this app: {unknown}")
        marks = ",".join("?" for _ in wanted)
        inside = f"({column} IN ({marks}) OR LOWER(REPLACE({kind_column}, '_', ' ')) IN ({marks}))"
        return (f"NOT {inside}" if negate else inside), (*wanted, *wanted)

    def resolve(self, conn, client, model: str, kinds: Iterable[Any], control=None) -> int:
        return resolve(conn, client, model, self.items, kinds, control) if client is not None and model else 0

    def refresh(self, conn, table: str, kind_column: str = "kind", concept_column: str = "concept") -> None:
        """Every stored file gets the concept its kind means (a kind that is a concept's own name needs no decision)."""
        for (kind,) in conn.execute(f"SELECT DISTINCT {kind_column} FROM {table}").fetchall():
            conn.execute(f"UPDATE {table} SET {concept_column}=? WHERE {kind_column}=?", (self.of(conn, kind), kind))
        conn.commit()
