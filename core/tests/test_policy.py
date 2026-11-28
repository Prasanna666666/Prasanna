"""Criteria 1, 2 and 6: the policy decides before anything is retrieved; restricted and deferred sources never enter a context; Mail stays a separate, default-deny source."""

from __future__ import annotations

from datetime import timedelta

import pytest
from conftest import (
    ALL_SENTINELS,
    SENTINEL_ATTACH,
    SENTINEL_FIN,
    SENTINEL_HEALTH,
    T0,
    StubModel,
    World,
    all_output,
    grant,
    labels,
    passage,
    request,
)

from atlas_core.gate import ContextBuilder, GatedModel, GatedRetrieval, ModelContext
from atlas_core.policy import InMemoryGrants, PermitToken, PolicyEngine, PolicyViolation

pytestmark = []


@pytest.mark.criterion(1)
def test_default_is_deny_nothing_is_retrieved_and_no_model_is_called(tmp_path):
    w = World(tmp_path, [])
    record = w.run_new(request(["documents"]))
    assert (record["state"], record["terminal_reason"]) == ("failed", "denied")
    assert w.retriever.calls == [] and w.model.calls == []
    answer = w.service.answer(record["task_id"])
    assert answer["not_searched"] == [{"source_type": "documents", "reason_code": "no_grant"}]


@pytest.mark.criterion(1)
def test_policy_is_decided_before_retrieval_and_retrieval_before_the_model(tmp_path):
    w = World(tmp_path, [grant("documents")])
    order: list[str] = []
    decide, search, generate = w.service._d.policy.decide, w.retriever.search, w.model.generate
    w.service._d.policy.decide = lambda *a, **k: (order.append("policy"), decide(*a, **k))[1]  # type: ignore[method-assign]
    w.retriever.search = lambda *a, **k: (order.append("retrieve"), search(*a, **k))[1]  # type: ignore[method-assign]
    w.model.generate = lambda c: (order.append("model"), generate(c))[1]  # type: ignore[method-assign]
    w.run_new(request(["documents"]))
    assert order.index("policy") < order.index("retrieve") < order.index("model")


@pytest.mark.criterion(1)
def test_only_the_granted_source_type_is_searched_and_the_rest_is_disclosed(tmp_path):
    w = World(tmp_path, [grant("documents")])
    record = w.run_new(request(["documents", "mail"]))
    assert w.retriever.calls == ["documents"]
    assert {p["evidence"]["source_type"] for p in w.model.calls[0].passages} == {"documents"}
    answer = w.service.answer(record["task_id"])
    assert {"source_type": "mail", "reason_code": "no_grant"} in answer["not_searched"]
    assert "source_type_not_searched" in answer["limitations"]


@pytest.mark.criterion(1)
@pytest.mark.parametrize(
    ("grants", "reason"),
    [
        ([grant("documents", revoked=True)], "grant_revoked"),
        ([grant("documents", expires="2026-11-01T00:00:00+00:00")], "grant_expired"),
        ([grant("documents", sensitivity="low")], "sensitivity_exceeds_grant"),
        ([], "no_grant"),
    ],
)
def test_a_grant_must_be_current_unrevoked_and_high_enough(grants, reason):
    decision, token = PolicyEngine(InMemoryGrants(grants)).decide(["documents"], T0)
    assert token is None and decision["decision"] == "deny" and decision["reason_code"] == reason


@pytest.mark.criterion(1)
def test_a_token_cannot_be_forged_and_a_context_cannot_be_made_by_hand():
    with pytest.raises(PolicyViolation):
        PermitToken(frozenset({"documents"}), T0 + timedelta(hours=1), {}, None)
    with pytest.raises(PolicyViolation):
        ModelContext("question", (), False, None)


@pytest.mark.criterion(1)
def test_the_model_gate_refuses_an_expired_token_and_the_builder_refuses_a_passage_outside_the_token():
    decision, token = PolicyEngine(InMemoryGrants([grant("documents")])).decide(["documents"], T0)
    assert token is not None and decision["decision"] == "allow"
    from conftest import CORPUS

    context = ContextBuilder(labels()).build(token, "q", [passage(CORPUS[0], 0, 10)], T0)
    with pytest.raises(PolicyViolation):
        GatedModel(StubModel(), labels()).generate(token, context, T0 + timedelta(hours=1))
    with pytest.raises(PolicyViolation):
        ContextBuilder(labels()).build(token, "q", [passage(CORPUS[4], 0, 10)], T0)


@pytest.mark.criterion(1)
def test_a_retriever_that_returns_a_denied_source_ends_the_task_and_nothing_reaches_the_model(tmp_path):
    w = World(tmp_path, [grant("documents")])
    w.retriever.misbehave = "finance"
    record = w.run_new(request(["documents"]))
    assert (record["state"], record["terminal_reason"]) == ("failed", "needs_attention")
    assert w.model.calls == []


@pytest.mark.criterion(1)
def test_gated_retrieval_never_calls_a_retriever_for_a_type_the_token_does_not_allow():
    decision, token = PolicyEngine(InMemoryGrants([grant("documents")])).decide(["documents", "mail"], T0)
    assert token is not None
    calls: list[str] = []

    class Spy:
        def search(self, source_type, query):
            calls.append(source_type)
            return []

    GatedRetrieval(labels()).fetch(token, Spy(), "q", T0)
    assert calls == ["documents"] and decision["denied"] == [{"source_type": "mail", "reason_code": "no_grant"}]


