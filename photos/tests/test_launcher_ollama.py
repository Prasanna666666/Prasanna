"""Starting the app starts the AI engine too, and waits until it answers."""

from aperture import launcher
from aperture.launcher import ensure_ollama as real_ensure_ollama  # imported before the autouse fake replaces it


def test_the_ai_engine_is_started_when_it_is_not_running_and_waited_for(monkeypatch):
    state = {"up": False, "started": 0}

    class Reply:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def urlopen(url, timeout=1):
        if not state["up"]:
            raise OSError("refused")
        return Reply()

    def start():
        state["started"] += 1
        state["up"] = True  # the app opens and begins to answer

    monkeypatch.setattr(launcher.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(launcher, "_start_ollama", start)
    assert real_ensure_ollama(wait=5) is True and state["started"] == 1
    assert real_ensure_ollama(wait=5) is True and state["started"] == 1  # already running: nothing is started again


def test_when_the_engine_never_answers_start_up_carries_on_and_says_so(monkeypatch):
    monkeypatch.setattr(launcher.urllib.request, "urlopen", lambda url, timeout=1: (_ for _ in ()).throw(OSError("refused")))
    monkeypatch.setattr(launcher, "_start_ollama", lambda: None)
    monkeypatch.setattr(launcher.time if hasattr(launcher, "time") else __import__("time"), "sleep", lambda s: None)
    assert real_ensure_ollama(wait=0.05) is False


def test_the_background_service_runs_the_sandboxed_web_app(monkeypatch, tmp_path):
    import plistlib

    from images.config import Paths

    monkeypatch.setattr(launcher.Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setattr(launcher, "_run", lambda cmd: "")
    monkeypatch.setattr(launcher, "_run_ok", lambda cmd: True)
    launcher.install_service(Paths(tmp_path / "drive"))
    plist = next((tmp_path / "Library" / "LaunchAgents").glob("*.plist"))
    command = plistlib.loads(plist.read_bytes())["ProgramArguments"][-1]
    assert "secure-ui --no-browser" in command and "aperture ui" not in command and "open -ga Ollama" in command
