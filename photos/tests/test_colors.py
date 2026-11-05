"""Colour search: measured once from the preview, matched by name."""

from __future__ import annotations

import pytest
from PIL import Image

from aperture.colors import color_clause, measure
from aperture.search.filters import Filters, apply_filters


@pytest.mark.parametrize(
    ("rgb", "name"),
    [
        ((220, 30, 30), "red"),
        ((30, 60, 220), "blue"),
        ((30, 180, 60), "green"),
        ((250, 220, 40), "yellow"),
        ((5, 5, 5), "black"),
        ((250, 250, 250), "white"),
        ((128, 128, 128), "gray"),
        ((110, 70, 30), "brown"),
        ((240, 130, 20), "orange"),
    ],
)
def test_solid_colours_are_named_correctly(tmp_path, rgb, name):
    import sqlite3

    hue, sat, val = measure(Image.new("RGB", (32, 32), rgb))
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE items(hue REAL, sat REAL, val REAL)")
    conn.execute("INSERT INTO items VALUES (?,?,?)", (hue, sat, val))
    matches = []
    for candidate in ("red", "orange", "yellow", "green", "teal", "blue", "purple", "pink", "brown", "black", "white", "gray"):
        clause, params = color_clause(candidate)
        if conn.execute(f"SELECT COUNT(*) FROM items WHERE {clause}", params).fetchone()[0]:
            matches.append(candidate)
    assert name in matches, (name, matches, hue, sat, val)


def test_filter_finds_only_photos_of_that_colour(scanned):
    ctx = scanned
    conn = ctx.db.connect()
    ids = [r[0] for r in conn.execute("SELECT id FROM items WHERE missing=0 ORDER BY id")]
    conn.execute("UPDATE items SET hue=220, sat=0.8, val=0.8")  # everything blue ...
    conn.execute("UPDATE items SET hue=0, sat=0.8, val=0.8 WHERE id=?", (ids[0],))  # ... except one red photo
    conn.commit()
    red, _ = apply_filters(conn, Filters(color="red"), None)
    blue, _ = apply_filters(conn, Filters(color="blue"), None)
    assert red.tolist() == [ids[0]]
    assert ids[0] not in blue.tolist() and len(blue) == len(ids) - 1
