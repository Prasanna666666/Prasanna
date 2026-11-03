from types import SimpleNamespace as NS

from saathi import agent
from saathi.modules import tasks


class FakeClient:
    """Scripted model: first calls add_task, then (after seeing the result) answers."""

    def __init__(self):
        self.calls = []
        self.messages = self

    def create(self, **kw):
        self.calls.append(kw)
        if len(self.calls) == 1:
            return NS(content=[{"type": "tool_use", "id": "t1", "name": "add_task",
                                "input": {"title": "Call Amma", "due": "2026-11-09", "recurrence": "weekly"}}])
        return NS(content=[{"type": "text", "text": "Done - every week."}])


def test_chat_runs_tool_loop(conn):
    hist = []
    out = agent.chat(conn, hist, "remind me weekly to call Amma", client=FakeClient(), model="m")
    assert out == "Done - every week."
    assert tasks.list_tasks(conn, {})[0]["title"] == "Call Amma"
    assert hist[2]["content"][0]["type"] == "tool_result" and not hist[2]["content"][0]["is_error"]


def test_tool_errors_go_back_to_model(conn):
    text, err = agent.run_tool(conn, "add_task", {"title": "x", "due": "garbage"})
    assert err and "error" in text
    assert agent.run_tool(conn, "nope", {})[1]
