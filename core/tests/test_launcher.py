"""The real launch -> enrol -> consent sequence (review 6012553336): the app-side launcher starts a Core as a child process, hands it a one-time code over a private pipe, and the app
enrols as owner with it. The child is a real process; only the Mac providers are fakes."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from test_app import atlas_client

from atlas_core.launcher import CoreProcess, LaunchFailed
from atlas_core.serve import CODE_SHAPE

pytestmark = pytest.mark.skipif(sys.platform not in ("linux", "darwin"), reason="the child-process hand-off is implemented for Linux and macOS")
FACTORY = "core_factory:build_config"
OWNER_ID = "owner-launch-0001"
INTRUDER_ID = "intruder-launch01"


@pytest.fixture
def launched(tmp_path):
    sock = Path(tempfile.mkdtemp(prefix="atl")) / "run" / "core.sock"
    cores: list[CoreProcess] = []

    def start(**kw):
        core = CoreProcess(tmp_path / "core", sock, config_factory=FACTORY, allow_custom_factory=True, **kw)
        cores.append(core)
        core.start()
        return core

    yield start, tmp_path, sock
    for core in cores:
        core.stop()


def read_proc(pid: int, name: str) -> bytes:
    """What another process of this user can read about the child: /proc on Linux; `ps -E` (command line and environment) on macOS."""
    if sys.platform == "darwin":
        return subprocess.run(["/bin/ps", "-E", "-ww", "-p", str(pid), "-o", "command="], capture_output=True, check=False).stdout
    return Path(f"/proc/{pid}/{name}").read_bytes()


def test_the_app_launches_the_core_hands_it_the_code_privately_enrols_and_acts_as_owner(launched):
    start, tmp_path, sock = launched
    core = start()
    code, pid = core.bootstrap_code, core.process.pid
    assert code and CODE_SHAPE.match(code)
    signer = Ed25519PrivateKey.generate()
    client = atlas_client.AtlasClient(str(sock), signer, OWNER_ID)
    assert client.enrol_self(bootstrap_code=code)["role"] == "owner"
    core.forget_code()
    assert core.bootstrap_code is None
    assert client.consent()["grants"] == []  # enrolled, owner, through a real socket of a real child process
    # the code was never somewhere another process of this user could read it
    assert code.encode() not in read_proc(pid, "cmdline") and code.encode() not in read_proc(pid, "environ")
    for path in (tmp_path / "core").rglob("*"):
        if path.is_file():
            assert code.encode() not in path.read_bytes(), path.name
    assert not any(code in line for line in os.popen("ps -eo args").read().splitlines())  # not in any process's visible command line


def test_a_wrong_or_missing_code_cannot_enrol_against_the_real_child(launched):
    start, _, sock = launched
    core = start()
    intruder = atlas_client.AtlasClient(str(sock), Ed25519PrivateKey.generate(), INTRUDER_ID)
    for code in (None, "wrong-code-wrong-code-0000"):
        with pytest.raises(atlas_client.ClientError) as e:
            intruder.enrol_self(bootstrap_code=code)
        assert e.value.code == "unauthenticated"
    owner = atlas_client.AtlasClient(str(sock), Ed25519PrivateKey.generate(), OWNER_ID)
    assert owner.enrol_self(bootstrap_code=core.bootstrap_code)["role"] == "owner"  # the legitimate app still can


def test_the_next_launch_needs_no_code_once_an_owner_exists_and_the_owner_stays_enrolled(launched):
    start, _tmp, sock = launched
    first = start()
    signer = Ed25519PrivateKey.generate()
    atlas_client.AtlasClient(str(sock), signer, OWNER_ID).enrol_self(bootstrap_code=first.bootstrap_code)
    first.stop()
    second = start()  # a new process, a new code that nobody needs
    client = atlas_client.AtlasClient(str(sock), signer, OWNER_ID)
    assert client.consent()["grants"] == []
    intruder = atlas_client.AtlasClient(str(sock), Ed25519PrivateKey.generate(), INTRUDER_ID)
    with pytest.raises(atlas_client.ClientError):
        intruder.enrol_self(bootstrap_code=second.bootstrap_code)  # even the new code cannot create a second owner


def run_serve(stdin: bytes, extra=()) -> subprocess.CompletedProcess:
    env = {"PATH": os.environ["PATH"], "PYTHONPATH": os.pathsep.join(p for p in sys.path if p)}
    tmp = tempfile.mkdtemp(prefix="atl")
    return subprocess.run(
        [sys.executable, "-m", "atlas_core.serve", "--data-dir", f"{tmp}/core", "--socket", f"{tmp}/run/core.sock", "--config-factory", FACTORY, "--allow-custom-factory", *extra],
        input=stdin, capture_output=True, timeout=30, env=env, check=False,
    )  # fmt: skip


@pytest.mark.parametrize("stdin", [b"", b"\n", b"short\n", b"has space in it which is not a valid code\n", b"x" * 200 + b"\n"])
def test_a_fresh_core_started_without_a_valid_code_exits_without_serving(stdin):
    done = run_serve(stdin)
    assert done.returncode == 4 and b"READY" not in done.stdout


@pytest.mark.skipif(
    sys.platform == "darwin", reason="on a Mac the production factory builds the real providers and serves; this asserts the honest refusal everywhere else"
)
def test_the_production_factory_refuses_honestly_because_the_mac_providers_are_not_built():
    env = {"PATH": os.environ["PATH"], "PYTHONPATH": os.pathsep.join(p for p in sys.path if p)}
    tmp = tempfile.mkdtemp(prefix="atl")
    done = subprocess.run(
        [sys.executable, "-m", "atlas_core.serve", "--data-dir", f"{tmp}/c", "--socket", f"{tmp}/s"],
        input=b"a-valid-looking-code-0123456789\n",
        capture_output=True,
        timeout=30,
        env=env,
        check=False,
    )
    assert done.returncode != 0 and b"READY" not in done.stdout  # a development stand-in is never silently used


def test_a_custom_factory_needs_the_explicit_allowance():
    env = {"PATH": os.environ["PATH"], "PYTHONPATH": os.pathsep.join(p for p in sys.path if p)}
    tmp = tempfile.mkdtemp(prefix="atl")
    refused = subprocess.run(
        [sys.executable, "-m", "atlas_core.serve", "--data-dir", f"{tmp}/c", "--socket", f"{tmp}/s", "--config-factory", FACTORY],
        input=b"a-valid-looking-code-0123456789\n",
        capture_output=True,
        timeout=30,
        env=env,
        check=False,
    )
    assert refused.returncode == 4 and b"READY" not in refused.stdout


def test_a_launcher_whose_child_dies_reports_a_content_free_failure(tmp_path):
    core = CoreProcess(tmp_path / "core", tmp_path / "s", config_factory="nonexistent_module:nothing", allow_custom_factory=True)
    with pytest.raises(LaunchFailed) as e:
        core.start(timeout=20)
    assert str(e.value) in ("exited", "timeout") and core.bootstrap_code is None


def test_the_source_arguments_are_name_equals_folder_and_anything_else_is_ignored():
    from atlas_core.serve import _source

    assert _source("documents=/Users/x/Documents") == ("documents", Path("/Users/x/Documents"))
    assert _source("mail=/a=b/c") == ("mail", Path("/a=b/c"))
    assert _source(None) is None and _source("") is None and _source("nofolder") is None and _source("=/x") is None and _source("name=") is None


def _alive(pid: int) -> bool:
    """Running, not merely present: a process that has exited but is not yet reaped (a zombie, e.g. when PID 1 in a container does not reap orphans) is gone."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    try:
        state = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[0]
    except (OSError, IndexError):  # no /proc (macOS) or it vanished: the signal probe above stands
        return True
    return state not in ("Z", "X")


