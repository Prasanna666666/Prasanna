"""Stage 7: health checks, diagnostics that carry no personal content, and a permission reset that purges."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
from conftest import SENTINEL_DOC
from test_app import World

from atlas_core.health import diagnostics, health, redact, reset_permissions

pytestmark = pytest.mark.criterion(9)
ROOMY = lambda path: (1000 * 2**30, 100 * 2**30, 900 * 2**30)  # noqa: E731  (a disk with plenty of room, whatever this machine has)


@pytest.fixture
def world(tmp_path):
    w = World(tmp_path)
    yield w
    w.close()


def a_core_that_has_answered(world):
    core = world.build()
    core.start()
    world.enable(core, "documents")
    world.wait_indexed(core)
    world.client().run_question(*world.question("en-total"))
    return core


def test_health_names_each_check_and_reports_codes_not_content(world):
    core = a_core_that_has_answered(world)
    checks = health(core, ROOMY)
    assert [(c.name, c.status) for c in checks] == [("designation_store", "ok"), ("index_documents", "ok"), ("disk", "ok")]
    assert all(c.code == "" for c in checks)


def test_diagnostics_hold_no_question_passage_file_name_key_or_home_path(world, tmp_path):
    core = a_core_that_has_answered(world)
    text = diagnostics(core, home=tmp_path, versions={"core": "0.1.0"}, usage=ROOMY)
    document = json.loads(text)
    assert set(document) == {"versions", "checks", "storage", "indexes"} and document["versions"]["core"] == "0.1.0"
    assert document["indexes"]["documents"]["complete"] is True
    for private in ("What is the total due", "1250.50", "invoice_en", SENTINEL_DOC, str(tmp_path), "ACME-2041", "client-mac-0001", "primary-1"):
        assert private not in text, private
    for name in world.docs.iterdir():
        assert name.name not in text


def test_redaction_is_a_second_line_of_defence_for_anything_that_slipped_in():
    home = Path("/Users/someone")
    text = redact(
        "opened /Users/someone/Documents/tax.pdf for alex@example.invalid card 4929 1234 5678 9010 token EXAMPLE-LONG-TOKEN-abcdefghijklmnop0123", home
    )
    assert "/Users/someone" not in text and "alex@" not in text and "4929" not in text and "EXAMPLE-LONG" not in text and "~/Documents/tax.pdf" in text


def test_a_permission_reset_withdraws_every_grant_and_purges_what_was_derived(world):
    core = a_core_that_has_answered(world)
    task_ids = list(core.tasks.ids_in(("completed", "partially_completed")))
    assert task_ids and core.indexes["documents"].coverage()["total"] > 0
    counter = iter(range(10_000))
    assert reset_permissions(core.designation, lambda t: f"reset-{t}-{next(counter):06d}") == ["documents"]
    for _ in range(100):
        if core.indexes["documents"].coverage()["total"] == 0:
            break
        time.sleep(0.05)
    assert core.designation.lifecycle("documents") != "enabled" and core.indexes["documents"].coverage()["total"] == 0
    assert "1250.50" not in json.dumps(core.service.answer(task_ids[0]))
    assert reset_permissions(core.designation, lambda t: f"again-{t}-{next(counter):06d}") == []  # nothing left to reset


def test_an_index_that_is_paused_or_incomplete_is_degraded_even_with_nothing_pending_or_failed(world):
    """ATLAS-HEALTH-045: health reads the whole coverage state, not only the pending and failed counts."""
    core = a_core_that_has_answered(world)
    index = core.indexes["documents"]
    real = index.coverage

    def view(**over):
        return lambda: {**real(), "failed": 0, "pending": 0, **over}

    def status():
        return next((c.status, c.code) for c in health(core, ROOMY) if c.name == "index_documents")

    index.coverage = view(complete=True, paused=None)
    assert status() == ("ok", "")
    index.coverage = view(complete=False, paused="disk_critical")
    assert status() == ("degraded", "index_paused")
    index.coverage = view(complete=False, paused=None)
    assert status() == ("degraded", "incomplete")
    index.coverage = view(complete=True, paused=None, total=0)  # a finished scan of an empty index is healthy
    assert status() == ("ok", "")
