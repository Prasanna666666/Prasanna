import pytest

from orbit import agent, agents, llm, tagging
from orbit.modules import ALL, notes, people, tools


@pytest.mark.parametrize(
    "text,expected",
    [
        ("spent 450 on groceries", "money"),
        ("remind me to call Amma every Sunday", "tasks"),
        ("when is dad's birthday", "family"),
        ("note: wifi password is on the router", "notes"),
        ("give me my morning brief", "briefing"),
        ("what's due today", "tasks"),
    ],
)
def test_keyword_routing(text, expected):
    assert agents.route(text) == expected


def test_ambiguous_uses_classifier_else_general():
    assert agents.route("hello there") == "general"
    assert agents.route("hello there", classify=lambda t, n: "Money.") == "money"
    assert agents.route("hello there", classify=lambda t, n: "banana") == "general"


def test_agent_tools_exist_and_are_least_privilege():
    all_tools = set(tools(ALL))
    for a in agents.AGENTS:
        assert a.tools <= all_tools, a.name
    assert "delete_person" not in agents.BY_NAME["money"].tools
    assert "add_transaction" not in agents.BY_NAME["family"].tools


class Scripted:
    """Records what it was offered; first asks for a tool outside the agent's permissions."""

    def __init__(self, first_call):
        self.first, self.calls = first_call, []

    def chat(self, model, messages, tools=None):
        self.calls.append((messages, tools))
        if len(self.calls) == 1:
            return {"content": "", "tool_calls": [{"function": {"name": self.first, "arguments": {"id": 1}}}]}
        return {"content": "ok", "tool_calls": []}


def test_agent_only_sees_and_may_call_its_own_tools(conn):
    people.add_person(conn, {"name": "Amma"})
    c = Scripted("delete_person")  # a money question must not be able to delete people
    trace = []
    agent.chat(conn, [], "I spent 100 on food", client=c, model="m", trace=trace)
    offered = {t["function"]["name"] for t in c.calls[0][1]}
    assert offered == set(agents.BY_NAME["money"].tools)
    assert trace[0]["agent"] == "money"
    assert conn.execute("SELECT COUNT(*) FROM people").fetchone()[0] == 1  # still there
    tool_msg = next(m for m in c.calls[1][0] if m["role"] == "tool")
    assert "not available" in tool_msg["content"]


def test_rule_tags_and_people(conn):
    people.add_person(conn, {"name": "Ramesh Kumar", "relation": "father"})
    notes.add_note(conn, {"body": "Ramesh BP tablet after breakfast, doctor visit Friday"})
    notes.add_note(conn, {"body": "random thought", "tags": "mine"})
    notes.add_note(conn, {"body": "zzz"})
    assert tagging.autotag_notes(conn) == 1
    got = {n["body"][:6]: n["tags"] for n in notes.search_notes(conn, {})}
    assert got["Ramesh"] == "family,health,ramesh"
    assert got["random"] == "mine"  # user tags are never overwritten


def test_model_tags_limited_to_vocabulary(conn):
    class M:
        def chat(self, model, messages, tools=None):
            return {"content": 'Sure! ["travel", "hacked", "ideas"]'}

    notes.add_note(conn, {"body": "zzz"})
    assert tagging.autotag_notes(conn, M(), "m") == 1
    assert notes.search_notes(conn, {})[0]["tags"] == "ideas,travel"


class FakeOllama(llm.OllamaClient):
    def __init__(self, names):
        self.names = names

    def installed(self):
        return self.names


def test_model_resolution_is_mistral_only():
    assert FakeOllama(["ministral-3:3b"]).resolve("ministral-3:3b") == "ministral-3:3b"
    assert FakeOllama(["ministral-3:3b-instruct-q4"]).resolve("ministral-3:3b") == "ministral-3:3b-instruct-q4"
    for other in (["llama3.2:3b"], ["qwen2.5:3b", "moondream"], []):  # never falls back to another model family
        with pytest.raises(RuntimeError, match="ollama pull ministral-3:3b"):
            FakeOllama(other).resolve("ministral-3:3b")
    with pytest.raises(RuntimeError, match="Several"):
        FakeOllama(["ministral-3:3b-a", "ministral-3:3b-b"]).resolve("ministral-3:3b")


def test_same_context_and_keepalive_as_aperture_so_one_loaded_model_is_shared(monkeypatch):
    """Ollama reloads a model when num_ctx changes; Orbit and Aperture must send the same value (4096)."""
    seen = {}
    monkeypatch.setattr(llm.OllamaClient, "_call", lambda self, path, body=None, timeout=300: seen.update(body=body) or {"message": {}})
    llm.OllamaClient("http://127.0.0.1:11434").chat("ministral-3:3b", [], None)
    assert seen["body"]["options"]["num_ctx"] == 4096 and seen["body"]["keep_alive"] == "2m"


def test_small_talk_gets_a_short_reply_with_no_tools_and_no_big_prompt(conn):
    from orbit import agent

    seen = []

    class Client:
        def chat(self, model, messages, tools=None, **kw):
            seen.append((messages[0]["content"], tools))
            return {"content": "chat" if "Reply with exactly one word" in messages[0]["content"] else "Hello! How can I help?"}

    out = agent.chat(conn, [], "hi", client=Client(), model="m")
    assert out == "Hello! How can I help?"
    assert len(seen) == 2 and seen[1][1] == [] and len(seen[1][0]) < 400  # the answer call carries no tool definitions


def test_a_reply_never_runs_past_its_time_and_says_so(conn, monkeypatch):
    from orbit import agent

    class Stuck:
        def chat(self, model, messages, tools=None, **kw):
            raise llm.Slow("out of time")

    reply = agent.chat(conn, [], "what do you make of my finances overall?", client=Stuck(), model="m")
    assert "more thinking than" in reply


def test_the_client_refuses_to_start_a_call_after_the_deadline(monkeypatch):
    import time as _t

    c = llm.OllamaClient("http://127.0.0.1:11434")
    c.deadline = _t.monotonic() - 1
    with pytest.raises(llm.Slow):
        c._call("/api/chat", {})