def test_a_core_whose_parent_dies_stops_by_itself_instead_of_running_on(tmp_path):
    """The app crashes or is killed: the Core it started must not be left running, processing sources with no one to answer to."""
    import signal
    import textwrap
    import time

    sock = Path(tempfile.mkdtemp(prefix="atl")) / "run" / "core.sock"
    parent_code = textwrap.dedent(
        f"""
        import os, signal, sys
        sys.path[:0] = {[str(Path(__file__).parent), str(Path(__file__).parent.parent / "src")]!r}
        from pathlib import Path
        from atlas_core.launcher import CoreProcess
        core = CoreProcess(Path({str(tmp_path / "core")!r}), Path({str(sock)!r}), config_factory="core_factory:build_config", allow_custom_factory=True)
        core.start()
        print(core.process.pid, flush=True)
        os.kill(os.getpid(), signal.SIGKILL)  # a crash: no cleanup of any kind runs
        """
    )
    parent = subprocess.Popen([sys.executable, "-c", parent_code], stdout=subprocess.PIPE, text=True)
    assert parent.stdout is not None
    core_pid = int(parent.stdout.readline())
    parent.wait(30)
    try:
        deadline = time.monotonic() + 15
        while _alive(core_pid) and time.monotonic() < deadline:
            time.sleep(0.2)
        assert not _alive(core_pid), "the Core outlived the app that started it"
    finally:
        if _alive(core_pid):
            os.kill(core_pid, signal.SIGKILL)


