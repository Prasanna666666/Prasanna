"""scripts/handover-keys.sh decides whether the hand-over from the reader to the store is sealed. It is run for real here, with a stand-in `security` (the macOS Keychain) and `docker`. It must never start half configured, and never start plain without saying so (review item B2)."""

import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "handover-keys.sh"
PRIV, PUB = "a" * 64, "b" * 64


def _stubs(tmp_path: Path, *, keychain: dict[str, str], docker_ok: bool, with_security: bool = True) -> dict[str, str]:
    bin_dir, store = tmp_path / "bin", tmp_path / "keychain"
    bin_dir.mkdir(parents=True)
    store.mkdir(parents=True)
    for service, value in keychain.items():
        (store / service).write_text(value)
    if with_security:
        (bin_dir / "security").write_text(
            '#!/bin/bash\nS="$STUB_KEYCHAIN"\ncase "$1" in\n'
            '  find-generic-password) while [ $# -gt 0 ]; do [ "$1" = -s ] && svc="$2"; shift; done; [ -f "$S/$svc" ] && cat "$S/$svc" || exit 44;;\n'
            '  add-generic-password) while [ $# -gt 0 ]; do [ "$1" = -s ] && svc="$2"; [ "$1" = -w ] && val="$2"; shift; done; printf %s "$val" > "$S/$svc";;\n'
            "esac\n"
        )
        (bin_dir / "security").chmod(0o755)
    # the stand-in docker prints a new pair, or, when asked for `--public-from-private`, the public key
    body = f'case "$*" in *--public-from-private*) echo {PUB};; *) printf "%s\\n%s\\n" {PRIV} {PUB};; esac' if docker_ok else "exit 1"
    (bin_dir / "docker").write_text("#!/bin/bash\n" + body + "\n")
    (bin_dir / "docker").chmod(0o755)
    return {"PATH": f"{bin_dir}:/usr/bin:/bin", "STUB_KEYCHAIN": str(store), "USER": "tester", "HOME": str(tmp_path)}


def _run(tmp_path: Path, env_extra: dict[str, str] | None = None, **stub_args):
    env = {**_stubs(tmp_path, **stub_args), **(env_extra or {})}
    out = subprocess.run(
        ["/bin/bash", "-c", f'cd "{ROOT}/library"; source "{SCRIPT}"; rc=$?; echo "RC=$rc PUB=${{LIBRARY_HANDOVER_PUBLIC_KEY:-}} PRIV=${{LIBRARY_HANDOVER_PRIVATE_KEY:-}}"'],
        capture_output=True, text=True, env=env, check=False, timeout=60,
    )  # fmt: skip
    last = out.stdout.strip().splitlines()[-1] if out.stdout.strip() else ""
    rc, pub, priv = (part.split("=", 1)[1] for part in last.split(" ")) if last.startswith("RC=") else ("?", "", "")
    return int(rc) if rc.isdigit() else -1, pub, priv, out.stdout + out.stderr


def test_the_keys_in_the_keychain_turn_sealing_on_and_say_so(tmp_path):
    rc, pub, priv, said = _run(tmp_path, keychain={"atlas-handover-private": PRIV, "atlas-handover-public": PUB}, docker_ok=False)
    assert (rc, pub, priv) == (0, PUB, PRIV) and "Sealed hand-over: ON (keys from the Keychain)" in said


def test_with_no_keys_yet_a_pair_is_made_once_and_kept_in_the_keychain(tmp_path):
    rc, pub, priv, said = _run(tmp_path, keychain={}, docker_ok=True)
    assert (rc, pub, priv) == (0, PUB, PRIV) and "a new key pair was made" in said
    assert (tmp_path / "keychain" / "atlas-handover-private").read_text() == PRIV
    assert (tmp_path / "keychain" / "atlas-handover-public").read_text() == PUB


def test_only_the_private_key_in_the_keychain_is_enough_the_public_one_is_worked_out_and_kept(tmp_path):
    rc, pub, priv, said = _run(tmp_path, keychain={"atlas-handover-private": PRIV}, docker_ok=True)
    assert (rc, pub, priv) == (0, PUB, PRIV) and "worked out from the private one" in said
    assert (tmp_path / "keychain" / "atlas-handover-public").read_text() == PUB


