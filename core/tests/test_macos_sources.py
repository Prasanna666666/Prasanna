"""The owner's Calendar, Contacts, Notes and Photos on macOS as read-only sources: permission is the platform's, asked for only when the owner turns the source on, and nothing is read without it.

Linux uses a fake platform (the seam); the tests marked macOS run the real frameworks on a hosted runner, where no permission has been granted, so they prove the real status calls, the denied path and
the honesty of the answers, not a read of real personal data.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime

import pytest
from test_domains import DomainWorld, started

from atlas_core.access import GRANTED, MISSING, UNKNOWN
from atlas_core.consent import ConsentService
from atlas_core.macos_sources import DOMAINS, MacPermissions, NativeRecords, ObjcPlatform
from atlas_core.records import Record

pytestmark = pytest.mark.criterion(5)
NOW = datetime(2026, 10, 20, 12, 0, tzinfo=UTC)


class FakePlatform:
    """SYNTHETIC. Status per domain, and the records each domain would give."""

    def __init__(self, status=GRANTED, records=None):
        self.states = dict.fromkeys(DOMAINS, status)
        self.records = records or {}
        self.requested, self.fetches = [], 0

    def status(self, domain):
        state = self.states[domain]
        if isinstance(state, Exception):
            raise state
        return state

    def request(self, domain):
        self.requested.append(domain)

    def fetch(self, domain, now):
        self.fetches += 1
        if self.states[domain] != GRANTED:
            raise PermissionError(domain)
        return list(self.records.get(domain, []))


class Inner:
    def current(self, source_type):
        return ("inner", source_type)


def event(rid, title, starts):
    return Record(rid, "calendar", starts, title, {"starts": starts, "location": "Clinic Zuid"})


def test_permission_evidence_is_the_platforms_and_anything_unclear_is_unknown():
    platform = FakePlatform()
    provider = MacPermissions(platform, Inner(), lambda: NOW)
    assert provider.current("calendar").state == GRANTED
    platform.states["calendar"] = MISSING
    assert provider.current("calendar").state == MISSING
    platform.states["calendar"] = "something-new"
    assert provider.current("calendar").state == UNKNOWN
    platform.states["calendar"] = OSError("boom")
    assert provider.current("calendar").state == UNKNOWN  # no answer is no evidence
    assert provider.current("documents") == ("inner", "documents")  # other sources keep their own provider


def test_a_denied_or_undecided_permission_gives_an_empty_source_and_a_granted_one_lists_newest_first():
    platform = FakePlatform(records={"calendar": [event("a", "Old", "2026-10-01T09:00:00+00:00"), event("b", "New", "2026-10-30T09:00:00+00:00")]})
    source = NativeRecords(platform, "calendar", lambda: NOW)
    page = source.list_page(None, 10)
    assert [i.message_id for i in page.items] == ["b", "a"] and source.read("b")["subject"] == "New"
    platform.states["calendar"] = MISSING
    assert source.list_page(None, 10).items == [] and source.read("b") is None  # nothing left over from before the permission was lost


def test_a_permission_request_is_made_once_per_source_when_the_owner_turns_it_on_and_a_failure_changes_nothing(tmp_path):
    (tmp_path / "w").mkdir()
    world = DomainWorld(tmp_path / "w")
    platform = FakePlatform()
    world.sources["calendar"] = NativeRecords(platform, "calendar", world.clock)
    try:
        core = started(world)
        calls = []
        service = ConsentService(core.designation, core.access, core.indexes, calls.append)
        service.enable(["calendar", "contacts"], "req-0000000001")
        assert calls == ["calendar", "contacts"]
        boom = ConsentService(core.designation, core.access, core.indexes, lambda _s: 1 / 0)
        assert boom.enable(["notes"], "req-0000000002")["grants"]  # the owner's choice stands even if the system could not be asked
    finally:
        world.close()


def test_the_owners_calendar_answers_through_the_core_only_under_a_grant_and_the_platform_permission(tmp_path):
    (tmp_path / "w").mkdir()
    world = DomainWorld(tmp_path / "w")
    platform = FakePlatform(MISSING, {"calendar": [event("c1", "Dentist appointment", "2026-10-20T09:00:00+00:00")]})
    world.sources["calendar"] = NativeRecords(platform, "calendar", world.clock)
    world.os._state["calendar"] = GRANTED
    try:
        core = started(world)
        world.enable(core, "calendar")
        assert platform.fetches == 0  # the platform says no: nothing was read
        platform.states["calendar"] = GRANTED
        world.wait(core, "calendar")
        assert platform.fetches >= 1
    finally:
        world.close()


@pytest.mark.skipif(sys.platform != "darwin", reason="the real frameworks exist only on macOS")
def test_the_real_frameworks_report_a_status_and_refuse_to_read_without_permission():
    platform = ObjcPlatform()
    for domain in DOMAINS:
        state = platform.status(domain)
        assert state in (GRANTED, MISSING, UNKNOWN)
        if state != GRANTED:
            with pytest.raises(PermissionError):
                platform.fetch(domain, NOW)  # denied or undecided: nothing is read
        else:
            try:
                records = platform.fetch(domain, NOW)
            except OSError:
                continue  # the system did not answer in time (Notes can be slow to start): no data and no hang
            assert all(r.domain == domain for r in records)


def test_a_system_that_does_not_answer_is_an_unavailable_source_not_an_empty_one(tmp_path):
    """ATLAS-MAC-090: a transient failure never becomes a successful empty snapshot; only a real denial or a genuinely empty source may empty the index."""
    from conftest import KEY
    from test_mail import AllowAll

    from atlas_core.access import FakeOSPermissions  # noqa: F401
    from atlas_core.mail import MailError, MailIndex

    platform = FakePlatform(records={"notes": [event("n1", "Quote", "2026-10-01T09:00:00+00:00"), event("n2", "Other", "2026-10-02T09:00:00+00:00")]})
    source = NativeRecords(platform, "notes", lambda: NOW)
    index = MailIndex(tmp_path / "n.db", KEY, source, "notes", access=AllowAll())
    index.scan()
    while index.run(10)["pending"]:
        pass
    assert index.coverage()["searched"] == 2
    real_fetch = platform.fetch
    platform.fetch = lambda domain, now: (_ for _ in ()).throw(OSError("notes_timeout"))
    with pytest.raises(MailError):
        index.scan()  # stops before anything is written
    assert index.coverage()["searched"] == 2 and index.coverage()["complete"] is False  # nothing lost, and the scan is not reported finished
    platform.fetch = lambda domain, now: (_ for _ in ()).throw(PermissionError("notes"))
    index.scan()  # an explicit denial is an empty source: the access layer withdraws the grant and the derived data goes
    platform.fetch = real_fetch
    platform.records["notes"] = []  # a genuinely empty source after a successful read
    index.scan()
    assert index.coverage()["searched"] == 0 and index.coverage()["complete"] is True
