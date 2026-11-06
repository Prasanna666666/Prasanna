"""The best few pictures: measured, spread over days and places, never a screenshot, never the same moment twice."""

from __future__ import annotations

from images.browse import highlights


def _set(conn, item_id, **v):
    conn.execute(
        "UPDATE items SET width=?, height=?, size=?, taken_at=?, place=?, ocr_chars=?, thumb='t', meta_done=1, missing=0 WHERE id=?",
        (v.get("w", 4000), v.get("h", 3000), v.get("size", 4_000_000), v.get("at"), v.get("place"), v.get("text", 0), item_id),
    )


def test_highlights_skip_screenshots_small_pictures_and_the_same_moment(scanned):
    conn = scanned.db.connect()
    ids = [r[0] for r in conn.execute("SELECT id FROM items WHERE missing=0 ORDER BY id")]
    assert len(ids) >= 5
    _set(conn, ids[0], at="2025-05-01 10:00:00", place="Goa, India")  # a good picture
    _set(
        conn, ids[1], at="2025-05-01 10:00:30", place="Goa, India", size=2_000_000
    )  # 30 seconds later: the same moment, and softer
    _set(conn, ids[2], at="2025-05-02 09:00:00", place="Goa, India", text=900)  # full of text: a screenshot or a letter
    _set(conn, ids[3], at="2025-05-03 09:00:00", w=300, h=200, size=20_000)  # tiny
    _set(conn, ids[4], at="2025-05-04 09:00:00", place="Utrecht, Netherlands")
    conn.commit()
    got = highlights(conn, limit=12)["ids"]
    assert ids[0] in got and ids[4] in got
    assert ids[1] not in got and ids[2] not in got and ids[3] not in got


def test_highlights_are_spread_over_days_and_places(scanned):
    conn = scanned.db.connect()
    ids = [r[0] for r in conn.execute("SELECT id FROM items WHERE missing=0 ORDER BY id")]
    for n, item_id in enumerate(ids):  # every picture on the same day in the same place, an hour apart
        _set(conn, item_id, at=f"2025-05-01 {8 + n:02d}:00:00", place="Goa, India")
    conn.commit()
    assert len(highlights(conn, limit=12)["ids"]) == 2  # at most two a day
