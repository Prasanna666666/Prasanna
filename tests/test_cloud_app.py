"""The whole cloud chain: client -> gateway -> provider, over real HTTP. The provider is a recorder: it proves what leaves the Mac."""

import json
import threading
from datetime import date
from types import SimpleNamespace

import numpy as np
import pytest

from aperture.agent.service import AgentService
from aperture.agent.toolagent import ToolAgent
from aperture.cloud import gateway as gw
from aperture.cloud.client import CloudInterpreter
from tests.test_cloud import Provider

PEOPLE = ["Anna Verhoeven"]
PLACES = ["Nagoya", "Eindhoven"]


@pytest.fixture()
def chain(tmp_path):
    provider = Provider('{"tool": "find_photos", "arguments": {"people": ["<PERSON_1>"], "places": ["<PLACE_1>"], "what": "hockey stadium"}}')
    gateway = gw.Gateway("sk-secret", gw.Usage(tmp_path / "usage.json"), provider_url=provider.url)
    server = gw.ThreadingHTTPServer(("127.0.0.1", 0), gw.make_handler(gateway, 0))
    port = server.server_port
    server.RequestHandlerClass = gw.make_handler(gateway, port)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield SimpleNamespace(provider=provider, port=port, gateway=gateway)
    server.shutdown()
    provider.stop()


def test_the_provider_never_hears_a_name_or_a_library_fact_and_the_names_are_restored_locally(chain):
    cloud = CloudInterpreter(chain.port, lambda: PEOPLE, lambda: PLACES)
    decided = cloud("photos of Anna Verhoeven at the Nagoya hockey stadium", True)
    assert decided == {"name": "find_photos", "arguments": {"people": ["Anna Verhoeven"], "places": ["Nagoya"], "what": "hockey stadium"}}
    everything = json.dumps(chain.provider.seen[0][1])
    for private in ("Anna", "Verhoeven", "Nagoya", "Eindhoven", "sk-secret".upper()):
        assert private not in everything
    assert "<PERSON_1>" in everything and "<PLACE_1>" in everything and "hockey stadium" in everything
    request = json.loads(json.loads(everything)["messages"][0]["content"])
    assert set(request) == {"today", "photos_already_on_screen", "request"}  # no photos, no counts, no library facts, no history, nothing else


def test_an_invented_placeholder_never_reaches_the_search(chain):
    chain.provider.text = '{"tool": "find_photos", "arguments": {"places": ["<PLACE_9>", "<PLACE_1>"], "people": ["<PERSON_7>"]}}'
    decided = CloudInterpreter(chain.port, lambda: PEOPLE, lambda: PLACES)("Nagoya", False)
    assert decided["arguments"] == {"places": ["Nagoya"]}


def test_when_the_gateway_is_down_or_gives_no_plan_the_local_model_decides(chain):
    assert CloudInterpreter(9, lambda: PEOPLE, lambda: PLACES)("dogs", False) is None  # nothing listens: no error, just None
    chain.provider.text = '{"tool": "none"}'
    assert CloudInterpreter(chain.port, lambda: PEOPLE, lambda: PLACES)("how are you", False) is None


def test_the_agent_uses_the_cloud_plan_and_falls_back_to_the_local_model(tmp_path):
    seen = []

    def make_executor():
        def run(plan, previous):
            seen.append(plan)
            return SimpleNamespace(ids=np.array([1, 2]), reports=[], notes=[], date_range="")
        return SimpleNamespace(run=run)

    class Local:
        calls = 0

        def chat_events(self, *a, **k):
            Local.calls += 1
            return iter([("tool", {"name": "find_photos", "arguments": {"what": "local guess"}})])

    service = AgentService(planner=None, executor_factory=make_executor, known_people=lambda: [], rescue=False)
    cloud_plan = {"name": "find_photos", "arguments": {"places": ["Nagoya"], "what": "stadium"}}
    agent = ToolAgent(Local(), service, lambda r: "", today=lambda: date(2026, 11, 4), cloud=lambda request, previous: cloud_plan)
    reply = agent.ask("Nagoya stadium")
    assert {c.query for c in seen[0].clauses} == {"Nagoya", "stadium"} and Local.calls == 0  # the local model was not even asked
    assert reply.timings["understood"] == "cloud"  # and the answer says so
    agent2 = ToolAgent(Local(), service, lambda r: "", today=lambda: date(2026, 11, 4), cloud=lambda request, previous: None)
    reply2 = agent2.ask("Nagoya stadium")
    assert reply2.timings["understood"] == "local" and Local.calls == 1 and seen[1].clauses[0].query == "local guess"  # cloud said nothing: the local model decided


