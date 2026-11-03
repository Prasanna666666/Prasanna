import pytest

from orbit import agent, agents, llm, tagging
from orbit.modules import ALL, notes, people, tools


@pytest.mark.parametrize("text,expected", [
    ("spent 450 on groceries", "money"),
    ("remind me to call Amma every Sunday", "tasks"),
    ("when is dad's birthday", "family"),
    ("note: wifi password is on the router", "notes"),
    ("give me my morning brief", "briefing"),
    ("what's due today", "tasks"),
])
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
    tool_msg = [m for m in c.calls[1][0] if m["role"] == "tool"][0]
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
