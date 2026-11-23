"""WP3.1: API 1.1 is validated independently of the frozen 1.0: explicit negotiation, a deterministic merge, strict conditional shapes, the coverage-to-limitation rules,
a content-free check on every new field, OpenAPI 1.1 parity with 1.0 and the specification vectors of the 1.1 signing rule. Contract and schema tests only: nothing here serves
a route or changes the runtime."""

from __future__ import annotations

import copy
import hashlib
import json
import re

import pytest
import yaml
from openapi_spec_validator import validate as validate_openapi

from atlas_core import contracts, identity
from atlas_core.contracts import ContractBuildError, ContractError, UnsupportedVersion

DIR = contracts.contracts_dir()
BASE = json.loads((DIR / "atlas-contracts.schema.json").read_text())
DELTA = json.loads((DIR / "atlas-contracts.1.1.delta.schema.json").read_text())
SHA = "a" * 64
T = "2026-11-20T10:00:00Z"


def ok(name: str, value, version: str = "1.1") -> None:
    contracts.validate(name, value, version)


def bad(name: str, value, version: str = "1.1") -> None:
    with pytest.raises(ContractError):
        contracts.validate(name, value, version)


# ---- negotiation (specified; the runtime is unchanged) ------------------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("requested", "advertised", "applied"), [(None, ("1.0",), "1.0"), ("1.0", ("1.0",), "1.0"), ("1.1", ("1.0", "1.1"), "1.1"), (None, ("1.0", "1.1"), "1.0")]
)
def test_negotiation_selects_a_version_only_from_what_is_asked_and_advertised(requested, advertised, applied):
    assert contracts.negotiate(requested, advertised) == applied


@pytest.mark.parametrize("requested", ["1.1", "1.2", "2", "2.0", "", " 1.0", "1.1,1.1", "1.0, 1.1", "garbage", 1.0, 11, ["1.1"], b"1.1", True])
def test_negotiation_fails_closed_on_anything_else_and_on_1_1_when_it_is_not_advertised(requested):
    with pytest.raises(UnsupportedVersion):
        contracts.negotiate(requested, ("1.0",))


# ---- the deterministic merge ---------------------------------------------------------------------------------------------------------------------------
def tiny_base() -> dict:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://x.invalid/1.0",
        "title": "t",
        "$defs": {"A": {"type": "string"}, "B": {"$ref": "#/$defs/A"}},
    }


def tiny_delta(**over) -> dict:
    delta = {"x-overrides": ["A"], "x-additions": ["C"], "$defs": {"A": {"type": "integer"}, "C": {"$ref": "#/$defs/B"}}}
    delta.update(over)
    return delta


def test_the_merge_replaces_only_the_listed_names_adds_the_new_ones_and_keeps_the_root_metadata():
    base = tiny_base()
    before = copy.deepcopy(base)
    merged = contracts.build_1_1(base, tiny_delta())
    assert base == before  # never mutated
    assert {k: v for k, v in merged.items() if k != "$defs"} == {k: v for k, v in before.items() if k != "$defs"}
    assert merged["$defs"] == {"A": {"type": "integer"}, "B": {"$ref": "#/$defs/A"}, "C": {"$ref": "#/$defs/B"}}  # B is untouched and now sees the replaced A
    assert json.dumps(merged) == json.dumps(contracts.build_1_1(tiny_base(), tiny_delta()))  # deterministic, key order included


@pytest.mark.parametrize(
    "delta",
    [
        tiny_delta(**{"x-overrides": ["A", "A"]}),  # duplicate override
        tiny_delta(**{"x-additions": ["C", "C"]}),  # duplicate addition
        tiny_delta(**{"x-overrides": ["Z"], "$defs": {"Z": {"type": "string"}, "C": {"type": "string"}}}),  # override that 1.0 does not have
        tiny_delta(**{"x-additions": ["B"], "$defs": {"A": {"type": "integer"}, "B": {"type": "string"}}}),  # addition that collides with 1.0
        tiny_delta(**{"x-overrides": ["A"], "x-additions": ["A"]}),  # a name in both lists
        tiny_delta(**{"$defs": {"A": {"type": "integer"}, "C": {"type": "string"}, "D": {"type": "string"}}}),  # a definition in neither list
        tiny_delta(**{"$defs": {"A": {"type": "integer"}}}),  # a listed name without a definition
        tiny_delta(**{"$defs": {"A": {"type": "integer"}, "C": {"$ref": "#/$defs/Nowhere"}}}),  # a dangling reference
        tiny_delta(**{"$defs": {"A": {"type": "integer"}, "C": {"$ref": "other.json#/$defs/X"}}}),  # a reference that leaves the document
        tiny_delta(**{"$defs": {"A": {"type": "no-such-type"}, "C": {"type": "string"}}}),  # not a valid schema
        {"x-overrides": ["A"], "x-additions": ["C"]},  # no $defs
        {"x-overrides": "A", "x-additions": ["C"], "$defs": {}},  # a list that is not a list
    ],
)
def test_the_merge_refuses_every_delta_that_does_not_apply_cleanly(delta):
    with pytest.raises(ContractBuildError):
        contracts.build_1_1(tiny_base(), delta)


