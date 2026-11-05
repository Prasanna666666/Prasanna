import json
from pathlib import Path

import pytest

from hub.registry import ManifestError, load, parse, upstream_is_private


def write(directory: Path, name: str, data: dict) -> None:
    (directory / name).write_text(json.dumps(data))


GOOD = {"id": "health", "name": "Health", "upstream": "http://127.0.0.1:8900", "pages": [{"id": "home", "label": "Home"}]}


def test_a_module_file_becomes_a_module_with_its_pages(tmp_path):
    write(tmp_path, "health.json", GOOD)
    m = load(tmp_path)["health"]
    assert m.name == "Health" and m.netloc == "127.0.0.1:8900" and [p.id for p in m.pages] == ["home"]
    assert "upstream" not in m.public()  # the page is never told where the app really lives


def test_only_this_computer_and_the_private_network_are_allowed_as_upstreams():
    for url in ("http://127.0.0.1:1", "http://localhost:1", "http://host.docker.internal:1", "http://10.1.2.3:1", "http://ollama.internal:1"):
        assert upstream_is_private(url)
    for url in ("http://example.com", "https://127.0.0.1:1", "http://8.8.8.8", "ftp://127.0.0.1", "http://"):
        assert not upstream_is_private(url)


@pytest.mark.parametrize("bad", [{"id": "Bad Id"}, {"id": "home"}, {"id": "x", "name": ""}, {"upstream": "http://example.com"}])
def test_a_bad_module_file_is_refused_with_a_reason(tmp_path, bad):
    with pytest.raises(ManifestError):
        parse({**GOOD, **bad}, "x.json")


def test_two_modules_cannot_share_an_id_and_a_broken_file_stops_start_up(tmp_path):
    write(tmp_path, "a.json", GOOD)
    write(tmp_path, "b.json", GOOD)
    with pytest.raises(ManifestError, match="already used"):
        load(tmp_path)
    (tmp_path / "b.json").write_text("{not json")
    with pytest.raises(ManifestError, match="cannot be read"):
        load(tmp_path)


def test_an_environment_variable_can_point_a_module_somewhere_else(monkeypatch):
    monkeypatch.setenv("HUB_UPSTREAM_HEALTH", "http://127.0.0.1:9999")
    assert parse(GOOD, "x").netloc == "127.0.0.1:9999"
    monkeypatch.setenv("HUB_UPSTREAM_HEALTH", "http://evil.example")
    with pytest.raises(ManifestError):
        parse(GOOD, "x")
