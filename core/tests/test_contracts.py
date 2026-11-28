"""The language-neutral contract itself: it is valid, strict, consistent with the error taxonomy, and the OpenAPI document matches it."""

from __future__ import annotations

import pathlib

import pytest
import yaml
from conftest import CORPUS, DOC_PAGE1, evidence
from openapi_spec_validator import validate as validate_openapi

from atlas_core import contracts
from atlas_core.contracts import ContractError, type_names, validate
from atlas_core.errors import TABLE, user_error

OPENAPI = contracts.contracts_dir() / "openapi.yaml"


@pytest.mark.criterion(13)
def test_every_type_of_the_contract_compiles():
    assert len(type_names()) >= 20
    for name in type_names():
        contracts._validator(name)


@pytest.mark.criterion(13)
def test_the_openapi_document_is_valid_and_every_schema_it_points_at_exists():
    spec = yaml.safe_load(OPENAPI.read_text())
    validate_openapi(spec, base_uri=OPENAPI.resolve().as_uri())
    assert spec["openapi"].startswith("3.1")
    text = OPENAPI.read_text()
    for name in set(__import__("re").findall(r"#/\$defs/([A-Za-z]+)", text)):
        assert name in type_names(), name


@pytest.mark.criterion(13)
def test_the_error_taxonomy_matches_the_contract_exactly_and_every_message_is_user_safe():
    enum = contracts._document()["$defs"]["ErrorCode"]["enum"]
    assert sorted(TABLE) == sorted(enum)
    for code in TABLE:
        error = user_error(code, "task0001")
        validate("UserSafeError", error)
        assert not any(c in error["message"] for c in "/\\{}<>") and "Traceback" not in error["message"]


@pytest.mark.criterion(13)
def test_the_contract_is_strict_unknown_fields_and_bad_values_are_refused_without_echoing_them():
    good = {"objective": "q", "source_scope": ["documents"], "budget": {"max_seconds": 10, "max_retries": 1}, "idempotency_key": "idem-key-0001"}
    validate("TaskRequest", good)
    for bad in (
        {**good, "grants": []},
        {**good, "source_scope": []},
        {**good, "idempotency_key": "short"},
        {**good, "budget": {"max_seconds": 0, "max_retries": 1}},
        {**good, "objective": ""},
    ):
        with pytest.raises(ContractError) as error:
            validate("TaskRequest", bad)
        assert "short" not in str(error.value) and "grants" not in repr(error.value.args)  # the place is named, the value never


@pytest.mark.criterion(4)
def test_an_evidence_reference_is_immutable_data_with_a_version_hash_a_locator_and_a_span():
    validate("EvidenceRef", evidence(CORPUS[0], 0, len(DOC_PAGE1), {"kind": "page", "page": 1}))
    with pytest.raises(ContractError):
        validate("EvidenceRef", {**evidence(CORPUS[0], 0, 5), "version_sha256": "not-a-hash"})
    assert pathlib.Path(contracts.contracts_dir() / "atlas-contracts.schema.json").exists()
