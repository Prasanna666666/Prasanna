"""The Docker deployment cannot run in CI; check its security properties from the files."""

from pathlib import Path

import yaml

ROOT = Path(__file__).parent.parent
C = yaml.safe_load((ROOT / "docker-compose.yml").read_text())
MAIL = yaml.safe_load((ROOT / "docker-compose.mail.yml").read_text())
S = C["services"]


def test_the_reader_has_no_network_and_sees_every_source_read_only():
    p = S["parser"]
    assert p["network_mode"] == "none"
    assert all(v.endswith(":ro") for v in p["volumes"] if not v.startswith("library-parsed"))  # inbox and collection folders
    assert p["read_only"] is True and p["cap_drop"] == ["ALL"] and p["mem_limit"] and p["pids_limit"]
    assert all(v.endswith(":ro") for v in MAIL["services"]["parser"]["volumes"])  # Apple Mail's folder is never written


def test_the_service_has_no_internet_and_its_key_comes_from_the_environment():
    a = S["app"]
    assert a["networks"] == ["private"] and C["networks"]["private"]["internal"] is True
    assert a["build"]["target"] == "app" and S["parser"]["build"]["target"] == "parser"
    assert a["read_only"] is True and a["cap_drop"] == ["ALL"]
    assert a["environment"]["ORBIT_DB_KEY"].startswith("${ORBIT_DB_KEY:?") and "secrets" not in C
    assert S["gateway"]["ports"] == ["127.0.0.1:8502:8502"]


def test_the_app_image_has_no_parsing_libraries_and_the_parser_image_has_no_shared_code():
    d = (ROOT / "Dockerfile").read_text()
    app = d.split("AS app")[1].split("AS parser")[0]
    parser = d.split("AS parser")[1].split("AS indexer")[0]
    assert "parse]" not in app and "USER 10001" in app and "USER 10001" in parser and "ORBIT_REQUIRE_ENCRYPTION=1" in app
    assert "[parse]" in parser and "orbit" not in parser.replace("ORBIT", "")  # the sealed reader carries only its own code


def test_the_picture_indexer_has_no_network_and_reads_the_photos_read_only():
    pictures = yaml.safe_load((ROOT / "docker-compose.pictures.yml").read_text())
    i = pictures["services"]["indexer"]
    assert i["network_mode"] == "none" and i["read_only"] is True and i["cap_drop"] == ["ALL"]
    assert any(v.endswith("/Photos:/Volumes/Expansion/Photos:ro") for v in i["volumes"]) and any(v.endswith("/models:ro") for v in i["volumes"])
    assert pictures["volumes"]["library-pictures"]["name"] == "library-pictures"  # a fixed name, so Photos can open the same index
    assert "ORBIT_DB_KEY" in pictures["services"]["app"]["environment"]


def test_only_the_service_can_write_to_the_photos_and_only_for_changes_you_confirm():
    pictures = yaml.safe_load((ROOT / "docker-compose.pictures.yml").read_text())["services"]
    assert all(v.endswith(":ro") for v in pictures["indexer"]["volumes"] if "/Photos" in v or "OrbitInbox" in v)  # the reader of pictures can never change them
    writable = [
        v for v in pictures["app"]["volumes"] if v.endswith(("/Photos:/Volumes/Expansion/Photos", "/Aperture_Exports:/Volumes/Expansion/Aperture_Exports"))
    ]
    assert len(writable) == 2  # the service: moves and exports, after a confirmation (library/changes.py)
