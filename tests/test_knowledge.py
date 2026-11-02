"""Questions about the library are answered from real facts, in the same chat."""

from __future__ import annotations

from datetime import date

from aperture.agent.knowledge import answer, gather_facts
from aperture.agent.planner import Planner
from aperture.agent.service import AgentService


def test_facts_contain_real_numbers_and_move_state(scanned):
    ctx = scanned
    conn = ctx.db.connect()
    total = conn.execute("SELECT COUNT(*) FROM items WHERE missing=0").fetchone()[0]
    facts = gather_facts(conn, ctx.paths, None)
    assert f"{total:,} files" in facts
    assert "Moves: nothing has been moved yet." in facts
    assert "No scan is running right now." in facts
    ids = conn.execute("SELECT id FROM items WHERE missing=0 LIMIT 3").fetchall()
    import numpy as np

    facts = gather_facts(conn, ctx.paths, np.array([r[0] for r in ids]))
    assert "previous answer: 3." in facts


def test_answer_passes_facts_and_question_to_the_model():
    seen = {}

    def fake(system: str, user: str) -> str:
        seen["user"] = user
        return " Yes, it is done. "

    assert answer(fake, "is the move finished?", "FACTS:\nx") == "Yes, it is done."
    assert "FACTS:\nx" in seen["user"] and "is the move finished?" in seen["user"]
    assert answer(lambda s, u: "  ", "q", "f").startswith("I could not")


def test_chat_routes_a_question_to_text_not_photos():
    import json

    class Scripted:
        def complete_json(self, system, user, schema):
            return json.dumps({"intent": "question", "clauses": []})

    service = AgentService(
        Planner(Scripted()),
        lambda: None,  # never used for a question
        lambda: [],
        today=lambda: date(2026, 11, 2),
        answerer=lambda q, prev: f"answer to: {q}",
    )
    reply = service.ask("did the move finish?")
    assert reply.kind == "chat" and reply.text == "answer to: did the move finish?"
    assert len(reply.ids) == 0
