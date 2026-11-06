"""When the model cannot read statements, that shows up before the first file or after the first few, never after dozens."""

import json

import pytest
from kit import extract

from finance import canary, tables
from finance.modules import money
from tests.test_finance import GOOD, LAYOUT, _load

SAMPLE_MARK = "Albert Heijn ⟂"  # the built-in sample has this description cell exactly; the test statements say "Albert Heijn Utrecht"


class Model:
    """Describes the sample statement correctly (or not), and every other statement as `others`."""

    def __init__(self, sample_ok=True, others_ok=True):
        self.sample_ok, self.others_ok, self.calls = sample_ok, others_ok, 0

    def chat(self, model, messages, tools=None, schema=None, **kw):
        self.calls += 1
        system = messages[0]["content"]
        if system == extract.KIND_PROMPT:
            return {"content": json.dumps({"kind": "bank_statement"})}
        ok = self.sample_ok if any(SAMPLE_MARK in m["content"] for m in messages) else self.others_ok
        return {"content": json.dumps(LAYOUT if ok else {"header_line": 0, "roles": ["date"], "date_format": "%d-%m-%Y"})}


@pytest.fixture(autouse=True)
def fresh_model_check():
    canary._model_checked.clear()


def pending(conn):
    return len(money._pending_documents(conn))


def load_many(conn, tmp_path, n):
    for i in range(n):
        _load(conn, tmp_path, f"statement-number-{i:02d}.pdf", GOOD)


def test_a_model_that_cannot_read_a_sample_statement_stops_everything_before_any_file_is_read(conn, tmp_path):
    load_many(conn, tmp_path, 5)
    model = Model(sample_ok=False)
    r = money.import_statements(conn, client=model, model="m")
    assert r["files"] == 0 and r["needs_check"] == [] and "Nothing was read" in r["problems"][0] and "not with your files" in r["problems"][0]
    assert conn.execute("SELECT COUNT(*) FROM statement_files").fetchone()[0] == 0 and pending(conn) == 5  # no file was blamed: all are still waiting
    assert model.calls <= 2  # the check took a couple of calls, then it stopped


def test_after_three_files_in_a_row_fail_the_run_stops_and_none_of_them_is_remembered_as_failed(conn, tmp_path):
    load_many(conn, tmp_path, 8)
    seen: list[str] = []
    r = money.import_statements(conn, client=Model(others_ok=False), model="m", progress=seen.append)
    assert r["files"] == 0 and r["needs_check"] == [] and "Stopped after 3 files" in r["problems"][0] and "model is struggling" in r["problems"][0]
    assert conn.execute("SELECT COUNT(*) FROM statement_files").fetchone()[0] == 0 and pending(conn) == 8  # all eight will be tried at the next Update
    assert not any("could not be read so far" in m for m in seen[:1])


def test_progress_says_how_many_could_not_be_read_so_far(conn, tmp_path):
    load_many(conn, tmp_path, 6)
    seen: list[str] = []

    class Flaky(Model):
        def chat(self, model, messages, tools=None, schema=None, **kw):
            if not any(SAMPLE_MARK in m["content"] for m in messages) and messages[0]["content"] != extract.KIND_PROMPT:
                self.n = getattr(self, "n", 0) + 1
                self.others_ok = self.n in (3, 4)  # the first two files and then others fail, but never three in a row
            return super().chat(model, messages, tools, schema, **kw)

    money.import_statements(conn, client=Flaky(), model="m", progress=seen.append)
    assert any("could not be read so far" in m for m in seen)


def test_a_good_model_passes_the_check_once_and_everything_is_read(conn, tmp_path):
    load_many(conn, tmp_path, 3)
    model = Model()
    r = money.import_statements(conn, client=model, model="m")
    assert r["files"] == 3 and r["problems"] == [] and r["needs_check"] == []
    assert canary.model_check(model, "m") is None  # remembered: the next check costs no model call
    calls = model.calls
    assert canary.model_check(model, "m") is None and model.calls == calls


def test_the_sample_the_check_uses_is_itself_read_exactly_by_code():
    layout = tables.Layout(**LAYOUT)
    read = tables.parse_table(canary._table(canary.SAMPLE), layout)
    assert read.status == "verified" and len(read.txns) == 3