def test_the_cloud_option_is_off_by_default():
    from aperture.config import Settings

    s = Settings()
    assert s.cloud_interpreter is False and s.cloud_cap_usd == 5.0 and s.cloud_port == 8770


def test_the_gateway_is_started_with_the_key_one_host_and_no_library_and_in_its_own_sandbox(monkeypatch, tmp_path):
    from aperture import launcher
    from aperture.config import Settings

    env = launcher.gateway_environment(Settings(), "sk-secret")
    assert env["APERTURE_CLOUD_KEY"] == "sk-secret" and env["APERTURE_TRUSTED_HOSTS"] == "api.anthropic.com"
    assert not any(k.startswith("APERTURE_DRIVE") or k == "AP_ROOT" for k in env)  # it is never told where the library is
    profile = (launcher.Path(launcher.__file__).resolve().parents[2] / "scripts" / "aperture-gateway.sb").read_text()
    assert '(deny file-read* (subpath "/Volumes"))' in profile and "Pictures" in profile and "(deny network" not in profile  # no library, but the network stays open
    monkeypatch.setattr(launcher.Path, "exists", lambda self: True)
    assert launcher.gateway_command()[:2] == ["/usr/bin/sandbox-exec", "-f"] and launcher.gateway_command()[-3:] == ["-m", "aperture", "cloud-gateway"]


def test_enabling_stores_the_key_in_the_keychain_only_and_turns_the_option_on(monkeypatch, tmp_path, capsys):
    import argparse

    from aperture import cli, launcher
    from aperture.config import Paths, Settings

    paths = Paths(tmp_path / "drive")
    paths.ensure()
    calls = []
    monkeypatch.setattr(cli.sys, "platform", "darwin")
    monkeypatch.setattr(cli.subprocess if hasattr(cli, "subprocess") else __import__("subprocess"), "run", lambda cmd, **k: calls.append(cmd) or SimpleNamespace(returncode=0, stdout="", stderr=""))
    import getpass

    key = "sk-ant-api03-" + "x" * 40
    monkeypatch.setattr(getpass, "getpass", lambda prompt="": "\x1b[200~ " + key + " \n")  # a paste with invisible extras still works
    monkeypatch.setattr(launcher, "keychain_key", lambda: key)
    assert cli.cmd_cloud(paths, argparse.Namespace(action="enable", forget_key=False)) == 0
    assert calls[0] == ["/usr/bin/security", "-i"] and key not in " ".join(calls[0])  # the key goes in on stdin, never in a command line
    monkeypatch.setattr(getpass, "getpass", lambda prompt="": "not a key")
    assert cli.cmd_cloud(paths, argparse.Namespace(action="enable", forget_key=False)) == 1 and "9 characters" in capsys.readouterr().out
    assert Settings.load(paths).cloud_interpreter is True
    cli.cmd_cloud(paths, argparse.Namespace(action="off", forget_key=True))
    assert Settings.load(paths).cloud_interpreter is False and calls[-1][1] == "delete-generic-password"


def test_the_cloud_model_and_cap_can_be_set_from_the_command_line(tmp_path):
    from aperture import cli
    from aperture.config import Paths, Settings

    paths = Paths(tmp_path / "drive")
    paths.ensure()
    args = cli.build_parser().parse_args(["settings", "--cloud-model", "claude-sonnet-5-5", "--cloud-cap", "2.5"])
    assert args.cloud_model == "claude-sonnet-5-5" and args.cloud_cap == 2.5
    s = Settings.load(paths)
    s.cloud_model, s.cloud_cap_usd = args.cloud_model, args.cloud_cap
    s.save(paths)
    assert Settings.load(paths).cloud_model == "claude-sonnet-5-5" and Settings.load(paths).cloud_cap_usd == 2.5


