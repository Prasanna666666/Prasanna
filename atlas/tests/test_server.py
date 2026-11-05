import json


def test_the_hub_page_and_its_menu_are_served_under_one_name(running):
    status, headers, body = running.shell("/")
    assert status == 200 and b"<title>" in body
    assert "frame-src http://*.atlas.localhost:" in headers["content-security-policy"] and "frame-ancestors 'none'" in headers["content-security-policy"]
    modules = running.json("/_atlas/api/modules")["modules"]
    assert [m["id"] for m in modules] == ["money", "photos"]
    assert all("upstream" not in m for m in modules)


def test_unknown_names_and_ports_are_refused_and_plain_addresses_are_sent_to_the_one_name(running):
    assert running.request("GET", "/", "evil.example")[0] == 421
    assert running.request("GET", "/", f"atlas.localhost.evil.example:{running.port}")[0] == 421
    assert running.request("GET", "/", f"nothing.atlas.localhost:{running.port}")[0] == 421
    assert running.request("GET", "/", "atlas.localhost:1")[0] == 421  # a different port is a different site
    status, headers, _ = running.request("GET", "/x", f"127.0.0.1:{running.port}")
    assert status == 302 and headers["location"] == f"http://atlas.localhost:{running.port}/x"


def test_the_hub_page_is_read_only_and_only_serves_its_own_files(running):
    assert running.request("POST", "/_atlas/api/search", f"atlas.localhost:{running.port}", b"{}")[0] == 405
    assert running.shell("/_atlas/static/atlas.css")[0] == 200
    assert running.shell("/_atlas/static/../server.py")[0] == 404
    assert running.shell("/_atlas/static/server.py")[0] == 404


def test_health_says_which_apps_are_up(running):
    health = running.json("/_atlas/api/health")
    assert health["money"]["up"] and health["photos"]["up"]
    running.apps["money"].close()
    import time

    time.sleep(0.01)
    assert not running.atlas.upstreams._check(running.atlas.modules["money"])["up"]


def test_search_asks_every_searchable_app_with_its_own_token_and_ignores_junk(running):
    found = running.json("/_atlas/api/search?q=lisbon")["results"]
    assert found == [{"module": "photos", "title": "Lisbon", "subtitle": "14 photos", "kind": "place", "link": "#/library?place=Lisbon"}]
    assert any(s["token"] == "secret" for s in running.apps["photos"].seen)  # the atlas read the token from the app's own page
    assert running.json("/_atlas/api/search?q=x")["results"] == []  # too short to search


def test_search_survives_the_app_restarting_with_a_new_token(running):
    running.json("/_atlas/api/search?q=lisbon")
    running.apps["photos"].token = "new-secret"
    assert running.json("/_atlas/api/search?q=lisbon")["results"][0]["title"] == "Lisbon"


def test_an_app_that_is_down_adds_nothing_to_search_and_shows_a_plain_page(running):
    running.apps["photos"].close()
    assert running.json("/_atlas/api/search?q=lisbon")["results"] == []
    status, _, body = running.request("GET", "/", f"photos.atlas.localhost:{running.port}")
    assert status == 502 and b"is not running" in body
    json.dumps(running.json("/_atlas/api/modules"))


def start_update(running, origin=True, header=True):
    headers = {}
    if origin:
        headers["Origin"] = f"http://atlas.localhost:{running.port}"
    if header:
        headers["X-Atlas"] = "1"
    return running.request("POST", "/_atlas/api/scan", f"atlas.localhost:{running.port}", b"", headers)


def test_one_update_button_starts_every_app_and_reports_each_one(running):
    status, _, body = start_update(running)
    assert status == 200
    report = json.loads(body)
    assert set(report["modules"]) == {"money", "photos"} and report["running"] is True
    assert report["modules"]["money"]["progress"] == "reading" and report["modules"]["money"]["name"] == "Money"
    assert running.apps["money"].scanning and running.apps["photos"].scanning  # the app's own change-protection header and token were supplied for it
    running.apps["money"].scanning = running.apps["photos"].scanning = False
    done = running.json("/_atlas/api/scan")
    assert done["running"] is False and done["modules"]["photos"]["summary"] == "3 files read" and done["modules"]["photos"]["needs_check"] == 1


def test_another_website_cannot_start_an_update(running):
    assert start_update(running, origin=False)[0] == 403
    assert start_update(running, header=False)[0] == 403
    status, _, _ = running.request("POST", "/_atlas/api/scan", f"atlas.localhost:{running.port}", b"", {"Origin": "http://evil.example", "X-Atlas": "1"})
    assert status == 403 and not running.apps["money"].scanning


def test_an_app_that_is_down_is_reported_and_does_not_stop_the_others(running):
    running.apps["money"].close()
    report = json.loads(start_update(running)[2])
    assert report["modules"]["money"]["up"] is False and "not running" in report["modules"]["money"]["problems"][0]
    assert report["modules"]["photos"]["up"] is True and running.apps["photos"].scanning
