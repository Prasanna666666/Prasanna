"""The Docker deployment cannot run in CI; check its security properties from the files."""

from pathlib import Path

import yaml

ROOT = Path(__file__).parent.parent
C = yaml.safe_load((ROOT / "docker-compose.yml").read_text())
S = C["services"]


def test_parser_has_no_network_and_cannot_write_inbox():
    p = S["parser"]
    assert p["network_mode"] == "none"
    assert any(v.endswith("/inbox:ro") for v in p["volumes"])
    assert p["read_only"] is True and p["cap_drop"] == ["ALL"] and p["mem_limit"] and p["pids_limit"]


def test_app_reads_parser_output_read_only_and_has_no_internet():
    a = S["app"]
    assert a["networks"] == ["private"] and C["networks"]["private"]["internal"] is True
    assert "orbit-parsed:/parsed:ro" in a["volumes"]
    assert a["build"]["target"] == "app" and S["parser"]["build"]["target"] == "parser"
    assert a["read_only"] is True and a["cap_drop"] == ["ALL"]


def test_database_key_is_a_secret_not_a_file_in_the_repo():
    assert "orbit_key" in S["app"]["secrets"] and C["secrets"]["orbit_key"] == {"environment": "ORBIT_DB_KEY"}
    assert S["app"]["environment"]["ORBIT_DB_KEY_FILE"] == "/run/secrets/orbit_key"
    assert S["gateway"]["ports"] == ["127.0.0.1:8501:8501"]


def test_images_keep_parsing_libraries_out_of_the_app():
    d = (ROOT / "Dockerfile").read_text()
    app = d.split("AS app")[1].split("AS parser")[0]
    parser = d.split("AS parser")[1]
    assert "secure" in app and "parse" not in app.replace("parser", "")
    assert "[parse]" in parser and "USER 10001" in app and "USER 10001" in parser
    assert "ORBIT_REQUIRE_ENCRYPTION=1" in app