def test_the_real_delta_applies_to_the_real_1_0_document_and_the_committed_1_1_document_is_exactly_that_merge():
    merged = contracts.build_1_1(BASE, DELTA)
    assert json.loads((DIR / "atlas-contracts.1.1.schema.json").read_text()) == merged
    assert set(BASE["$defs"]) < set(merged["$defs"]) and set(DELTA["x-overrides"]) | set(DELTA["x-additions"]) == set(DELTA["$defs"])
    untouched = set(BASE["$defs"]) - set(DELTA["x-overrides"])
    assert all(merged["$defs"][name] == BASE["$defs"][name] for name in untouched)


# ---- a replaced type accepts everything the 1.0 type accepted, except where a field is newly required -------------------------------------------------
@pytest.mark.parametrize("name", ["Limitation", "ErrorCode"])
def test_a_replaced_enumeration_only_adds_values(name):
    old, new = BASE["$defs"][name]["enum"], contracts._document("1.1")["$defs"][name]["enum"]
    assert new[: len(old)] == old and len(new) > len(old)


@pytest.mark.parametrize("name", ["SafeEvent", "AnswerEnvelope", "Locator"])
def test_a_replaced_object_keeps_every_1_0_property(name):
    old = BASE["$defs"][name]["properties"]
    new = contracts._document("1.1")["$defs"][name]
    props = new["properties"] if "properties" in new else new["anyOf"][0]["properties"]
    assert set(old) <= set(props)
    if name == "AnswerEnvelope":
        assert new["required"] == [*BASE["$defs"][name]["required"], "coverage"]


# ---- Coverage ------------------------------------------------------------------------------------------------------------------------------------------
def cov(state="complete", searched=3, total=3, pending=(), failed=()):
    return {
        "state": state,
        "searched": searched,
        "total": total,
        "pending": [{"category": c, "count": 1} for c in pending],
        "failed": [{"reason_code": r, "count": 1} for r in failed],
        "as_of": T,
    }


@pytest.mark.parametrize(
    "value",
    [
        cov(),
        cov("indexing", 2, None, ("not_yet_indexed",)),
        cov("indexing", 0, 0),
        cov("partial", 3, 3, ("attachments",)),
        cov("partial", 3, 3, (), ("encrypted",)),
        cov("partial", 1, 9, ("unsupported_source", "os_access")),
    ],
)
def test_coverage_accepts_its_three_states(value):
    ok("Coverage", value)


@pytest.mark.parametrize(
    "value",
    [
        {**cov(), "state": "done"},
        {**cov(), "searched": -1},
        {**cov(), "total": -1},
        {**cov(), "extra": 1},
        {k: v for k, v in cov().items() if k != "as_of"},
        {k: v for k, v in cov().items() if k != "failed"},
        {**cov("partial", pending=("somewhere",))},
        {**cov("partial", failed=("badreason",))},
        cov("complete", pending=("attachments",)),  # complete with something pending
        cov("complete", failed=("corrupt",)),  # complete with something failed
        cov("partial"),  # partial with nothing pending and nothing failed
        {**cov(), "pending": [{"category": "attachments", "count": -1}]},
        {**cov(), "pending": [{"category": "attachments", "count": 1, "name": "x.pdf"}]},  # no free text
    ],
)
def test_coverage_refuses_every_malformed_or_contradictory_value(value):
    bad("Coverage", value)


# ---- AnswerEnvelope: the coverage-to-limitation rules --------------------------------------------------------------------------------------------------
def envelope(coverage=None, limitations=(), **over):
    value = {
        "task_id": "task00001", "answer": "x", "citations": [], "verification": {"status": "verified", "unproven_figures": [], "unproven_dates": [], "citation_failures": []},
        "language": {"support_status": "unmeasured"}, "limitations": list(limitations), "not_searched": [], "coverage": coverage if coverage is not None else cov(),
    }  # fmt: skip
    return {**value, **over}


