"""Stage 5: Finance, Health, Calendar, Contacts and Notes through a whole Core on the socket, synthetic records only. G-021: the local model may read an authorised restricted domain, only under a grant for
exactly that domain; nothing crosses domains; a revocation purges the index and what tasks derived from it; a task holding restricted data has no network; every figure is code-derived and verifiable."""

from __future__ import annotations

import json
import time

import pytest
from conftest import KEY
from test_app import World
from test_client import atlas_client
from test_egress import PUBLIC, FakeTransport

from atlas_core.app import Core, CoreConfig
from atlas_core.egress import EgressGateway
from atlas_core.finance_calc import summary_records, verify_summary
from atlas_core.records import InMemoryRecords, Record

pytestmark = pytest.mark.criterion(5)


def fin(rid, day, amount, category="rent", kind="expense", merchant="Landlord"):
    return Record(
        rid, "finance", day, f"{category} payment {rid}", {"amount": amount, "currency": "EUR", "kind": kind, "category": category, "merchant": merchant}
    )


FINANCE = [
    fin("f1", "2026-10-15", "412.30"),
    fin("f2", "2026-10-16", "0.10", "tea"),
    fin("f3", "2026-10-17", "0.20", "tea"),
    fin("i1", "2026-10-01", "3000.00", "salary", "income", "Employer"),
]
HEALTH = [
    Record(
        "h1", "health", "2026-10-12T08:00:00+00:00", "Resting heart rate", {"measure": "resting heart rate", "value": "61", "unit": "bpm", "source": "watch"}
    )
]
CALENDAR = [Record("c1", "calendar", "2026-10-20T09:00:00+00:00", "Dentist appointment", {"starts": "2026-10-20T09:00:00+00:00", "location": "Clinic Zuid"})]
CONTACTS = [Record("p1", "contacts", "2026-09-01T00:00:00+00:00", "Contact Jansen", {"name": "Jansen", "organisation": "Zuid Clinic", "phone": "0612345678"})]
NOTES = [Record("n1", "notes", "2026-10-18T00:00:00+00:00", "Passport reminder", {"text": "Renew the passport before the trip in March."})]


class DomainWorld(World):
    def __init__(self, tmp, transport=None, live=False) -> None:
        super().__init__(tmp)
        self.transport, self.live = transport, live
        self.sources = {
            "finance": InMemoryRecords("finance", FINANCE + summary_records(FINANCE)),
            "health": InMemoryRecords("health", HEALTH),
            "calendar": InMemoryRecords("calendar", CALENDAR),
            "contacts": InMemoryRecords("contacts", CONTACTS),
            "notes": InMemoryRecords("notes", NOTES),
        }
        self.clients.register("client-mac-0001", self.key.public_key(), owner=True)
        self.runtime.scripts.update(
            {
                "rent": {"mode": "honest", "answer": "The rent in October was 412.30 EUR.", "quote": "412.30", "lang": "en"},
                "tea-total": {"mode": "honest", "answer": "Tea in October totalled 0.30 EUR.", "quote": "0.30", "lang": "en"},
                "heart": {"mode": "honest", "answer": "Your resting heart rate was 61 bpm.", "quote": "61", "lang": "en"},
            }
        )

    def build(self) -> Core:
        gateway = None if self.transport is None else EgressGateway(self.transport, resolve=lambda host: [PUBLIC])
        core = Core(
            CoreConfig(
                data_dir=self.tmp / "core", socket_path=self.sock, task_key=KEY + "t", designation_key=KEY + "d", documents_key=KEY + "o", mail_key=KEY + "m", anchor=self.anchor,
                os_permissions=self.os, clients=self.clients, manifest=self.manifest, model_record_key=b"k" * 32, runtime=self.runtime, documents=("documents", self.docs),
                records={name: (source, KEY + name[:3]) for name, source in self.sources.items()}, open_bootstrap=True, clock=self.clock, egress=gateway, live_network=self.live,
            )
        )  # fmt: skip
        self.cores.append(core)
        return core

    def wait(self, core: Core, name: str) -> None:
        for _ in range(400):
            if core.indexes[name].coverage()["complete"]:
                return
            time.sleep(0.02)
        raise AssertionError(f"{name} indexing did not finish")

    def ask(self, case: str, question: str, scope: list[str]) -> dict:
        self.runtime.current = case
        return self.client().run_question(question, scope)


@pytest.fixture
def world(tmp_path):
    w = DomainWorld(tmp_path)
    yield w
    w.close()