def test_stop_terminates_waits_for_and_reaps_the_core(launched):
    start, _, _ = launched
    core = start()
    pid = core.process.pid
    core.stop()
    assert core.process.returncode == 0 and not _alive(pid)  # a clean exit, reaped: no zombie left behind


def test_a_second_core_on_the_same_data_folder_does_not_start_and_touches_nothing(launched):
    start, tmp_path, sock = launched
    first = start()
    done = subprocess.run(  # same data folder, same socket, a perfectly valid code: it must still refuse
        [sys.executable, "-m", "atlas_core.serve", "--data-dir", str(tmp_path / "core"), "--socket", str(sock), "--config-factory", FACTORY, "--allow-custom-factory"],
        input=b"a-valid-looking-code-0123456789\n", capture_output=True, timeout=30, env={"PATH": os.environ["PATH"], "PYTHONPATH": os.pathsep.join(p for p in sys.path if p)}, check=False,
    )  # fmt: skip
    assert done.returncode == 5 and b"READY" not in done.stdout
    code = first.bootstrap_code
    owner = atlas_client.AtlasClient(str(sock), Ed25519PrivateKey.generate(), OWNER_ID)
    assert owner.enrol_self(bootstrap_code=code)["role"] == "owner"  # the first Core still owns its socket and answers


def test_a_data_folder_lock_dies_with_its_holder_so_a_crash_never_blocks_the_next_start(launched):
    start, _tmp, sock = launched
    first = start()
    first.process.kill()  # no cleanup of any kind runs: the socket file stays behind
    first.process.wait(10)
    assert sock.exists()  # stale
    second = start()  # the OS released the lock; the stale socket is recognised as stale and replaced
    owner = atlas_client.AtlasClient(str(sock), Ed25519PrivateKey.generate(), OWNER_ID)
    assert owner.enrol_self(bootstrap_code=second.bootstrap_code)["role"] == "owner"


def test_a_locked_keychain_makes_the_core_exit_with_its_own_code_and_the_launcher_says_the_mac_needs_sign_in(tmp_path):
    from atlas_core import launcher, serve

    assert launcher.EXIT_NEEDS_SIGNIN == serve.EXIT_NEEDS_SIGNIN == 6
    env = {"PATH": os.environ["PATH"], "PYTHONPATH": os.pathsep.join(p for p in sys.path if p)}
    direct = subprocess.run(
        [sys.executable, "-m", "atlas_core.serve", "--data-dir", str(tmp_path / "c"), "--socket", str(tmp_path / "s"), "--config-factory", "core_factory:keychain_locked", "--allow-custom-factory"],
        input=b"a-valid-looking-code-0123456789\n", capture_output=True, timeout=30, env=env, check=False,
    )  # fmt: skip
    assert (
        direct.returncode == 6 and b"READY" not in direct.stdout and sorted(p.name for p in (tmp_path / "c").iterdir()) == ["core.lock"]
    )  # no key, store or socket: only the empty lock file
    process = launcher.CoreProcess(tmp_path / "core", tmp_path / "run" / "core.sock", config_factory="core_factory:keychain_locked", allow_custom_factory=True)
    with pytest.raises(launcher.LaunchFailed) as e:
        process.start(timeout=30)
    assert str(e.value) == "needs_owner_signin" and process.bootstrap_code is None


