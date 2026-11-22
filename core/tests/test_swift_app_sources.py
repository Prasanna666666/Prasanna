"""The SwiftUI app is written but NOT built (no Swift here). These checks only stop it drifting from what is verified and stop it being described as more than it is."""

from __future__ import annotations

import re
from pathlib import Path

APP = Path(__file__).resolve().parents[2] / "app"
CORE = Path(__file__).resolve().parents[1]


def test_the_app_reads_the_same_catalogue_the_verified_client_and_its_completeness_test_use():
    assert (APP / "Sources/AtlasKit/ux_catalogue.json").read_bytes() == (CORE / "client/ux_catalogue.json").read_bytes()


def test_the_swift_signing_vectors_are_the_ones_in_the_specification_and_the_python_identity_code():
    from atlas_core import identity

    doc = (CORE / "docs/CONTRACT_1_1.md").read_text()
    vectors = re.findall(r'XCTAssertEqual\(hex\(m\), "([0-9a-f]+)"\)', (APP / "Tests/AtlasKitTests/SigningTests.swift").read_text())
    assert len(vectors) == 2 and all(v in doc for v in vectors)
    fields = ("post", "/v1/tasks?after=0", "1700000000", "abcdefgh12345678", b'{"a":1}')
    assert vectors == [identity.canonical(*fields).hex(), identity.canonical(*fields, version="1.1").hex()]


def test_the_app_claims_only_what_the_macos_ci_job_proves_it_builds_and_has_never_been_launched():
    readme, package = (APP / "README.md").read_text(), (APP / "Package.swift").read_text()
    assert "never launched" in readme and "never launched" in package  # nobody has seen it run
    assert "macOS CI runner" in readme and "macos:" in (APP.parent / ".github" / "workflows" / "ci.yml").read_text()  # the claim has a job behind it


def test_the_app_never_names_a_remote_host_or_cloud_service():
    for path in (APP / "Sources").rglob("*.swift"):
        assert not re.search(r"https?://|URLSession|api\.openai|anthropic", path.read_text()), path.name


def test_the_packaging_script_parses_says_it_is_only_ad_hoc_signed_and_fetches_nothing_but_the_local_packages():
    import subprocess

    script = APP.parent / "scripts" / "package_mac.sh"
    assert subprocess.run(["bash", "-n", str(script)], check=False).returncode == 0
    text = script.read_text()
    assert (
        "smoke-tested" in text
        and "NOT a release signature" in text
        and "notaris" in text
        and "curl" not in text
        and "http" not in text.replace("http://www.apple.com", "")
    )