VALID_MAPPINGS = [
    (cov(), ()),
    (cov(), ("context_truncated",)),
    (cov("indexing", 2, None, ("not_yet_indexed",)), ("indexing_incomplete",)),
    (cov("partial", 3, 3, ("attachments",)), ("attachment_pending",)),
    (cov("partial", 3, 3, ("unsupported_source",)), ("source_unsupported",)),
    (cov("partial", 3, 3, ("os_access",)), ("os_access_missing",)),
    (cov("partial", 3, 3, (), ("corrupt",)), ("partial_work",)),
    (cov("partial", 3, 9, ("not_yet_indexed",)), ("partial_work",)),
    (
        cov("partial", 3, 9, ("attachments", "unsupported_source", "os_access"), ("timeout",)),
        ("attachment_pending", "source_unsupported", "os_access_missing", "partial_work"),
    ),
]
INVALID_MAPPINGS = [
    (cov("indexing", 2, None, ("not_yet_indexed",)), ()),  # indexing without indexing_incomplete
    (cov("partial", 3, 3, ("attachments",)), ("indexing_incomplete",)),  # indexing_incomplete with a partial state
    (cov(), ("indexing_incomplete",)),  # ... or a complete one
    (cov("partial", 3, 3, ("attachments",)), ()),  # a pending category without its limitation
    (cov("partial", 3, 3, ("unsupported_source",)), ("partial_work",)),
    (cov("partial", 3, 3, ("os_access",)), ("source_unsupported",)),
    (cov("partial", 3, 3, (), ("corrupt",)), ()),  # failed items without partial_work
    (cov("partial", 3, 9, ("not_yet_indexed",)), ()),  # not_yet_indexed in a partial answer without partial_work
    (cov("partial", 3, 3, ("attachments", "os_access"), ()), ("attachment_pending",)),  # one of two categories disclosed
    (cov("partial", 3, 3, ("attachments",)), ("attachment_pending", "os_access_missing")),  # a limitation without its cause (contradictory)
    (cov("partial", 3, 3, ("attachments",)), ("attachment_pending", "source_unsupported")),
    (cov(), ("attachment_pending",)),  # complete with a pending limitation
    (cov(), ("source_unsupported",)),
    (cov(), ("os_access_missing",)),
]


@pytest.mark.parametrize(("coverage", "limitations"), VALID_MAPPINGS)
def test_an_answer_whose_limitations_match_its_coverage_is_valid(coverage, limitations):
    ok("AnswerEnvelope", envelope(coverage, limitations))


@pytest.mark.parametrize(("coverage", "limitations"), INVALID_MAPPINGS)
def test_an_answer_with_a_missing_or_contradictory_limitation_is_refused(coverage, limitations):
    bad("AnswerEnvelope", envelope(coverage, limitations))


def test_a_1_1_answer_needs_coverage_and_the_model_descriptor_is_optional():
    ok("AnswerEnvelope", envelope())
    ok("AnswerEnvelope", envelope(model={"model_id": "main-27b", "role": "main", "runtime": "mlx"}))
    without = envelope()
    del without["coverage"]
    bad("AnswerEnvelope", without)
    bad("AnswerEnvelope", envelope(model={"model_id": "main-27b", "role": "main", "runtime": "mlx", "prompt": "secret"}))


def test_a_1_0_shaped_answer_is_refused_by_1_1_and_still_valid_in_1_0_which_never_sees_the_1_1_requirement():
    old = envelope()
    del old["coverage"]
    bad("AnswerEnvelope", old, "1.1")
    ok("AnswerEnvelope", old, "1.0")
    with pytest.raises(ContractError):
        contracts.validate("AnswerEnvelope", envelope(), "1.0")  # a field that does not exist in 1.0 is refused there
    with pytest.raises(ContractError):
        contracts.validate("AnswerEnvelope", envelope())  # the default is 1.0


# ---- ModelDescriptor, IndexStatus, consent shapes ------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("value", [{"model_id": "m", "role": "ab", "runtime": "stub"}, {"model_id": "Main_27B.q4:1", "role": "fast_path", "runtime": "mlx"}])
def test_the_model_descriptor_accepts_ids_and_roles_and_the_two_runtimes(value):
    ok("ModelDescriptor", value)


@pytest.mark.parametrize(
    "value",
    [
        {"model_id": "m", "role": "main"},
        {"model_id": "m", "role": "main", "runtime": "ollama"},
        {"model_id": "has space", "role": "main", "runtime": "mlx"},
        {"model_id": "/Users/someone/model", "role": "main", "runtime": "mlx"},
        {"model_id": "x" * 65, "role": "main", "runtime": "mlx"},
        {"model_id": "m", "role": "Main", "runtime": "mlx"},
        {"model_id": "m", "role": "main", "runtime": "mlx", "prompt": "what is my balance"},
        {"model_id": "m", "role": "main", "runtime": "mlx", "version": "1"},
    ],
)
def test_the_model_descriptor_refuses_content_paths_and_extra_fields(value):
    bad("ModelDescriptor", value)


