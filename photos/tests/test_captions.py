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


def test_caption_all_is_resumable_and_makes_text_searchable(scanned):
    from images.search.text import search_text_ids

    from aperture.agent.captions import caption_all

    ctx = scanned
    conn = ctx.db.connect()
    vision = FakeVision()
    total = conn.execute("SELECT COUNT(*) FROM items WHERE missing=0 AND kind='image' AND preview IS NOT NULL").fetchone()[0]
    described, failed = caption_all(conn, ctx.paths, vision, "fake", limit=2)
    assert (described, failed) == (2, 0)
    described, failed = caption_all(conn, ctx.paths, vision, "fake")
    assert described == total - 2  # the first two were skipped: resumable
    assert len(search_text_ids(conn, "blue square")) == total  # captions are searchable text


def test_caption_all_gives_up_when_the_model_is_missing(scanned):
    from aperture.agent.captions import caption_all
    from aperture.agent.llm import LLMError

    class Broken:
        def describe(self, image, question=""):
            raise LLMError("model not installed")

    ctx = scanned
    conn = ctx.db.connect()
    described, failed = caption_all(conn, ctx.paths, Broken(), "x")
    assert described == 0 and failed == 5  # stopped after five failures in a row
