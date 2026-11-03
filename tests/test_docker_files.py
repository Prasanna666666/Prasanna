"""The Docker deployment cannot run in CI; check the security properties of the files instead."""

from pathlib import Path

import yaml

ROOT = Path(__file__).parent.parent


def test_aperture_compose_security_properties():
    c = yaml.safe_load((ROOT / "docker-compose.aperture.yml").read_text())
    assert c["networks"]["private"]["internal"] is True
    app = c["services"]["aperture"]
    assert app["networks"] == ["private"], "the app must have no route to the internet"
    assert app["read_only"] is True and app["cap_drop"] == ["ALL"]
    photos = [v for v in app["volumes"] if "/Photos" in v]
    assert photos and all(v.endswith(":ro") for v in photos), "photos must be mounted read-only"
    # only the model-download job may reach the outside network
    outside = [n for n, s in c["services"].items() if "outside" in (s.get("networks") or [])]
    assert outside == ["fetch-models"]
    assert c["services"]["gateway"]["ports"] == ["127.0.0.1:8765:8765"]


def test_dockerfile_runs_non_root_and_without_mac_extras():
    d = (ROOT / "Dockerfile.aperture").read_text()
    assert "USER 10001" in d and "[ml,ui]" in d and "mac" not in d.split("pip install")[-1]
