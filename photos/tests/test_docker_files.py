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
    assert set(c["networks"]) == {"private"}, "no outside network may exist"
    assert "fetch-models" not in c["services"], "no service may download anything"
    assert c["services"]["gateway"]["ports"] == ["127.0.0.1:8765:8765"]


def test_dockerfile_runs_non_root_and_without_mac_extras():
    d = (ROOT / "Dockerfile.aperture").read_text()
    assert (
        "APERTURE_NEVER_ONLINE=1" in d
        and "USER 10001" in d
        and "images[ml]" in d
        and "photos[ui]" in d
        and "mac" not in d.split("pip install")[-1]
    )


def test_the_photo_index_lives_in_a_private_docker_volume_not_a_mac_folder():
    from pathlib import Path

    compose = (Path(__file__).parent.parent / "docker-compose.aperture.yml").read_text()
    assert "library-pictures:/Volumes/Expansion/Aperture/data" in compose and "library-pictures:\n    external: true" in compose
    assert "/Aperture:/Volumes/Expansion/Aperture\n" not in compose  # the whole Aperture folder is no longer a bind mount
    assert (
        "Photos:/Volumes/Expansion/Photos:ro" in compose and "/Aperture/models:/Volumes/Expansion/Aperture/models:ro" in compose
    )


def test_the_coding_assistant_is_denied_the_drive_and_the_containers_data():
    import json
    from pathlib import Path

    deny = json.loads((Path(__file__).parent.parent / ".claude" / "settings.json").read_text())["permissions"]["deny"]
    assert "Read(//Volumes/**)" in deny and "Bash(docker cp:*)" in deny and "Bash(docker exec:*)" in deny
