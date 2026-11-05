import json


def test_the_hub_page_and_its_menu_are_served_under_one_name(running):
    status, headers, body = running.shell("/")
    assert status == 200 and b"<title>" in body
    assert "frame-src http://*.home.localhost:" in headers["content-security-policy"] and "frame-ancestors 'none'" in headers["content-security-policy"]
    modules = running.json("/_hub/api/modules")["modules"]
    assert [m["id"] for m in modules] == ["money", "photos"]
    assert all("upstream" not in m for m in modules)


def test_unknown_names_and_ports_are_refused_and_plain_addresses_are_sent_to_the_one_name(running):
    assert running.request("GET", "/", "evil.example")[0] == 421
    assert running.request("GET", "/", f"home.localhost.evil.example:{running.port}")[0] == 421
    assert running.request("GET", "/", f"nothing.home.localhost:{running.port}")[0] == 421
    assert running.request("GET", "/", "home.localhost:1")[0] == 421  # a different port is a different site
    status, headers, _ = running.request("GET", "/x", f"127.0.0.1:{running.port}")
    assert status == 302 and headers["location"] == f"http://home.localhost:{running.port}/x"


def test_the_hub_page_is_read_only_and_only_serves_its_own_files(running):
    assert running.request("POST", "/_hub/api/search", f"home.localhost:{running.port}", b"{}")[0] == 405
    assert running.shell("/_hub/static/hub.css")[0] == 200
    assert running.shell("/_hub/static/../server.py")[0] == 404
    assert running.shell("/_hub/static/server.py")[0] == 404


def test_health_says_which_apps_are_up(running):
    health = running.json("/_hub/api/health")
    assert health["money"]["up"] and health["photos"]["up"]
    running.apps["money"].close()
    import time

    time.sleep(0.01)
    assert not running.hub.upstreams._check(running.hub.modules["money"])["up"]


def test_search_asks_every_searchable_app_with_its_own_token_and_ignores_junk(running):
    found = running.json("/_hub/api/search?q=lisbon")["results"]
    assert found == [{"module": "photos", "title": "Lisbon", "subtitle": "14 photos", "kind": "place", "link": "#/library?place=Lisbon"}]
    assert any(s["token"] == "secret" for s in running.apps["photos"].seen)  # the hub read the token from the app's own page
    assert running.json("/_hub/api/search?q=x")["results"] == []  # too short to search


def test_search_survives_the_app_restarting_with_a_new_token(running):
    running.json("/_hub/api/search?q=lisbon")
    running.apps["photos"].token = "new-secret"
    assert running.json("/_hub/api/search?q=lisbon")["results"][0]["title"] == "Lisbon"


def test_an_app_that_is_down_adds_nothing_to_search_and_shows_a_plain_page(running):
    running.apps["photos"].close()
    assert running.json("/_hub/api/search?q=lisbon")["results"] == []
    status, _, body = running.request("GET", "/", f"photos.home.localhost:{running.port}")
    assert status == 502 and b"is not running" in body
    json.dumps(running.json("/_hub/api/modules"))
