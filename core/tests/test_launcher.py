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
