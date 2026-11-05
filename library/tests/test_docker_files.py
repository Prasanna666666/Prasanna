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
    parser = d.split("AS parser")[1]
    assert "parse]" not in app and "USER 10001" in app and "USER 10001" in parser and "ORBIT_REQUIRE_ENCRYPTION=1" in app
    assert "[parse]" in parser and "orbit" not in parser.replace("ORBIT", "")  # the sealed reader carries only its own code
