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
    agent.ask("Nagoya stadium")
    assert {c.query for c in seen[0].clauses} == {"Nagoya", "stadium"} and Local.calls == 0  # the local model was not even asked
    agent2 = ToolAgent(Local(), service, lambda r: "", today=lambda: date(2026, 11, 4), cloud=lambda request, previous: None)
    agent2.ask("Nagoya stadium")
    assert Local.calls == 1 and seen[1].clauses[0].query == "local guess"  # cloud said nothing: the local model decided


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
    monkeypatch.setattr(cli.subprocess if hasattr(cli, "subprocess") else __import__("subprocess"), "run", lambda cmd, **k: calls.append(cmd) or SimpleNamespace(returncode=0))
    monkeypatch.setattr(launcher, "keychain_key", lambda: "sk-secret")
    assert cli.cmd_cloud(paths, argparse.Namespace(action="enable", forget_key=False)) == 0
    assert calls[0][:2] == ["/usr/bin/security", "add-generic-password"] and "-w" in calls[0] and "sk-secret" not in " ".join(calls[0])  # the key is never an argument
    assert Settings.load(paths).cloud_interpreter is True
    cli.cmd_cloud(paths, argparse.Namespace(action="off", forget_key=True))
    assert Settings.load(paths).cloud_interpreter is False and calls[-1][1] == "delete-generic-password"