@pytest.mark.parametrize(
    "value",
    [
        {"state": "idle", "indexed": 0, "total": 0, "newest_indexed": None, "failed": []},
        {"state": "building", "indexed": 5, "total": None, "newest_indexed": T, "failed": [{"reason_code": "timeout", "count": 2}]},
    ],
)
def test_the_index_status_shape(value):
    ok("IndexStatus", value)


@pytest.mark.parametrize(
    "value",
    [
        {"state": "busy", "indexed": 0, "total": 0, "newest_indexed": None, "failed": []},
        {"state": "idle", "indexed": -1, "total": 0, "newest_indexed": None, "failed": []},
        {"state": "idle", "indexed": 0, "total": 0, "failed": []},
        {"state": "idle", "indexed": 0, "total": 0, "newest_indexed": "yesterday", "failed": []},
        {"state": "idle", "indexed": 0, "total": 0, "newest_indexed": None, "failed": [{"reason_code": "x.pdf", "count": 1}]},
        {"state": "idle", "indexed": 0, "total": 0, "newest_indexed": None, "failed": [], "path": "/x"},
    ],
)
def test_the_index_status_refuses_bad_values_and_free_text(value):
    bad("IndexStatus", value)


def grant_value():
    return {
        "grant_id": "grant0001",
        "source_type": "documents",
        "max_sensitivity": "medium",
        "designated_by": "owner",
        "purpose": "answer_question",
        "issued_at": T,
        "expires_at": None,
        "revoked": False,
    }


def test_the_consent_shapes_exist_in_1_1_only_and_refuse_bad_values():
    ok("ConsentRequest", {"sources": ["documents", "mail"]})
    for value in ({"sources": []}, {"sources": ["documents", "documents"]}, {"sources": ["Documents"]}, {"sources": ["documents"], "folders": ["/x"]}, {}):
        bad("ConsentRequest", value)
    ok(
        "ConsentState",
        {"grants": [grant_value()], "sources": [{"source_type": "documents", "os_access": "granted"}, {"source_type": "mail", "os_access": "unknown"}]},
    )
    for value in ({"grants": [], "sources": [{"source_type": "mail", "os_access": "denied"}]}, {"grants": [{"grant_id": "g"}], "sources": []}, {"grants": []}):
        bad("ConsentState", value)
    for name in ("ConsentRequest", "ConsentState", "IndexStatus", "ModelDescriptor", "Coverage"):
        assert name not in contracts.type_names("1.0")


# ---- Locator: conditional requirements and irrelevant fields -------------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    "value",
    [
        {"kind": "page", "page": 1},
        {"kind": "block", "block": 0},
        {"kind": "message_part", "message_part": "body"},
        {"kind": "message_part", "message_part": "body", "quoted": True},
        {"kind": "span_only"},
        {"kind": "header_field", "header": "from", "authenticity": "claimed"},
        {"kind": "header_field", "header": "message_id", "authenticity": "claimed"},
        {"kind": "attachment_part", "attachment_id": "attach0001"},
        {"kind": "attachment_part", "attachment_id": "attach0001", "page": 2},
        {"kind": "attachment_part", "attachment_id": "attach0001", "block": 3},
        {"kind": "sheet_cell", "sheet": 0, "cell": "B7"},
        {"kind": "sheet_cell", "sheet": 3, "cell": "AA120"},
    ],
)
def test_every_valid_locator_shape(value):
    ok("Locator", value)