def test_conversation_goes_to_the_cloud_with_only_your_redacted_words_and_falls_back_locally(chain):
    chain.provider.text = "Hello <PERSON_1>! Lovely to hear from you."
    cloud = CloudInterpreter(chain.port, lambda: PEOPLE, lambda: PLACES)
    history = [("user", "my name is Anna Verhoeven"), ("assistant", "**586** photos \u00b7 Taken in or near Nagoya | Readings considered: ..."), ("user", "I like Nagoya")]
    reply = cloud.chat("hi it's Anna Verhoeven", history)
    assert reply == "Hello Anna Verhoeven! Lovely to hear from you."  # the real name is restored locally
    sent = json.dumps(chain.provider.seen[0][1])
    for private in ("Anna", "Verhoeven", "Nagoya", "586", "Readings"):
        assert private not in sent  # no name, no earlier answer, no result, no count
    content = json.loads(json.loads(sent)["messages"][0]["content"])
    assert set(content) == {"today", "their_earlier_messages", "their_message"} and len(content["their_earlier_messages"]) == 2  # only their own words
    assert CloudInterpreter(9, lambda: PEOPLE, lambda: PLACES).chat("hi", None) is None  # gateway down: the local model replies


def test_the_agent_uses_the_cloud_for_conversation_but_keeps_comments_on_results_local():
    from aperture.agent.service import AgentService

    service = AgentService(planner=None, executor_factory=lambda: None, known_people=lambda: [], rescue=False,
                           router=lambda request, previous: "about" if "why" in request else "chat")
    local = []
    service._chat_stream = lambda request, history: local.append(request) or iter(["local reply"])
    agent = ToolAgent(SimpleNamespace(), service, lambda r: "", today=lambda: date(2026, 11, 4), cloud_chat=lambda request, history: "cloud reply")
    reply = agent.ask("hello there")
    assert reply.text == "cloud reply" and reply.timings["understood"] == "cloud" and not local
    agent.ask("why these?", previous_ids=np.array([1, 2]))
    assert local == ["why these?"]  # a question about the results never leaves the Mac
    quiet = ToolAgent(SimpleNamespace(), service, lambda r: "", today=lambda: date(2026, 11, 4), cloud_chat=lambda request, history: None)
    quiet.ask("hello again")
    assert local[-1] == "hello again"  # the cloud had nothing: the local model replied


def test_a_photo_answer_says_how_the_request_was_understood():
    from aperture.agent.toolagent import describe_call

    assert describe_call("find_photos", {"places": ["Nagoya"], "what": "hockey stadium"}) == "show photos \u00b7 places Nagoya \u00b7 what hockey stadium"
    assert describe_call("count_photos", {"year": 2019}) == "count photos \u00b7 year 2019"


def test_with_the_switch_off_the_cloud_is_never_called_and_never_mentioned():
    from aperture.agent.service import AgentService

    service = AgentService(planner=None, executor_factory=lambda: None, known_people=lambda: [], rescue=False, router=lambda request, previous: "chat")
    service._chat_stream = lambda request, history: iter(["local reply"])
    calls, said = [], []
    agent = ToolAgent(SimpleNamespace(), service, lambda r: "", today=lambda: date(2026, 11, 4), cloud=lambda q, p: calls.append(q),
                      cloud_chat=lambda r, h: calls.append(r) or "cloud", cloud_on=lambda: False)
    reply = agent.ask("hello there", progress=said.append) if "progress" in ToolAgent.ask.__code__.co_varnames else agent.ask("hello there")
    assert not calls and reply.text != "cloud" and not any("cloud" in str(s).lower() for s in said)


def test_a_slow_or_failing_cloud_is_skipped_for_a_while_so_answers_are_not_delayed_twice():
    calls = []

    def broken(request, timeout=None):
        calls.append(1)
        raise TimeoutError

    cloud = CloudInterpreter(9, lambda: [], lambda: [], opener=broken)
    assert cloud("baby photos", False) is None and cloud("baby photos", False) is None and cloud.chat("hi", None) is None
    assert len(calls) == 1  # after the first failure the rest are not even attempted
