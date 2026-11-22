"""The launchd property list that starts the Core after the owner signs in (Stage 4; UC-046).

A user LaunchAgent, not a LaunchDaemon: it runs only inside the owner's logged-in session, so the Keychain is unlocked when it starts and no key ever has to be kept where a headless boot could read it.
FileVault stays on and auto-login stays off; after a restart or an OS update the Core is simply not running until the owner signs in, and the app says "Mac needs owner sign-in" (see the Core's exit
code 6). Nothing here installs or loads the agent: it only produces the file's content and its path, so a test can check the policy without a Mac.
"""

from __future__ import annotations

import plistlib
from pathlib import Path

LABEL = "app.atlas.core"
EXIT_FAIL_RETRY_SECONDS = 30


def plist(program_arguments: list[str], data_dir: Path, *, label: str = LABEL) -> bytes:
    """The property list. The Core is restarted if it crashes (not if it exits cleanly or is refused: a refusal such as needs-sign-in or another Core running must not turn into a restart loop)."""
    if not program_arguments or not Path(program_arguments[0]).is_absolute():
        raise ValueError("the program must be an absolute path")
    document = {
        "Label": label,
        "ProgramArguments": list(program_arguments),
        "RunAtLoad": True,
        "KeepAlive": {"Crashed": True},  # restart after a crash or a signal, never after a normal exit or a deliberate refusal
        "ThrottleInterval": EXIT_FAIL_RETRY_SECONDS,
        "LimitLoadToSessionType": "Aqua",  # only in the owner's graphical login session
        "ProcessType": "Interactive",
        "WorkingDirectory": "/",
        "StandardOutPath": "/dev/null",  # the Core logs content-free events itself; nothing it prints is kept
        "StandardErrorPath": "/dev/null",
        "EnvironmentVariables": {},  # no key, code or path to a secret in the environment
        "AbandonProcessGroup": False,
    }
    del data_dir  # the data folder is passed on the command line by the caller; it is not part of the plist's policy
    return plistlib.dumps(document, fmt=plistlib.FMT_XML, sort_keys=True)


def install_path(home: Path, label: str = LABEL) -> Path:
    """Where the owner's agent lives: `~/Library/LaunchAgents` (per user), never `/Library/LaunchDaemons`."""
    return home / "Library" / "LaunchAgents" / f"{label}.plist"