@pytest.mark.parametrize(
    "value",
    [
        {"kind": "header_field"},  # missing header and authenticity
        {"kind": "header_field", "header": "from"},  # missing authenticity
        {"kind": "header_field", "authenticity": "claimed"},  # missing header
        {"kind": "header_field", "header": "from", "authenticity": "verified"},  # authenticity other than claimed
        {"kind": "header_field", "header": "cc", "authenticity": "claimed"},
        {"kind": "attachment_part"},  # missing attachment_id
        {"kind": "attachment_part", "attachment_id": "short"},
        {"kind": "sheet_cell", "cell": "B7"},  # missing sheet
        {"kind": "sheet_cell", "sheet": 0},  # missing cell
        {"kind": "sheet_cell", "sheet": "Salaries", "cell": "B7"},  # a sheet name is content of the owner
        {"kind": "sheet_cell", "sheet": 0, "cell": "7B"},
        {"kind": "sheet_cell", "sheet": 0, "cell": "B0"},
        {"kind": "page", "header": "from"},  # a new field on an old kind
        {"kind": "page", "page": 1, "authenticity": "claimed"},
        {"kind": "block", "block": 0, "cell": "A1"},
        {"kind": "message_part", "message_part": "body", "attachment_id": "attach0001"},
        {"kind": "page", "page": 1, "quoted": True},  # quoted only on message_part
        {"kind": "span_only", "quoted": False},
        {"kind": "header_field", "header": "from", "authenticity": "claimed", "quoted": True},
        {"kind": "header_field", "header": "from", "authenticity": "claimed", "page": 1},
        {"kind": "attachment_part", "attachment_id": "attach0001", "cell": "A1"},
        {"kind": "sheet_cell", "sheet": 0, "cell": "A1", "page": 1},
        {"kind": "unknown_kind"},
    ],
)
def test_a_locator_missing_a_required_field_or_carrying_an_irrelevant_one_is_refused(value):
    bad("Locator", value)


@pytest.mark.parametrize(
    "value", [{"kind": "page", "page": 1}, {"kind": "block", "block": 4}, {"kind": "message_part", "message_part": "thread"}, {"kind": "span_only"}]
)
def test_every_1_0_locator_stays_valid_in_1_1_and_an_evidence_reference_uses_the_new_kinds(value):
    ok("Locator", value, "1.0")
    ok("Locator", value, "1.1")
    ok(
        "EvidenceRef",
        {
            "source_id": "source0001",
            "source_type": "mail",
            "version_sha256": SHA,
            "locator": {"kind": "header_field", "header": "date", "authenticity": "claimed"},
            "span": {"start": 0, "end": 4},
        },
    )
    bad(
        "EvidenceRef",
        {
            "source_id": "source0001",
            "source_type": "mail",
            "version_sha256": SHA,
            "locator": {"kind": "header_field", "header": "date", "authenticity": "claimed"},
            "span": {"start": 0, "end": 4},
        },
        "1.0",
    )


# ---- Limitation, ErrorCode, SafeEvent ------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    "value", ["indexing_incomplete", "source_unsupported", "os_access_missing", "attachment_pending", "partial_work", "attachments_not_searched"]
)
def test_new_and_old_limitations_are_valid_in_1_1_and_the_new_ones_only_there(value):
    ok("Limitation", value)
    if value in ("indexing_incomplete", "source_unsupported", "os_access_missing", "attachment_pending"):
        bad("Limitation", value, "1.0")
    bad("Limitation", "made_up_limitation")


@pytest.mark.parametrize("value", ["os_access_missing", "index_unavailable", "unsupported_version"])
def test_new_and_old_error_codes(value):
    ok("ErrorCode", value)
    assert (value in ("unsupported_version",)) == (_valid("ErrorCode", value, "1.0"))
    bad("ErrorCode", "made_up_error")


def _valid(name: str, value, version: str) -> bool:
    try:
        contracts.validate(name, value, version)
    except ContractError:
        return False
    return True


def event(**fields):
    return {"event": "api.request", "component": "api", "correlation_id": "corr00001", **fields}


@pytest.mark.parametrize(
    "value",
    [
        event(event="consent.changed", component="consent", action="granted", source_type="documents"),
        event(event="consent.changed", component="consent", action="revoked", source_type="mail"),
        event(event="model.routed", component="model", role="main", model_id="main-27b"),
        event(event="egress.decision", component="egress", decision="deny", reason_code="leak_check", destination_class="search_provider"),
        event(),
        event(event="task.created", component="tasks", count=2, duration_ms=1.5),
    ],
)
def test_new_and_old_safe_events_are_valid_in_1_1(value):
    ok("SafeEvent", value)


@pytest.mark.parametrize(
    "value",
    [
        event(event="consent.changed", component="consent", action="renamed", source_type="documents"),
        event(event="model.routed", component="model", role="main", model_id="has space"),
        event(event="model.routed", component="model", prompt="what is my balance"),
        event(event="egress.decision", component="egress", destination_class="evil.example"),
        event(event="egress.decision", component="egress", url="https://evil.example/?d=secret"),
        event(event="egress.decision", component="egress", query="my statement"),
        event(event="not.an.event"),
        event(component="nowhere"),
        event(source_type="Documents"),
        event(role="Main Role"),
    ],
)
def test_a_safe_event_cannot_carry_content_a_host_a_url_or_a_free_text_field(value):
    bad("SafeEvent", value)
    assert not _valid("SafeEvent", event(event="model.routed", component="model", role="main", model_id="m"), "1.0")  # the new events exist only in 1.1


