"""Stage 7: the signing and notarisation script cannot run without an Apple Developer ID, refuses a wrong identity, never takes a secret, and its dry run shows the exact order of steps."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.criterion(15)
SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "sign_and_notarize.sh"
ENV = {"PATH": os.environ["PATH"]}


def run(*args, **env):
    return subprocess.run(["bash", str(SCRIPT), *args], capture_output=True, text=True, env={**ENV, **env}, check=False, timeout=30)


def test_without_a_developer_id_or_a_notary_profile_it_refuses_with_its_own_code():
    assert run("Atlas.app").returncode == 2 and "DEVELOPER_ID" in run("Atlas.app").stderr
    assert run("Atlas.app", DEVELOPER_ID="Developer ID Application: Test (ABCDE12345)").returncode == 2
    assert run().returncode == 64


def test_only_a_developer_id_application_identity_is_accepted():
    done = run("Atlas.app", "--dry-run", DEVELOPER_ID="Apple Development: Test (ABCDE12345)", NOTARY_PROFILE="p")
    assert done.returncode == 2 and "Developer ID Application" in done.stderr


def test_the_dry_run_lists_every_step_in_order_and_prints_no_secret():
    done = run("Atlas.app", "--dry-run", DEVELOPER_ID="Developer ID Application: Test (ABCDE12345)", NOTARY_PROFILE="atlas-notary")
    lines = done.stdout.splitlines()
    assert done.returncode == 0
    order = [
        "find Atlas.app/Contents",
        "codesign --force --options runtime --timestamp --sign",
        "codesign --verify --deep --strict",
        "ditto -c -k --keepParent",
        "xcrun notarytool submit",
        "xcrun stapler staple",
        "spctl --assess",
    ]
    positions = [next(i for i, line in enumerate(lines) if line.startswith(step)) for step in order]
    assert positions == sorted(positions) and len(set(positions)) == len(order)  # nested code is signed before the app, and notarisation comes before stapling
    assert "--keychain-profile atlas-notary" in done.stdout and "password" not in done.stdout.lower() and "--options runtime" in done.stdout


def test_the_script_takes_no_password_or_key_argument():
    text = SCRIPT.read_text()
    assert "--password" not in text and "--apple-id" not in text and "--key " not in text and "set -euo pipefail" in text
