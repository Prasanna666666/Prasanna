"""Browsing the library as a website: by date, trips, places and people. Real database and server, invented photos."""

import json
import urllib.error
import urllib.request

import pytest

from aperture.web import browse
from web_fixture import make_ctx, start_server


@pytest.fixture
def lib(tmp_path):
    ctx, _agent, ids = make_ctx(tmp_path)
    conn = ctx.db.connect()
    yield ctx, conn, ids
    conn.close()


def test_the_library_is_newest_first_a_page_at_a_time_with_the_whole_total(lib):
    _ctx, conn, ids = lib
    first = browse.library(conn, {}, 0, 30)
    assert first["total"] == len(ids) and len(first["ids"]) == 30 and first["more"] is True
    second = browse.library(conn, {}, 30, 30)
    assert set(first["ids"]).isdisjoint(second["ids"]) and browse.library(conn, {}, 60, 30)["more"] is False
    days = [conn.execute("SELECT taken_at FROM items WHERE id=?", (i,)).fetchone()[0] for i in first["ids"]]
    assert days == sorted(days, reverse=True)


def test_the_library_can_be_narrowed_by_year_month_range_place_and_person(lib):
    _ctx, conn, ids = lib
    months = {r[0]: r[1] for r in conn.execute("SELECT substr(taken_at,1,7), COUNT(*) FROM items GROUP BY 1")}
    assert browse.library(conn, {"year": "2025"})["total"] == len(ids) and browse.library(conn, {"year": "2024"})["total"] == 0
    m = next(iter(months))
    assert browse.library(conn, {"month": m})["total"] == months[m]
    only = browse.library(conn, {"from": "2025-03-01", "to": "2025-03-31"})
    assert only["total"] == months["2025-03"]
    goa = browse.library(conn, {"place": "Goa, India"})
    assert goa["total"] == conn.execute("SELECT COUNT(*) FROM items WHERE place='Goa, India'").fetchone()[0] > 0
    conn.execute("INSERT INTO people(id, name) VALUES (1, 'Amma')")
    for item in ids[:5]:
        conn.execute(
            "INSERT INTO faces(item_id, x1, y1, x2, y2, score, emb, person_id) VALUES (?,?,?,?,?,?,?,1)",
            (item, 0.2, 0.2, 0.6, 0.6, 0.9, b"\x00" * 8),
        )
    conn.commit()
    assert browse.library(conn, {"person": "1"})["total"] == 5
    assert browse.library(conn, {"year": "20x5; DROP TABLE items"})["total"] == len(
        ids
    )  # anything that is not a year is ignored, never run


def test_missing_and_unread_photos_are_never_listed(lib):
    _ctx, conn, ids = lib
    conn.execute("UPDATE items SET missing=1 WHERE id=?", (ids[0],))
    conn.execute("UPDATE items SET meta_done=0 WHERE id=?", (ids[1],))
    conn.commit()
    r = browse.library(conn, {}, 0, 200)
    assert ids[0] not in r["ids"] and ids[1] not in r["ids"] and r["total"] == len(ids) - 2


def test_the_timeline_counts_years_and_months(lib):
    _ctx, conn, ids = lib
    t = browse.timeline(conn)
    assert t["total"] == len(ids) and t["years"][0]["year"] == "2025" and t["years"][0]["total"] == len(ids)
    assert sum(m["n"] for m in t["years"][0]["months"]) == len(ids)
    assert [m["month"] for m in t["years"][0]["months"]] == sorted((m["month"] for m in t["years"][0]["months"]), reverse=True)


def test_places_are_counted_with_a_picture_and_busiest_first(lib):
    _ctx, conn, ids = lib
    p = browse.places(conn)
    assert [x["n"] for x in p] == sorted((x["n"] for x in p), reverse=True) and {x["place"] for x in p} == {
        "Goa, India",
        "Bengaluru, India",
        "Eindhoven, Netherlands",
        "Lisbon, Portugal",
    }
    assert next(x for x in p if x["place"] == "Lisbon, Portugal")["country"] == "Portugal" and all(x["cover"] in ids for x in p)


def test_trips_come_from_events_or_from_photos_taken_close_together(lib):
    _ctx, conn, ids = lib
    assert browse.trips(conn)  # no events yet: made from runs of photos
    conn.execute(
        "INSERT INTO events(id, start, stop, n, place, country) VALUES (1, '2025-03-01 09:00:00', '2025-03-04 18:00:00', 12, 'Lisbon, Portugal', 'Portugal')"
    )
    for item in ids[:12]:
        conn.execute("INSERT INTO photo_events(item_id, event_id) VALUES (?,1)", (item,))
    conn.commit()
    t = browse.trips(conn)
    assert t == [
        {
            "title": "Lisbon, Portugal",
            "place": "Lisbon, Portugal",
            "start": "2025-03-01",
            "stop": "2025-03-04",
            "n": 12,
            "cover": ids[0],
        }
    ]