def new_string_fields(node, path="", out=None):
    """Every string schema in `node` that is not an enumeration, a constant, a pattern, a reference or a date-time (so it could carry free text)."""
    out = [] if out is None else out
    if isinstance(node, dict):
        if node.get("type") == "string" and not (set(node) & {"enum", "const", "pattern", "format"}):
            out.append(path)
        for key, value in node.items():
            new_string_fields(value, f"{path}/{key}", out)
    elif isinstance(node, list):
        for index, value in enumerate(node):
            new_string_fields(value, f"{path}/{index}", out)
    return out


# The only two free-text fields of the 1.1 additions, both by design and never logged: the cited span the owner asked to inspect, and public web text returned as untrusted data (it is public, carries no authority and
# is not evidence).
ALLOWED_FREE_TEXT = {"PassageText/properties/text", "ResearchResult/properties/text"}


def test_no_new_field_of_the_1_1_contract_can_carry_free_text():
    for name in DELTA["x-additions"]:
        found = [f for f in new_string_fields(DELTA["$defs"][name], name) if f not in ALLOWED_FREE_TEXT]
        assert not found, (
            name
        )  # whole new types; PassageText.text is the cited span itself, by design, and is served only to an enrolled client on the owner-only socket and never logged
    for name in DELTA["x-overrides"]:
        old, new = BASE["$defs"][name], DELTA["$defs"][name]
        added_paths = set(new_string_fields(new, name)) - set(new_string_fields(old, name))
        added_paths = {p for p in added_paths if "/answer" not in p}  # AnswerEnvelope.answer is a 1.0 field, free text by design
        assert not added_paths, (name, added_paths)


# ---- OpenAPI 1.1: parity with 1.0 and exactly the permitted delta --------------------------------------------------------------------------------------
OPENAPI_10 = yaml.safe_load((DIR / "openapi.yaml").read_text())
OPENAPI_11_PATH = DIR / "openapi-1.1.yaml"
OPENAPI_11 = yaml.safe_load(OPENAPI_11_PATH.read_text())
NEW_PATHS = {
    "/v1/consent",
    "/v1/consent/{grant_id}",
    "/v1/index/status",
    "/v1/tasks/{task_id}/citations/{index}",
    "/v1/compute",
    "/v1/enrol",
    "/v1/mode",
    "/v1/tasks/{task_id}/research",
    "/v1/actions",
    "/v1/actions/approve",
    "/v1/actions/undo",
    "/v1/sync",
    "/v1/devices",
    "/v1/devices/offer",
    "/v1/devices/pair",
    "/v1/devices/revoke",
    "/v1/library/search",
    "/v1/attention",
    "/v1/records/{domain}",
    "/v1/finance/summary",
    "/v1/health/summary",
    "/v1/review",
    "/v1/app/updates",
    "/v1/app/updates/install",
    "/v1/app/updates/rollback",
}
OPS = ("get", "post", "put", "patch", "delete")


def operations(spec):
    return {(path, method): op for path, item in spec["paths"].items() for method, op in item.items() if method in OPS}


def normalised(op):
    """A 1.1 operation with exactly the permitted additions removed: the ApiVersion parameter, the response echo header, the versioned error response and the retargeted schema files."""
    text = (
        yaml.safe_dump(op)
        .replace("./atlas-contracts.1.1.schema.json#", "./atlas-contracts.schema.json#")
        .replace("components/responses/ErrorVersioned", "components/responses/Error")
    )
    out = yaml.safe_load(text)
    out["parameters"] = [p for p in out.get("parameters", []) if p != {"$ref": "#/components/parameters/ApiVersion"}] or None
    for response in out["responses"].values():
        response.get("headers", {}).pop("X-Atlas-Api-Version", None)
        if not response.get("headers", True):
            del response["headers"]
    return {k: v for k, v in out.items() if v is not None}


def test_openapi_1_1_is_valid_and_every_reference_resolves():
    validate_openapi(OPENAPI_11, base_uri=OPENAPI_11_PATH.resolve().as_uri())
    assert OPENAPI_11["openapi"].startswith("3.1") and OPENAPI_11["info"]["version"] == "1.1"
    names = set(re.findall(r"atlas-contracts\.1\.1\.schema\.json#/\$defs/([A-Za-z]+)", OPENAPI_11_PATH.read_text()))
    assert names and names <= set(contracts.type_names("1.1"))