FACTORY_CALLS: list[str] = []


def recording_factory(data_dir, socket_path, code, options):
    """Stands for the production factory, which provisions Keychain keys and opens stores: it must never run for a start that cannot own the folder."""
    FACTORY_CALLS.append(str(data_dir))
    raise AssertionError("keys would have been provisioned")


def test_a_start_that_cannot_own_the_data_folder_provisions_no_keys_and_opens_no_store(tmp_path, monkeypatch):
    """The folder lock is taken BEFORE the config factory (Keychain provisioning, store opening): the losing start exits busy and touches nothing."""
    import io

    from atlas_core import serve
    from atlas_core.app import acquire_data_dir

    data = tmp_path / "core"
    held = acquire_data_dir(data)  # another Core owns the folder
    try:
        monkeypatch.setattr(sys, "stdin", io.StringIO(""))
        FACTORY_CALLS.clear()
        code = serve.main(
            ["--data-dir", str(data), "--socket", str(tmp_path / "s"), "--config-factory", "test_launcher:recording_factory", "--allow-custom-factory"]
        )
        assert code == serve.EXIT_BUSY and FACTORY_CALLS == []
    finally:
        os.close(held)


def test_concurrent_starts_across_a_keychain_refusal_never_have_two_contenders_in_the_factory(tmp_path):
    """The lock file is stable across failed starts (never unlinked), so contenders cannot end up holding different files at one path: at no moment are two of them past the lock."""
    import threading
    import time

    from atlas_core import serve
    from atlas_core.app import CoreAlreadyRunning, acquire_data_dir

    data = tmp_path / "core"
    inside, worst, entered = [0], [0], []
    guard = threading.Lock()
    start = threading.Barrier(8)

    def contender():
        start.wait()
        for _ in range(25):
            try:
                lock = acquire_data_dir(data)
            except CoreAlreadyRunning:
                time.sleep(0.001)
                continue
            with guard:
                inside[0] += 1
                worst[0] = max(worst[0], inside[0])
                entered.append(1)
            time.sleep(0.003)  # the factory is running (and would refuse because the Keychain is locked)
            with guard:
                inside[0] -= 1
            serve._give_up(lock)  # the refusal path of main()

    threads = [threading.Thread(target=contender) for _ in range(8)]
    [t.start() for t in threads]
    [t.join(30) for t in threads]
    assert entered and worst[0] == 1, f"{worst[0]} contenders were past the lock at once"
    assert (data / "core.lock").exists()


def test_an_unexpected_factory_failure_releases_the_folder_lock(tmp_path, monkeypatch):
    import io

    from atlas_core import serve
    from atlas_core.app import acquire_data_dir

    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    data = tmp_path / "core"
    with pytest.raises(AssertionError):  # recording_factory raises one: not a refusal the host knows
        serve.main(["--data-dir", str(data), "--socket", str(tmp_path / "s"), "--config-factory", "test_launcher:recording_factory", "--allow-custom-factory"])
    again = acquire_data_dir(data)  # the lock was released: a new start can take the folder
    os.close(again)


def test_a_stop_with_a_request_still_running_exits_with_status_7_and_the_next_start_succeeds(launched):
    """MAC-18, process level: the Core is told to stop while a client holds a request open. It keeps its stores rather than closing them
    under live work, exits with EXIT_SHUTDOWN_INCOMPLETE (7) once the drain deadline passes, and the OS releases the folder lock so the
    next start takes the folder and answers."""
    import signal
    import socket as socket_module

    from atlas_core import serve

    start, _tmp, sock = launched
    first = start()
    held = socket_module.socket(socket_module.AF_UNIX, socket_module.SOCK_STREAM)
    held.connect(str(sock))
    held.sendall(b"GET /v1/version HTTP/1.1\r\nHost: localhost\r\n")  # a request the Core is still reading when told to stop
    first.process.send_signal(signal.SIGTERM)
    assert first.process.wait(60) == serve.EXIT_SHUTDOWN_INCOMPLETE
    held.close()
    second = start()
    owner = atlas_client.AtlasClient(str(sock), Ed25519PrivateKey.generate(), OWNER_ID)
    assert owner.enrol_self(bootstrap_code=second.bootstrap_code)["role"] == "owner"
