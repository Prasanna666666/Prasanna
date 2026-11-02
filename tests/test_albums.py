"""Albums are runs of photos close in time; places are counted."""

from __future__ import annotations

from aperture.albums import build_albums, places_summary


def test_albums_split_on_long_gaps_and_skip_small_runs(scanned):
    ctx = scanned
    conn = ctx.db.connect()
    ids = [r[0] for r in conn.execute("SELECT id FROM items WHERE missing=0 ORDER BY id")]
    assert len(ids) >= 5
    # first three: a short run on day 1; the rest: a run on day 3, one hour apart
    for i, item_id in enumerate(ids):
        taken = f"2025-05-01 10:{i:02d}:00" if i < 3 else f"2025-05-03 1{i % 10}:00:00"
        conn.execute("UPDATE items SET taken_at=?, place='Utrecht, The Netherlands' WHERE id=?", (taken, item_id))
    conn.commit()
    albums = build_albums(conn, gap_hours=10, min_photos=2)
    assert [len(a) for a in albums] == [len(ids) - 3, 3]  # newest first
    assert albums[0].title.startswith("Utrecht - 2025-05-03")
    assert build_albums(conn, gap_hours=10, min_photos=100) == []


def test_places_summary_counts(scanned):
    conn = scanned.db.connect()
    ids = [r[0] for r in conn.execute("SELECT id FROM items WHERE missing=0 ORDER BY id")]
    conn.execute("UPDATE items SET place='Enschede, The Netherlands' WHERE id IN (?,?)", (ids[0], ids[1]))
    conn.execute("UPDATE items SET place='Zürich, Switzerland' WHERE id=?", (ids[2],))
    conn.commit()
    assert places_summary(conn)[:2] == [("Enschede, The Netherlands", 2), ("Zürich, Switzerland", 1)]