def test_people_have_their_clearest_face_and_hidden_or_photo_less_people_are_left_out(lib):
    _ctx, conn, ids = lib
    conn.executemany(
        "INSERT INTO people(id, name, hidden) VALUES (?,?,?)", [(1, "Amma", 0), (2, None, 0), (3, "Hidden", 1), (4, "Nobody", 0)]
    )
    for pid, items, score in ((1, ids[:6], 0.8), (2, ids[6:8], 0.7), (3, ids[8:10], 0.9)):
        for item in items:
            conn.execute(
                "INSERT INTO faces(item_id, x1, y1, x2, y2, score, emb, person_id) VALUES (?,?,?,?,?,?,?,?)",
                (item, 0.1, 0.1, 0.5, 0.5, score, b"\x00" * 8, pid),
            )
    conn.execute("UPDATE faces SET score=0.99 WHERE item_id=? AND person_id=1", (ids[3],))
    conn.commit()
    p = browse.people(conn)
    assert (
        [x["id"] for x in p] == [1, 2]
        and p[0]["n"] == 6
        and p[0]["cover"] == ids[3]
        and p[0]["name"] == "Amma"
        and p[1]["name"] == ""
    )


class Client:
    def __init__(self, web, server):
        self.web, self.base = web, f"http://127.0.0.1:{server.server_port}"

    def get(self, path, token=True):
        req = urllib.request.Request(self.base + path, headers={"X-Lumo-Token": self.web.token} if token else {})
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, None


def test_the_browse_endpoints_need_the_token_and_answer_with_the_same_data(tmp_path):
    ctx, _agent, ids = make_ctx(tmp_path)
    web, server = start_server(ctx)
    try:
        c = Client(web, server)
        for path in ("/api/library", "/api/timeline", "/api/trips", "/api/places", "/api/people"):
            assert c.get(path, token=False)[0] == 403  # not without the token
            assert c.get(path)[0] == 200
        status, body = c.get("/api/library?year=2025&offset=60")
        assert status == 200 and body["total"] == len(ids) and len(body["ids"]) == 10 and body["more"] is False
        assert c.get("/api/library?offset=abc")[1]["offset"] == 0  # a bad offset is just zero
        assert c.get("/api/places")[1][0]["n"] > 0
    finally:
        server.shutdown()


def test_serve_binds_loopback_unless_sandboxed(monkeypatch):
    import inspect

    from aperture.web import server

    src = inspect.getsource(server.serve)
    assert '"127.0.0.1"' in src and "APERTURE_SANDBOXED" in src


def test_search_finds_places_people_and_trips_with_where_each_opens():
    places = [{"place": "Goa, India", "n": 14}, {"place": "Lisbon, Portugal", "n": 8}]
    people = [{"id": 3, "name": "Asha", "n": 20}, {"id": 4, "name": "", "n": 5}]
    trips = [{"title": "Lisbon", "place": "Lisbon, Portugal", "start": "2025-03-02", "stop": "2025-03-09", "n": 14}]
    found = browse.search_links(places, people, trips, "lis")
    assert [r["kind"] for r in found] == ["place", "trip"] and found[0]["link"] == "#/library?place=Lisbon%2C%20Portugal"
    assert found[1]["link"] == "#/library?from=2025-03-02&to=2025-03-09"
    assert browse.search_links(places, people, trips, "asha")[0]["link"] == "#/library?person=3"
    assert browse.search_links(places, people, trips, "l") == []  # too short


def test_the_front_door_search_is_answered_by_the_server(tmp_path):
    ctx, _agent, _ids = make_ctx(tmp_path)
    web, server = start_server(ctx)
    port = server.server_address[1]
    req = urllib.request.Request(f"http://127.0.0.1:{port}/api/search?q=goa", headers={"X-Lumo-Token": web.token})
    with urllib.request.urlopen(req) as r:
        results = json.loads(r.read())["results"]
    assert results and results[0]["kind"] == "place"
    server.shutdown()


def test_one_update_button_can_start_and_follow_the_indexing(tmp_path, monkeypatch):
    ctx, _agent, _ids = make_ctx(tmp_path)
    web, server = start_server(ctx)
    started: list[list[str]] = []
    monkeypatch.setattr("aperture.web.server.subprocess.Popen", lambda cmd, **kw: started.append(cmd))
    port = server.server_address[1]

    def call(method, path):
        req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", method=method, headers={"X-Lumo-Token": web.token})
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read())

    status = call("GET", "/api/scan")
    assert set(status) == {"running", "progress", "summary", "problems", "needs_check"} and status["running"] is False
    assert call("POST", "/api/scan") == {"started": True} and started and started[0][-1] == "scan"
    server.shutdown()


def test_the_one_assistant_lists_and_runs_the_photo_search_tool(tmp_path):
    ctx, _agent, _ids = make_ctx(tmp_path)
    web, server = start_server(ctx)
    port = server.server_address[1]

    def call(method, path, body=None):
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}{path}",
            data=json.dumps(body).encode() if body is not None else None,
            method=method,
            headers={"X-Lumo-Token": web.token, "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read())

    [tool] = call("GET", "/api/tools")["tools"]
    assert tool["name"] == "find_photos" and tool["parameters"]["required"] == ["request"]
    found = call("POST", "/api/tool", {"name": "find_photos", "args": {"request": "photos from the beach", "show": True}})
    assert found["ok"] and found["data"]["count"] == 41 and found["data"]["answer"].startswith("I found **41 photos**")
    assert (
        len(found["items"]) == 24
        and found["items"][0]["kind"] == "photo"
        and found["items"][0]["thumb"].startswith("/api/photo/")
    )
    quiet = call("POST", "/api/tool", {"name": "find_photos", "args": {"request": "photos from the beach"}})
    assert quiet["ok"] and quiet["items"] == [] and quiet["data"]["count"] == 41  # shown only when asked for
    assert call("POST", "/api/tool", {"name": "find_photos", "args": {}})["ok"] is False
    assert call("POST", "/api/tool", {"name": "other", "args": {"request": "x"}})["ok"] is False
    server.shutdown()
