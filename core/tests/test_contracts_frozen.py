"""WP3.1: API 1.0 is frozen. Its two files are byte-identical to the accepted baseline, the default validator means 1.0, and the running Core still serves only 1.0
(a request for 1.1 fails closed) until a later reviewed package serves 1.1."""

from __future__ import annotations

import hashlib

import pytest
from conftest import World, grant, request
from test_api import Harness

from atlas_core import SUPPORTED_VERSIONS, contracts

FROZEN_SHA256 = {
    "atlas-contracts.schema.json": "65f5a3f6ac41410ea494e2902759a8dca3c2d3ef48e023ebdb6fe548a66a386c",
    "openapi.yaml": "c653a427fc632dd6f834338b4c1c0cbf6513e12771b541aff68935682e034393",
}


@pytest.fixture
def h(tmp_path) -> Harness:
    return Harness(World(tmp_path, [grant("documents")]))


@pytest.mark.parametrize("name", sorted(FROZEN_SHA256))
def test_the_1_0_contract_files_are_byte_identical_to_the_accepted_baseline(name):
    assert hashlib.sha256((contracts.contracts_dir() / name).read_bytes()).hexdigest() == FROZEN_SHA256[name]


def test_the_default_validator_is_1_0_and_never_applies_a_1_1_requirement():
    assert contracts.VERSIONS == ("1.0", "1.1")
    assert "Coverage" not in contracts.type_names() and "Coverage" in contracts.type_names("1.1")
    with pytest.raises(contracts.UnsupportedVersion):
        contracts.type_names("1.2")


def test_the_runtime_still_advertises_only_1_0():
    assert SUPPORTED_VERSIONS == ("1.0",)


def test_a_request_for_1_1_is_refused_today_but_the_discovery_call_still_answers_it(h):
    status, body = h.json("POST", "/v1/tasks", request(), headers={"x-atlas-api-version": "1.1"})
    assert status == 426 and body["code"] == "unsupported_version" and h.w.retriever.calls == []
    assert h.json("GET", "/v1/version", headers={"x-atlas-api-version": "1.1"}) == (200, {"api_version": "1.0", "supported": ["1.0"]})
    assert h.json("POST", "/v1/tasks", request(), headers={"x-atlas-api-version": "1.0"})[0] == 201


def test_no_route_serves_the_specification_only_endpoints(h):
    for method, target in (("GET", "/v1/consent"), ("POST", "/v1/consent"), ("DELETE", "/v1/consent/grant0001"), ("GET", "/v1/index/status")):
        status, body = h.json(method, target, {"sources": ["documents"]} if method == "POST" else None)
        assert status == 404 and body["code"] == "not_found", (method, target)
