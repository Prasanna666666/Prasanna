"""The macOS sandbox cannot run on CI/Linux, so check what can be checked: the files are well-formed."""

import subprocess
from pathlib import Path

SCRIPTS = Path(__file__).parent.parent / "scripts"


def test_profile_parens_balanced_and_denies_network():
    text = "\n".join(line.split(";;")[0] for line in (SCRIPTS / "aperture-sandbox.sb").read_text().splitlines())
    assert text.count("(") == text.count(")")
    assert "(deny network*)" in text and "(allow default)" in text
    # network allows are loopback / unix sockets only
    allows = [ln for ln in text.splitlines() if ln.startswith("(allow network*")]
    assert allows and all("localhost" in ln or "unix-socket" in ln for ln in allows)


def test_wrapper_is_valid_bash():
    assert subprocess.run(["bash", "-n", str(SCRIPTS / "aperture-sandboxed.sh")]).returncode == 0
