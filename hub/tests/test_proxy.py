import json


def photos(running, path="/", method="GET", body=None, headers=None):
    return running.request(method, path, f"photos.home.localhost:{running.port}", body, headers)


def test_an_app_is_reached_under_its_own_name_and_sees_its_own_address(running):
    status, headers, body = photos(running, "/api/health")
    assert status == 200 and json.loads(body) == {"ok": True}
    assert running.apps["photos"].seen[-1]["host"] == running.apps["photos"].url.removeprefix("http://")  # the app is told its own local name, not the hub's


def test_the_app_may_be_shown_inside_the_hub_page_and_nowhere_else(running):
    _, headers, _ = photos(running, "/api/health")
    policy = headers["content-security-policy"]
    assert f"frame-ancestors http://home.localhost:{running.port}" in policy and "'none'" not in policy.split("frame-ancestors")[1]
    assert "default-src 'self'" in policy  # the rest of the app's own policy is untouched


def test_a_page_from_another_site_cannot_act_through_the_hub(running):
    status, _, _ = photos(running, "/api/chat", "POST", b"{}", {"Origin": "http://evil.example"})
    assert status == 403 and not any(s["method"] == "POST" for s in running.apps["photos"].seen)


def test_the_hubs_own_origins_are_passed_on_as_the_apps_own(running):
    origin = f"http://photos.home.localhost:{running.port}"
    status, _, body = photos(running, "/api/chat", "POST", b'{"a": 1}', {"Origin": origin, "Content-Type": "application/json"})
    assert status == 200 and json.loads(body) == {"echo": '{"a": 1}'}
    assert running.apps["photos"].seen[-1]["origin"] == running.apps["photos"].url


def test_a_streamed_answer_arrives_in_pieces_not_all_at_the_end(running):
    status, headers, body = photos(running, "/api/stream")
    assert status == 200 and headers["content-type"] == "text/event-stream" and body == b"data: 0\n\ndata: 1\n\ndata: 2\n\n"


def test_an_oversized_request_is_refused_before_it_reaches_the_app(running):
    status, _, _ = photos(running, "/api/chat", "POST", None, {"Content-Length": str(50 * 1024 * 1024)})
    assert status == 413


def test_the_app_keeps_its_own_errors(running):
    assert photos(running, "/missing")[0] == 404


def test_the_app_is_always_called_by_its_own_local_name_even_when_the_hub_reaches_it_another_way():
    from hub.registry import parse

    docker = parse({"id": "money", "name": "Money", "upstream": "http://host.docker.internal:8501"}, "x")
    assert docker.netloc == "host.docker.internal:8501" and docker.presented == "127.0.0.1:8501"
    custom = parse({"id": "money", "name": "Money", "upstream": "http://host.docker.internal:8501", "host": "money.localhost:8501"}, "x")
    assert custom.presented == "money.localhost:8501"