FIN = grant("finance", sensitivity="restricted")
HEALTH = grant("health", sensitivity="restricted")


@pytest.mark.criterion(5)
def test_an_owner_authorised_finance_task_lets_the_local_model_read_finance_and_nothing_else(tmp_path, caplog, capsys):
    """G-021: owner-authorised Finance data MAY enter the local model context of the task it was authorised for; nothing of any other domain comes with it, and no content is logged."""
    w = World(tmp_path, [grant("documents"), FIN, HEALTH])
    record = w.run_new(request(["finance"]))
    assert w.retriever.calls == ["finance"]  # only the domain the task named: the documents and health grants are not used
    assert {p["evidence"]["source_type"] for p in w.model.calls[0].passages} == {"finance"}  # the separately labelled domain
    assert SENTINEL_FIN in repr(w.model.calls)  # the local model really was given it
    assert SENTINEL_FIN not in repr(w.store.events_after(record["task_id"], 0)) + all_output(
        w, caplog, capsys
    )  # no event, log line or output carries the content
    assert SENTINEL_HEALTH not in repr(w.model.calls)


@pytest.mark.criterion(5)
@pytest.mark.parametrize(
    ("grants", "scope"),
    [
        ([grant("documents")], ["finance"]),  # a documents grant never opens finance
        ([grant("finance")], ["finance"]),  # a ceiling below "restricted" never opens it
        ([HEALTH], ["finance"]),  # another restricted domain's grant never opens it
        ([], ["finance"]),
        ([FIN], ["health"]),
    ],
)
def test_a_restricted_domain_needs_its_own_grant_with_a_restricted_ceiling(tmp_path, grants, scope):
    w = World(tmp_path, grants)
    record = w.run_new(request(scope))
    assert w.retriever.calls == [] and w.model.calls == [] and record["terminal_reason"] == "denied"
    assert w.service.answer(record["task_id"])["not_searched"][0]["reason_code"] == "restricted_domain"
    assert SENTINEL_FIN not in repr(w.model.calls) and SENTINEL_HEALTH not in repr(w.model.calls)


@pytest.mark.criterion(5)
def test_a_task_authorised_for_one_restricted_domain_never_reaches_the_other(tmp_path):
    w = World(tmp_path, [grant("documents"), FIN])
    record = w.run_new(request(["documents", "finance", "health"]))
    assert sorted(w.retriever.calls) == ["documents", "finance"]
    reasons = {n["source_type"]: n["reason_code"] for n in w.service.answer(record["task_id"])["not_searched"]}
    assert reasons == {"health": "restricted_domain"}
    assert SENTINEL_HEALTH not in repr(w.model.calls)


@pytest.mark.criterion(5)
def test_revoking_a_finance_grant_ends_the_authority_before_anything_more_is_read_or_sent():
    g = grant("finance", sensitivity="restricted")
    engine = PolicyEngine(InMemoryGrants([g]))
    decision, token = engine.decide(["finance"], T0)
    assert token is not None and decision["decision"] == "allow"
    g["revoked"] = True
    still, denied = engine.revalidate(token, T0)
    assert still == frozenset() and denied == [{"source_type": "finance", "reason_code": "grant_revoked"}]


@pytest.mark.criterion(6)
def test_mail_is_not_searchable_by_default_and_documents_do_not_open_it(tmp_path):
    w = World(tmp_path, [])
    assert w.run_new(request(["mail"], key="idem-mail-0001"))["terminal_reason"] == "denied" and w.retriever.calls == []
    w2 = World(tmp_path / "second", [grant("documents")]) if (tmp_path / "second").mkdir() is None else None
    assert w2 is not None
    record = w2.run_new(request(["documents", "mail"]))
    assert w2.retriever.calls == ["documents"]
    assert {"source_type": "mail", "reason_code": "no_grant"} in w2.service.answer(record["task_id"])["not_searched"]


@pytest.mark.criterion(6)
def test_mail_body_headers_and_attachments_have_distinct_types_and_attachments_stay_excluded(tmp_path, caplog, capsys):
    w = World(tmp_path, [grant("mail"), grant("mail_attachment")])
    w.model.answer_text, w.model.quote = "The meeting is on 2026-04-02.", "2026-04-02"
    record = w.run_new(request(["mail", "mail_attachment"]))
    assert w.retriever.calls == ["mail"]  # the attachment type is deferred to G-O18 even though a grant exists
    cited = w.service.answer(record["task_id"])
    assert cited["citations"][0]["evidence"]["locator"] == {"kind": "message_part", "message_part": "body"}
    assert "attachments_not_searched" in cited["limitations"]
    assert {"source_type": "mail_attachment", "reason_code": "deferred_decision"} in cited["not_searched"]
    assert SENTINEL_ATTACH not in repr(w.model.calls) + repr(cited) + all_output(w, caplog, capsys)
    assert not any(s in all_output(w, caplog, capsys) for s in ALL_SENTINELS)