def test_openapi_1_1_keeps_every_1_0_path_and_operation_id_and_adds_only_the_three_new_paths():
    ops10, ops11 = operations(OPENAPI_10), operations(OPENAPI_11)
    assert set(ops10) <= set(ops11)
    assert {key[0] for key in ops11} - {key[0] for key in ops10} == NEW_PATHS
    assert {ops10[k]["operationId"] for k in ops10} <= {ops11[k]["operationId"] for k in ops11}
    for key in ops10:
        assert ops10[key]["operationId"] == ops11[key]["operationId"], key
    for key in set(ops11) - set(ops10):
        assert ops11[key]["x-atlas-status"].startswith("served by the Core"), key


def test_each_1_1_operation_equals_its_1_0_counterpart_apart_from_the_permitted_delta_and_version_discovery_has_none():
    ops10, ops11 = operations(OPENAPI_10), operations(OPENAPI_11)
    discovery = ("/v1/version", "get")
    assert ops11[discovery] == ops10[discovery]  # no parameter, no echo header, the 1.0 schema: the unversioned discovery call
    for key, op in ops10.items():
        if key != discovery:
            assert normalised(ops11[key]) == op, key
    for key, op in ops11.items():
        if key != discovery:
            assert {"$ref": "#/components/parameters/ApiVersion"} in op["parameters"], key
            assert all(
                r.get("headers", {}).get("X-Atlas-Api-Version") or r.get("$ref") == "#/components/responses/ErrorVersioned" for r in op["responses"].values()
            ), key


def test_the_1_1_security_scheme_states_the_six_field_signing_rule_and_the_1_0_file_does_not():
    new = OPENAPI_11["components"]["securitySchemes"]["SignedRequest"]["description"]
    assert "SIX fields" in new and "1.1" in new and "/v1/version is the unversioned discovery call" in new
    assert "SIX fields" not in OPENAPI_10["components"]["securitySchemes"]["SignedRequest"]["description"]


# ---- the 1.1 signing rule: specification vectors and a reference function (nothing here is verified by the Core) -----------------------------------------
def reference_canonical(version: str, method: str, target: str, timestamp: str, nonce: str, body: bytes) -> bytes:
    fields = [method.upper(), target, timestamp, nonce, hashlib.sha256(body).hexdigest()]
    if any(c in f for f in fields for c in "\r\n"):
        raise ValueError("a field contains CR or LF")
    return "\n".join(([version] if version == "1.1" else []) + fields).encode()


VECTOR = ("post", "/v1/tasks?after=0", "1700000000", "abcdefgh12345678", b'{"a":1}')
VECTOR_10_HEX = "504f53540a2f76312f7461736b733f61667465723d300a313730303030303030300a616263646566676831323334353637380a30313561626437663563633537613264643934623735393066303461643830383432373339303565653333656335636562656165363232373661393766383632"
VECTOR_11_HEX = "312e310a" + VECTOR_10_HEX


def test_the_1_0_signed_message_is_unchanged_and_equals_what_the_identity_module_builds():
    assert reference_canonical("1.0", *VECTOR).hex() == VECTOR_10_HEX
    assert identity.canonical(*VECTOR) == reference_canonical("1.0", *VECTOR)


def test_the_1_1_signed_message_is_the_version_then_the_five_1_0_fields_and_matches_the_published_vector():
    message = reference_canonical("1.1", *VECTOR)
    assert message.hex() == VECTOR_11_HEX and message.decode().split("\n")[0] == "1.1" and message.count(b"\n") == identity.canonical(*VECTOR).count(b"\n") + 1
    assert message != identity.canonical(*VECTOR) and not message.endswith(b"\n")


def test_stripping_or_changing_the_version_downgrades_to_a_different_message_so_the_signature_would_fail():
    signed_for_11 = reference_canonical("1.1", *VECTOR)
    assert reference_canonical("1.0", *VECTOR) != signed_for_11  # header stripped or set to 1.0: verified as five fields
    assert reference_canonical("1.1", *VECTOR) != identity.canonical(*VECTOR)  # a request signed for 1.0 and re-labelled 1.1


@pytest.mark.parametrize("position", range(5))
def test_a_field_containing_a_line_break_is_refused_so_a_field_cannot_smuggle_a_delimiter(position):
    fields = list(VECTOR)
    fields[position] = ("x\n" + "1") if position != 4 else b"{}"  # the body is hashed, so it cannot carry a delimiter; the other four are refused
    if position == 4:
        assert reference_canonical("1.1", *fields)  # the body is not a delimited field
    else:
        with pytest.raises(ValueError):
            reference_canonical("1.1", *fields)


