"""The Library: search through the same policy and retrieval path as a question, one result per source, and the coverage of each source so an incomplete index is never shown as a complete search."""

from __future__ import annotations

import pytest
from test_app import World
from test_client import atlas_client

pytestmark = pytest.mark.criterion(10)


@pytest.fixture
def world(tmp_path):
    w = World(tmp_path, mail=True)
    w.clients.register("client-mac-0001", w.key.public_key(), owner=True)
    yield w
    w.close()


def test_a_search_over_an_enabled_source_returns_one_titled_result_per_source_with_its_coverage(world):
    core = world.build()
    core.start()
    world.enable(core, "documents")
    world.wait_indexed(core)
    out = world.client().library_search("total due invoice", ["documents"])
    assert out["state"] == "results" and 1 <= len(out["results"]) <= 20
    first = out["results"][0]
    assert first["source_type"] == "documents" and first["title"] and "1250.50" in " ".join(r["excerpt"] for r in out["results"])
    assert len({r["source_id"] for r in out["results"]}) == len(out["results"])  # one entry per source
    assert out["coverage"][0]["source_type"] == "documents" and out["coverage"][0]["complete"] is True and out["coverage"][0]["total"] > 0


def test_nothing_is_searched_without_a_current_grant(world):
    core = world.build()
    core.start()
    out = world.client().library_search("total due", ["documents"])
    assert out == {"state": "denied", "results": [], "coverage": []} and core.indexes["documents"].coverage()["total"] == 0


def test_a_search_with_no_matches_says_so_and_an_incomplete_index_is_never_presented_as_complete(world):
    core = world.build()
    core.start()
    world.enable(core, "documents")
    world.wait_indexed(core)
    assert world.client().library_search("zzzunmatchedwordzzz", ["documents"])["state"] == "no_results"
    core.indexes["documents"].pause_growth("disk_pressure")  # an index that has not finished
    core.indexes["documents"]._set_pause("disk_pressure")
    partial = world.client().library_search("zzzunmatchedwordzzz", ["documents"])
    assert partial["state"] == "partial_no_results" and partial["coverage"][0]["complete"] is False


def test_a_malformed_search_is_refused_and_titles_and_excerpts_are_single_clean_lines(world):
    core = world.build()
    core.start()
    world.enable(core, "documents")
    world.wait_indexed(core)
    client = world.client()
    for bad in ({"query": "", "scope": ["documents"]}, {"query": "x", "scope": []}, {"query": "x", "scope": ["Documents; DROP"]}):
        with pytest.raises(atlas_client.ClientError) as e:
            client._json("POST", "/v1/library/search", bad)
        assert e.value.code == "invalid_request"
    for r in client.library_search("invoice", ["documents"])["results"]:
        assert "\n" not in r["title"] + r["excerpt"] and len(r["excerpt"]) <= 300 and len(r["title"]) <= 120
