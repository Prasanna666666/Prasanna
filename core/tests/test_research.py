"""Public web research through the Core's answer path (API 1.1 `POST /v1/tasks/{id}/research`): off by default, a refusal before anything is sent when the query repeats private context, no network at all for a task
with Finance or Health in scope, the result is untrusted data and never changes the task's answer. Synthetic fixtures only: no test reaches the Internet."""

from __future__ import annotations

import json

import pytest
from conftest import KEY
from test_app import World
from test_egress import PUBLIC, FakeTransport

from atlas_core.app import Core, CoreConfig
from atlas_core.egress import EgressGateway
from atlas_core.events import SafeLog

pytestmark = pytest.mark.criterion(11)


class ResearchWorld(World):
    def __init__(self, tmp, transport, live: bool, log: SafeLog) -> None:
        super().__init__(tmp)
        self.transport, self.live, self.log = transport, live, log
        self.clients.register("client-mac-0001", self.key.public_key(), owner=True)  # the research route is for an enrolled OWNER client

    def build(self) -> Core:
        gateway = None if self.transport is None else EgressGateway(self.transport, resolve=lambda host: [PUBLIC])
        core = Core(
            CoreConfig(
                data_dir=self.tmp / "core", socket_path=self.sock, task_key=KEY + "t", designation_key=KEY + "d", documents_key=KEY + "o", mail_key=KEY + "m", anchor=self.anchor,
                os_permissions=self.os, clients=self.clients, manifest=self.manifest, model_record_key=b"k" * 32, runtime=self.runtime, documents=("documents", self.docs),
                open_bootstrap=True, clock=self.clock, egress=gateway, live_network=self.live, log=self.log,
            )
        )  # fmt: skip
        self.cores.append(core)
        return core


def make(tmp_path, transport, live):
    events: list[dict] = []
    world = ResearchWorld(tmp_path, transport, live, SafeLog(lambda line: events.append(json.loads(line))))
    core = world.build()
    core.start()
    world.enable(core, "documents")
    world.wait_indexed(core)
    client = world.client()
    task_id = client.ask(*world.question("en-total"))
    client.result(task_id)
    return world, client, task_id, events


def test_public_research_is_off_by_default_even_with_a_gateway_configured(tmp_path):
    transport = FakeTransport()
    world, client, task_id, events = make(tmp_path, transport, live=False)
    try:
        with pytest.raises(Exception) as e:
            client.research(task_id, "museum opening hours Amsterdam")
        assert getattr(e.value, "code", "") == "forbidden" and transport.calls == []
        assert [(x["decision"], x["reason_code"]) for x in events if x["event"] == "egress.decision"] == [("deny", "provider_disabled")]
    finally:
        world.close()


def test_with_no_gateway_configured_nothing_can_be_sent(tmp_path):
    world, client, task_id, _ = make(tmp_path, None, live=True)
    try:
        with pytest.raises(Exception) as e:
            client.research(task_id, "museum opening hours Amsterdam")
        assert getattr(e.value, "code", "") == "forbidden"
    finally:
        world.close()


def test_a_public_query_returns_untrusted_data_with_provenance_and_does_not_change_the_answer(tmp_path):
    transport = FakeTransport()
    world, client, task_id, events = make(tmp_path, transport, live=True)
    try:
        core = world.cores[0]
        before = json.dumps(core.tasks.answer(task_id), sort_keys=True)
        result = client.research(task_id, "museum opening hours Amsterdam")
        assert (
            (result["trust"], result["authority"]) == ("untrusted", "none")
            and result["domain"] == "search.example.invalid"
            and len(result["content_hash"]) == 64
        )
        assert "museum opens at nine" in result["text"] and transport.calls == ["https://search.example.invalid/?q=museum%20opening%20hours%20Amsterdam"]
        assert json.dumps(core.tasks.answer(task_id), sort_keys=True) == before  # public content is never evidence: the answer and its citations are untouched
        assert [(x["decision"], x["reason_code"]) for x in events if x["event"] == "egress.decision"] == [("allow", "allowed")]
        assert "museum" not in json.dumps(events)  # the audit says where and what class, never the query or the page
    finally:
        world.close()


def test_a_query_that_repeats_the_tasks_private_context_is_refused_before_anything_is_sent(tmp_path):
    transport = FakeTransport()
    world, client, task_id, events = make(tmp_path, transport, live=True)
    try:
        question, _ = world.question("en-total")
        word = next(w for w in question.replace("?", "").split() if len(w) >= 5)
        with pytest.raises(Exception) as e:
            client.research(task_id, f"{word} lookup")
        assert getattr(e.value, "code", "") == "forbidden" and transport.calls == []
        denials = [(x["decision"], x["reason_code"]) for x in events if x["event"] == "egress.decision"]
        assert denials == [("deny", "leak_check")]
    finally:
        world.close()


def test_a_task_with_finance_or_health_in_scope_may_not_use_the_network_at_all(tmp_path):
    transport = FakeTransport()
    world, client, _, events = make(tmp_path, transport, live=True)
    try:
        record = client.ask(
            "What is the weather like today", ["finance"]
        )  # denied by policy (no grant) but the task exists, and its scope names a restricted domain
        with pytest.raises(Exception) as e:
            client.research(record, "weather Amsterdam tomorrow")
        assert getattr(e.value, "code", "") == "forbidden" and transport.calls == []
        assert [x["reason_code"] for x in events if x["event"] == "egress.decision"][-1] == "restricted_domain"
    finally:
        world.close()


def test_an_unknown_task_is_not_found_and_nothing_is_sent(tmp_path):
    transport = FakeTransport()
    world, client, _, _ = make(tmp_path, transport, live=True)
    try:
        with pytest.raises(Exception) as e:
            client.research("task-does-not-exist-0001", "museum opening hours")
        assert getattr(e.value, "code", "") == "not_found" and transport.calls == []
    finally:
        world.close()