def test_a_six_field_message_can_never_equal_a_five_field_message():
    for method in ("GET", "POST", "DELETE"):
        five = identity.canonical(method, "/v1/tasks", "1700000000", "abcdefgh12345678", b"")
        six = reference_canonical("1.1", method, "/v1/tasks", "1700000000", "abcdefgh12345678", b"")
        assert five != six and five.count(b"\n") + 1 == six.count(b"\n")


def test_the_contract_documentation_publishes_the_same_vectors():
    text = (contracts.contracts_dir().parent / "docs" / "CONTRACT_1_1.md").read_text()
    assert VECTOR_10_HEX in text and VECTOR_11_HEX in text


# ---- SafeEvent.reason_code is a closed vocabulary in 1.1 -----------------------------------------------------------------------------------------------
POLICY_REASONS = [
    "granted",
    "nothing_requested",
    "unknown_source_type",
    "restricted_domain",
    "deferred_decision",
    "no_grant",
    "grant_revoked",
    "grant_expired",
    "sensitivity_exceeds_grant",
]  # policy.decision (policy.py)
RECOVERY_REASONS = ["requeued", "needs_attention"]  # task.recovered (tasks.py recover)
VERIFICATION_REASONS = ["verified", "partially_verified", "unverified", "failed"]  # answer.verified (the Verification.status values)
EGRESS_REASONS = [
    "allowed", "not_a_typed_tool", "leak_check", "url_not_permitted", "private_address", "redirect_blocked", "length_cap", "header_not_allowed", "host_not_allowed", "provider_disabled", "budget_exceeded",
]  # fmt: skip  # egress.decision: INTERNET_AND_NETWORK_POLICY.md sections 10.1 to 10.6
ROUTING_REASONS = ["primary_model", "deep_model", "fallback_model", "memory_fallback", "model_refused"]  # model.routed (intelligence.py)
ALL_REASONS = [*POLICY_REASONS, *RECOVERY_REASONS, *VERIFICATION_REASONS, *EGRESS_REASONS, *ROUTING_REASONS]


def test_the_reason_code_enumeration_is_exactly_the_documented_vocabulary():
    declared = contracts._document("1.1")["$defs"]["SafeEvent"]["properties"]["reason_code"]
    assert declared["enum"] == ALL_REASONS and "pattern" not in declared and len(set(ALL_REASONS)) == len(ALL_REASONS)


@pytest.mark.parametrize("reason", ALL_REASONS)
def test_every_listed_reason_code_is_accepted(reason):
    ok("SafeEvent", event(event="policy.decision", component="policy", reason_code=reason))
    ok("SafeEvent", event(event="egress.decision", component="egress", decision="deny", reason_code=reason, destination_class="connector"))


@pytest.mark.parametrize(
    "reason",
    [
        "made_up_reason",
        "no_such_code",
        "my_bank_statement",
        "balance_1200",
        "statement_pdf",
        "Granted",
        "no grant",
        "../etc/passwd",
        "a/b",
        "granted;drop",
        "",
        "x" * 49,
        7,
        None,
    ],
)
def test_an_unknown_slug_or_a_content_like_value_is_refused_as_a_reason_code(reason):
    bad("SafeEvent", event(event="policy.decision", component="policy", reason_code=reason))
    bad("SafeEvent", event(event="egress.decision", component="egress", reason_code=reason))


def test_the_open_vocabulary_of_1_0_is_unchanged_and_only_1_1_closes_it():
    ok("SafeEvent", event(reason_code="made_up_reason"), "1.0")  # frozen 1.0 keeps its pattern
    bad("SafeEvent", event(reason_code="made_up_reason"), "1.1")


def test_every_reason_the_policy_code_can_return_is_in_the_closed_list():
    source = (contracts.contracts_dir().parent / "src" / "atlas_core" / "policy.py").read_text()
    found = set(re.findall(r'return "([a-z_]+)", (?:None|str)', source)) | set(re.findall(r'reason = "([a-z_]+)"', source)) | {"nothing_requested"}
    assert found and found <= set(POLICY_REASONS), found - set(POLICY_REASONS)


def test_every_event_the_running_core_emits_fits_the_1_1_safe_event(tmp_path):
    from conftest import World, grant, parse_events, request

    events = []
    for index, grants in enumerate(([grant("documents")], [])):  # an answered task, then a denied one
        (tmp_path / str(index)).mkdir()
        world = World(tmp_path / str(index), grants)
        world.run_new(request())
        events += parse_events(world.lines)
    assert {e["event"] for e in events} >= {"task.created", "policy.decision", "answer.verified", "task.transition"}
    for record in events:
        ok("SafeEvent", record)
    assert {e["reason_code"] for e in events if "reason_code" in e} >= {"granted", "no_grant", "verified"}
