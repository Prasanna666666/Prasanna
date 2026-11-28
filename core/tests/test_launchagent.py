"""Stage 4, UC-046: the Core starts only after the owner signs in; no headless unlock, no key in the file."""

from __future__ import annotations

import plistlib
from pathlib import Path

import pytest

from atlas_core.launchagent import LABEL, install_path, plist

pytestmark = pytest.mark.criterion(15)
PROGRAM = [
    "/Applications/Atlas.app/Contents/Resources/python/bin/python3",
    "-m",
    "atlas_core.serve",
    "--data-dir",
    "/Users/o/Library/Application Support/Atlas/core",
]


def test_the_agent_runs_only_in_the_owners_login_session_and_restarts_only_after_a_crash():
    document = plistlib.loads(plist(PROGRAM, Path("/x")))
    assert document["Label"] == LABEL and document["ProgramArguments"] == PROGRAM and document["RunAtLoad"] is True
    assert document["LimitLoadToSessionType"] == "Aqua"  # a graphical login session: after the owner signs in, with the Keychain unlocked
    assert document["KeepAlive"] == {"Crashed": True}  # a clean exit or a refusal (needs sign-in, another Core running) is not restarted in a loop
    assert document["ThrottleInterval"] >= 30
    assert "UserName" not in document and "SessionCreate" not in document  # not a daemon, not another user's session


def test_nothing_secret_or_remote_is_in_the_file():
    document = plistlib.loads(plist(PROGRAM, Path("/x")))
    for forbidden in ("key", "code", "token", "password", "sockets", "machservices"):
        assert not [k for k in document if forbidden in k.lower()], forbidden
    assert document["EnvironmentVariables"] == {} and document["StandardOutPath"] == "/dev/null"


def test_the_agent_lives_in_the_users_launch_agents_folder_never_in_a_system_daemons_folder():
    path = install_path(Path("/Users/owner"))
    assert str(path) == f"/Users/owner/Library/LaunchAgents/{LABEL}.plist" and "LaunchDaemons" not in str(path)


@pytest.mark.parametrize("program", [[], ["python3"], ["./python"]])
def test_a_relative_or_missing_program_is_refused(program):
    with pytest.raises(ValueError):
        plist(program, Path("/x"))
