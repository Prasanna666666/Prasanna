"""Not every message is a photo search: greetings, thanks and general questions get a normal conversational answer."""

from datetime import date

from aperture.agent.llm import LLMError, OllamaClient
from aperture.agent.planner import PlanResult
from aperture.agent.schema import Plan
from aperture.agent.service import CHAT_SYSTEM, AgentService
from aperture.config import Settings


class FakePlanner:
    def __init__(self, plan):
        self.plan_obj = plan
        self.seen = []

    def plan(self, request, ctx):
        self.seen.append(request)
        return PlanResult(plan=self.plan_obj)


def service(plan, chatter=None):
    def boom():
        raise AssertionError("a chat message must never run a photo search")

    return AgentService(FakePlanner(plan), boom, lambda: [], today=lambda: date(2026, 11, 3), chatter=chatter)


def test_chat_intent_gets_a_conversational_reply_with_history_and_no_photos():
    seen = {}

    def chatter(request, history):
        seen.update(request=request, history=history)
        return "RAW keeps all the sensor data; JPEG is a smaller, processed copy."

    reply = service(Plan(intent="chat"), chatter).ask(
        "what is the difference between RAW and JPEG?", history=[("user", "hi"), ("assistant", "Hello!")]
    )
    assert reply.kind == "chat" and "JPEG" in reply.text and len(reply.ids) == 0
    assert seen["history"] == [("user", "hi"), ("assistant", "Hello!")] and "RAW and JPEG" in seen["request"]


def test_chat_without_a_chatter_falls_back_to_the_plan_message():
    reply = service(Plan(intent="chat", message="Hi! Ask me for photos.")).ask("tell me about cameras")
    assert reply.kind == "chat" and reply.text == "Hi! Ask me for photos."


def test_chat_model_errors_are_reported_not_raised():
    def chatter(request, history):
        raise LLMError("Ollama is not reachable")

    reply = service(Plan(intent="chat"), chatter).ask("tell me about cameras")
    assert reply.kind == "error" and "not reachable" in reply.text


def test_empty_chat_reply_uses_the_fallback():
    assert service(Plan(intent="chat"), lambda r, h: "").ask("tell me about cameras").text.startswith("Ask me to find photos")


def test_complete_chat_sends_the_conversation_and_stays_in_one_context(monkeypatch):
    sent = []
    monkeypatch.setattr(
        OllamaClient, "_request", lambda self, path, payload=None: sent.append(payload) or {"message": {"content": " Sure! "}}
    )
    c = OllamaClient("http://127.0.0.1:11434", "ministral-3:3b")
    out = c.complete_chat(
        CHAT_SYSTEM,
        [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "Hello"},
            {"role": "user", "content": "tell me a joke"},
        ],
    )
    p = sent[0]
    assert out == "Sure!" and p["messages"][0] == {"role": "system", "content": CHAT_SYSTEM} and len(p["messages"]) == 4
    assert p["options"]["num_ctx"] == 4096 and p["options"]["num_predict"] == 400 and "format" not in p


def test_instant_photo_preview_is_off_by_default_and_guarded():
    assert Settings().quick_preview is False
    import inspect

    from aperture.ui.views import chat

    src = inspect.getsource(chat.render)
    assert "if ctx.settings.quick_preview:" in src and "history=turns" in src


def test_chat_voice_is_natural_short_and_photo_focused_with_examples():
    assert "photo app" in CHAT_SYSTEM and "one or two short sentences" in CHAT_SYSTEM and "without emojis" in CHAT_SYSTEM
    assert "never claim to have found any" in CHAT_SYSTEM and "cannot browse the web" in CHAT_SYSTEM
    assert (
        "User: Hello\nAssistant: " in CHAT_SYSTEM
        and "like a thoughtful friend" not in CHAT_SYSTEM
        and "talk about anything" not in CHAT_SYSTEM
    )


def test_the_real_agent_is_wired_for_conversation(tmp_path, monkeypatch):
    """Builds the agent exactly as the app does (this would have caught a missing import)."""
    from aperture.bootstrap import AppContext
    from aperture.config import Paths

    monkeypatch.setenv("APERTURE_ALLOW_INTERNAL", "1")
    paths = Paths(tmp_path / "Expansion")
    paths.ensure()
    ctx = AppContext(paths)
    agent = ctx.service()
    assert isinstance(agent, AgentService) and agent._chatter is not None
    sent = []
    monkeypatch.setattr(
        OllamaClient, "_request", lambda self, path, payload=None: sent.append(payload) or {"message": {"content": "Hi there!"}}
    )
    assert agent._chatter("hello", [("user", "x"), ("assistant", "y")]) == "Hi there!"
    assert [m["role"] for m in sent[0]["messages"]] == ["system", "user", "assistant", "user"]


def test_the_date_comes_before_the_examples_and_is_not_glued_to_one(tmp_path, monkeypatch):
    from datetime import date

    from aperture.agent.llm import OllamaClient
    from aperture.bootstrap import AppContext
    from aperture.config import Paths

    sent = []
    monkeypatch.setattr(
        OllamaClient, "_request", lambda self, path, payload=None: sent.append(payload) or {"message": {"content": "ok"}}
    )
    monkeypatch.setenv("APERTURE_ALLOW_INTERNAL", "1")
    paths = Paths(tmp_path / "Expansion")
    paths.ensure()
    ctx = AppContext(paths)
    ctx.service()._chatter("hello", [])
    system = sent[0]["messages"][0]["content"]
    assert system.startswith(f"Today's date is {date.today():%A %d %B %Y}.\nYou are the Photos assistant")
    assert system.rstrip().endswith("than a JPEG.")  # the last example answer ends cleanly: nothing glued after it
