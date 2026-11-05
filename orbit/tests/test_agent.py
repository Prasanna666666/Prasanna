from orbit import agent
from orbit.modules import money, tasks


class FakeLocalModel:
    """Scripted model. Sends a numeric arg as a string, like small models do."""

    def __init__(self):
        self.calls = []

    def chat(self, model, messages, tools=None):
        self.calls.append(messages)
        if len(self.calls) == 1:
            return {
                "content": "",
                "tool_calls": [{"function": {"name": "add_task", "arguments": {"title": "Call Amma", "due": "2026-11-09", "recurrence": "weekly"}}}],
            }
        return {"content": "Done - every week.", "tool_calls": []}


def test_chat_runs_tool_loop(conn):
    hist = []
    out = agent.chat(conn, hist, "remind me weekly to call Amma", client=FakeLocalModel(), model="m")
    assert out == "Done - every week."
    assert tasks.list_tasks(conn, {})[0]["title"] == "Call Amma"
    assert [h["role"] for h in hist] == ["user", "assistant", "tool", "assistant"]


def test_string_numbers_are_coerced(conn):
    _out, err = agent.run_tool(conn, "add_transaction", {"amount": "1,250.50", "category": "food"})
    assert not err and money.summary(conn, {})["spent"] == 1250.5
    tid = tasks.add_task(conn, {"title": "x"})["id"]
    assert not agent.run_tool(conn, "complete_task", {"id": str(tid)})[1]


def test_tool_errors_go_back_to_model(conn):
    text, err = agent.run_tool(conn, "add_task", {"title": "x", "due": "garbage"})
    assert err and "error" in text
    assert agent.run_tool(conn, "nope", {})[1]
    assert not agent.run_tool(conn, "add_task", '{"title": "json string args"}')[1]