def test_the_private_key_alone_with_no_way_to_work_out_the_public_one_starts_plain_loudly_or_not_at_all(tmp_path):
    rc, pub, priv, said = _run(tmp_path / "a", keychain={"atlas-handover-private": PRIV}, docker_ok=False)
    assert (rc, pub, priv) == (0, "", "") and "Sealed hand-over: OFF" in said
    rc2, _, _, _ = _run(tmp_path / "b", {"ATLAS_REQUIRE_SEALED": "1"}, keychain={"atlas-handover-private": PRIV}, docker_ok=False)
    assert rc2 == 2


def test_the_public_key_alone_or_a_damaged_private_key_in_the_keychain_is_never_guessed_at_and_nothing_starts(tmp_path):
    for n, only in enumerate(({"atlas-handover-public": PUB}, {"atlas-handover-private": "not-a-key"})):
        rc, pub, priv, said = _run(tmp_path / f"x{n}", keychain=only, docker_ok=True)
        assert rc == 2 and (pub, priv) == ("", "") and "Not starting" in said


@pytest.mark.parametrize("env", [{"LIBRARY_HANDOVER_PUBLIC_KEY": PUB}, {"LIBRARY_HANDOVER_PRIVATE_KEY": PRIV}])
def test_only_one_key_in_the_environment_stops_the_start(tmp_path, env):
    rc, _, _, said = _run(tmp_path, env, keychain={}, docker_ok=True)
    assert rc == 2 and "Set both, or neither" in said


@pytest.mark.parametrize("bad", ["not-hex", "ab" * 31, "ab" * 33, "Z" * 64])
def test_a_malformed_key_in_the_environment_stops_the_start(tmp_path, bad):
    rc, _, _, said = _run(tmp_path, {"LIBRARY_HANDOVER_PUBLIC_KEY": bad, "LIBRARY_HANDOVER_PRIVATE_KEY": PRIV}, keychain={}, docker_ok=True)
    assert rc == 2 and "not 64 hexadecimal characters" in said


def test_both_keys_in_the_environment_are_used(tmp_path):
    rc, pub, priv, said = _run(tmp_path, {"LIBRARY_HANDOVER_PUBLIC_KEY": PUB, "LIBRARY_HANDOVER_PRIVATE_KEY": PRIV}, keychain={}, docker_ok=False)
    assert (rc, pub, priv) == (0, PUB, PRIV) and "keys from the environment" in said


def test_turning_it_off_is_explicit_and_loud(tmp_path):
    rc, pub, priv, said = _run(tmp_path, {"ATLAS_SEAL_HANDOVER": "0"}, keychain={"atlas-handover-private": PRIV, "atlas-handover-public": PUB}, docker_ok=True)
    assert (rc, pub, priv) == (0, "", "") and "Sealed hand-over: OFF" in said and "unsealed" in said


def test_when_no_pair_can_be_made_it_starts_plain_but_says_so_unless_sealing_is_required(tmp_path):
    rc, pub, priv, said = _run(tmp_path / "a", keychain={}, docker_ok=False)
    assert (rc, pub, priv) == (0, "", "") and "Sealed hand-over: OFF" in said and "unsealed" in said
    rc2, _, _, said2 = _run(tmp_path / "b", {"ATLAS_REQUIRE_SEALED": "1"}, keychain={}, docker_ok=False)
    assert rc2 == 2 and "not starting" in said2


def test_without_a_keychain_it_says_plainly_that_sealing_is_off(tmp_path):
    rc, _, _, said = _run(tmp_path, keychain={}, docker_ok=True, with_security=False)
    assert rc == 0 and "Sealed hand-over: OFF" in said and "Keychain" in said


def test_the_library_start_script_runs_the_decision_and_stops_if_it_fails():
    up = (ROOT / "library" / "scripts" / "up.sh").read_text()
    assert "source ../scripts/handover-keys.sh || exit 2" in up
    assert up.index("handover-keys.sh") < up.index("docker compose")
    assert os.access(SCRIPT, os.R_OK)