def started(world) -> Core:
    core = world.build()
    core.start()
    return core


def test_a_domain_is_offered_for_designation_only_when_its_adapter_is_configured(tmp_path):
    bare = World(tmp_path)
    core = bare.build()
    try:
        assert core.designation.designable() == ["documents", "mail"]  # no Finance, Health, Calendar, Contacts or Notes: none has an adapter in this Core
    finally:
        bare.close()
    (tmp_path / "w").mkdir()
    world = DomainWorld(tmp_path / "w")
    try:
        core = started(world)
        assert core.designation.designable() == ["calendar", "contacts", "documents", "finance", "health", "mail", "notes"]
    finally:
        world.close()


def test_nothing_in_any_domain_is_read_until_the_owner_enables_it(world):
    core = started(world)
    time.sleep(0.3)
    assert all(index.coverage()["total"] == 0 for name, index in core.indexes.items() if name != "documents")
    assert [world.sources[n].reads for n in world.sources] == [0] * 5


def test_a_restricted_domain_answers_under_its_own_grant_with_an_exact_citation(world):
    core = started(world)
    world.enable(core, "finance", "health")
    world.wait(core, "finance")
    world.wait(core, "health")
    view = world.ask("rent", "What was the rent payment in October", ["finance"])
    assert "412.30" in view["text"] and view["citations"][0]["quote"] == "412.30"
    view = world.ask("heart", "What was my resting heart rate", ["health"])
    assert "61 bpm" in view["text"] and view["citations"][0]["quote"] == "61"


def test_a_code_computed_total_is_served_with_the_inputs_it_names_and_verifies(world):
    core = started(world)
    world.enable(core, "finance")
    world.wait(core, "finance")
    view = world.ask("tea-total", "What was the total tea spending in 2026-10", ["finance"])
    assert "0.30" in view["text"] and view["citations"][0]["quote"] == "0.30"
    summary = next(s for s in summary_records(FINANCE) if s.record_id == "sum-2026-10-tea")
    assert "f2" in summary.fields["note"] and "f3" in summary.fields["note"] and verify_summary(summary, FINANCE)


def test_no_domain_answers_for_another_domains_grant_and_nothing_crosses_over(world):
    core = started(world)
    world.enable(core, "documents", "calendar")
    world.wait_indexed(core)
    world.wait(core, "calendar")
    with pytest.raises(atlas_client.ClientError) as e:
        world.ask("rent", "What was the rent payment in October", ["finance"])  # finance was never enabled
    assert e.value.code == "source_denied" and world.sources["finance"].reads == 0
    view = world.ask("rent", "What was the rent payment in October", ["calendar", "documents"])  # asking elsewhere never reaches finance
    assert (
        view["citations"] == "No sources are cited." and world.sources["finance"].reads == 0 and world.sources["health"].reads == 0
    )  # the (scripted) model's claim is unproven: no finance passage reached it


def test_withdrawing_a_domain_purges_its_index_and_what_tasks_derived_from_it(world):
    core = started(world)
    world.enable(core, "finance")
    world.wait(core, "finance")
    client = world.client()
    world.runtime.current = "rent"
    task_id = client.ask("What was the rent payment in October", ["finance"])
    client.result(task_id)
    assert "412.30" in json.dumps(core.service.answer(task_id))
    core.designation.withdraw("finance", "withdraw-finance-1")
    for _ in range(100):
        if core.indexes["finance"].coverage()["total"] == 0:
            break
        time.sleep(0.05)
    assert core.indexes["finance"].coverage()["total"] == 0  # the index is emptied
    assert "412.30" not in json.dumps(core.service.answer(task_id))  # and the answer derived from it is withheld, not served


def test_a_task_with_a_restricted_domain_in_scope_has_no_network_even_when_live(tmp_path):
    transport = FakeTransport()
    world = DomainWorld(tmp_path, transport, live=True)
    try:
        core = started(world)
        world.enable(core, "finance", "notes")
        world.wait(core, "finance")
        client = world.client()
        world.runtime.current = "rent"
        restricted = client.ask("What was the rent payment in October", ["finance"])
        client.result(restricted)
        with pytest.raises(atlas_client.ClientError) as e:
            client.research(restricted, "weather Amsterdam tomorrow")
        assert e.value.code == "forbidden" and transport.calls == []
        world.wait(core, "notes")
        world.runtime.current = "rent"
        plain = client.ask("Passport reminder", ["notes"])
        client.result(plain)
        assert (
            client.research(plain, "museum opening hours Amsterdam")["trust"] == "untrusted" and len(transport.calls) == 1
        )  # a non-restricted task may, under the gate
    finally:
        world.close()


