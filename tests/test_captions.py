"""Describing one photo: remembered, and never crashes without a preview."""

from __future__ import annotations

import pytest

from aperture.agent.captions import NoPreview, cached_caption, describe_item


class FakeVision:
    def __init__(self):
        self.calls = []

    def describe(self, image: bytes, question: str = "") -> str:
        self.calls.append((len(image), question))
        return "A blue square." if not question else f"answer: {question}"


def test_description_is_remembered_but_questions_are_not(scanned):
    ctx = scanned
    conn = ctx.db.connect()
    item_id = conn.execute("SELECT id FROM items WHERE missing=0 AND preview IS NOT NULL LIMIT 1").fetchone()[0]
    vision = FakeVision()
    assert describe_item(conn, ctx.paths, vision, "fake", item_id) == "A blue square."
    assert describe_item(conn, ctx.paths, vision, "fake", item_id) == "A blue square."
    assert len(vision.calls) == 1  # second time came from the database
    assert cached_caption(conn, item_id) == "A blue square."
    assert describe_item(conn, ctx.paths, vision, "fake", item_id, "what colour?") == "answer: what colour?"
    assert len(vision.calls) == 2


def test_no_preview_is_a_clear_error(scanned):
    ctx = scanned
    conn = ctx.db.connect()
    item_id = conn.execute("SELECT id FROM items WHERE missing=0 LIMIT 1").fetchone()[0]
    conn.execute("UPDATE items SET preview=NULL, thumb=NULL WHERE id=?", (item_id,))
    conn.commit()
    with pytest.raises(NoPreview):
        describe_item(conn, ctx.paths, FakeVision(), "fake", item_id)


def test_needs_to_see_is_false_when_the_ai_is_unreachable(scanned):
    ctx = scanned
    ctx.settings.ollama_url = "http://127.0.0.1:9"  # nothing listens here
    assert ctx.needs_to_see("what colour is the shirt?") is False
