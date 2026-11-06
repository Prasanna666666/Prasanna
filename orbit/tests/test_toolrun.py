"""Running one tool for the one assistant: arguments are coerced, failures come back as data, and a few tools are off limits."""

from orbit import toolrun
from orbit.modules import money, tasks


def test_string_numbers_are_coerced(conn):
    _out, err = toolrun.run_tool(conn, "add_transaction", {"amount": "1,250.50", "category": "food"})
    assert not err and money.summary(conn, {})["spent"] == 1250.5
    tid = tasks.add_task(conn, {"title": "x"})["id"]
    assert not toolrun.run_tool(conn, "complete_task", {"id": str(tid)})[1]


def test_tool_errors_go_back_to_the_model(conn):
    text, err = toolrun.run_tool(conn, "add_task", {"title": "x", "due": "garbage"})
    assert err and "error" in text
    assert toolrun.run_tool(conn, "nope", {})[1]
    assert not toolrun.run_tool(conn, "add_task", '{"title": "json string args"}')[1]


def test_a_tool_outside_the_allowed_set_is_refused(conn):
    assert toolrun.run_tool(conn, "add_task", {"title": "x"}, frozenset({"list_tasks"}))[1]


def test_no_assistant_may_delete_an_imported_payment():
    assert "delete_transaction" in toolrun.NEVER_BY_AI