def test_contacts_and_calendar_are_labelled_by_the_policy_and_carry_their_fields_exactly(world):
    core = started(world)
    assert core.indexes["contacts"].label == "high" and core.indexes["calendar"].label == "medium" and core.indexes["finance"].label == "restricted"
    assert core.indexes["notes"].label == "medium" and core.indexes["health"].label == "restricted"


def test_a_migrated_legacy_finance_database_answers_through_the_core_under_the_finance_grant(tmp_path):
    import sqlite3

    from atlas_core.migration import migrate
    from atlas_core.recordstore import RecordStore, StoredRecords

    legacy = tmp_path / "finance.db"
    conn = sqlite3.connect(str(legacy))
    conn.executescript("CREATE TABLE transactions (id INTEGER PRIMARY KEY, day TEXT, amount_minor INTEGER, kind TEXT, category TEXT, note TEXT);")
    conn.execute("INSERT INTO transactions VALUES (1, '2026-10-15', 41230, 'expense', 'rent', 'October')")
    conn.commit()
    conn.close()
    (tmp_path / "w").mkdir()
    store = RecordStore(tmp_path / "w" / "finance-records.db", KEY + "f", frozenset({"finance"}))
    assert migrate(legacy, StoredRecords(store, "finance")).ok
    world = DomainWorld(tmp_path / "w")
    world.sources["finance"] = StoredRecords(store, "finance")
    try:
        core = started(world)
        world.enable(core, "finance")
        world.wait(core, "finance")
        view = world.ask("rent", "What was the rent transaction in October", ["finance"])
        assert "412.30" in view["text"] and view["citations"][0]["quote"] == "412.30"
    finally:
        world.close()
        store.close()


def test_the_finance_summary_is_computed_by_code_served_only_under_the_finance_grant_and_exact(tmp_path):
    from decimal import Decimal

    (tmp_path / "w").mkdir()
    world = DomainWorld(tmp_path / "w")
    september = [fin("s1", "2026-09-03", "100.10", "rent"), fin("s2", "2026-09-20", "50.20", "fuel")]
    world.sources["finance"] = InMemoryRecords("finance", FINANCE + september)
    try:
        core = started(world)
        owner = world.client()
        denied = owner.finance_summary()
        assert (
            denied["state"] == "denied" and denied["months"] == [] and denied["latest"] is None and world.sources["finance"].reads == 0
        )  # nothing read without the grant
        world.enable(core, "finance")
        out = owner.finance_summary()
        assert out["state"] == "ready" and out["computed_by_code"] is True and out["transaction_count"] == 6
        assert [(m["month"], m["total"]) for m in out["months"]] == [("2026-09", "150.30"), ("2026-10", "412.60")]
        latest = out["latest"]
        assert (
            latest["month"] == "2026-10"
            and latest["total"] == "412.60"
            and latest["categories"] == [{"category": "rent", "total": "412.30"}, {"category": "tea", "total": "0.30"}]
        )
        assert (latest["previous_total"], latest["delta"], latest["percent"]) == ("150.30", "262.30", "174.5")  # 262.30 / 150.30, rounded half-up to one place
        assert Decimal(latest["total"]) - Decimal(latest["previous_total"]) == Decimal(latest["delta"])
        assert sum(Decimal(c["total"]) for c in latest["categories"]) == Decimal(latest["total"])  # the categories add up to the month, exactly
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

        member_key = Ed25519PrivateKey.generate()
        world.clients.register("member-device-0001", member_key.public_key())
        member = atlas_client.AtlasClient(str(world.sock), member_key, "member-device-0001", clock=world.clock)
        with pytest.raises(atlas_client.ClientError) as e:
            member.finance_summary()  # the route is for the owner client only
        assert e.value.code == "forbidden"
    finally:
        world.close()


def test_a_core_without_a_finance_source_has_no_finance_route_and_an_empty_one_says_so(tmp_path):
    (tmp_path / "w").mkdir()
    world = DomainWorld(tmp_path / "w")
    world.sources["finance"] = InMemoryRecords("finance", [])
    try:
        core = started(world)
        world.enable(core, "finance")
        assert world.client().finance_summary()["state"] == "empty"
    finally:
        world.close()
