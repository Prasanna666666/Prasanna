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


def test_app_deletes_parser_output_after_storing_it_and_has_no_internet():
    a = S["app"]
    assert a["networks"] == ["private"] and C["networks"]["private"]["internal"] is True
    assert "orbit-parsed:/parsed" in a["volumes"]  # writable only so the readable copy can be deleted once stored in the encrypted database
    assert a["build"]["target"] == "app" and S["parser"]["build"]["target"] == "parser"
    assert a["read_only"] is True and a["cap_drop"] == ["ALL"]


def test_database_key_comes_from_the_environment_never_from_a_file_in_the_repo():
    assert "secrets" not in S["app"] and "secrets" not in C  # a read-only container cannot be given a Docker secret
    assert S["app"]["environment"]["ORBIT_DB_KEY"].startswith("${ORBIT_DB_KEY:?")  # up.sh must supply it from the Keychain
    assert not any("key" in v.lower() and "=" in v for v in S["app"].get("volumes", []))
    assert S["gateway"]["ports"] == ["127.0.0.1:8501:8501"]


def test_images_keep_parsing_libraries_out_of_the_app():
    d = (ROOT / "Dockerfile").read_text()
    app = d.split("AS app")[1].split("AS parser")[0]
    parser = d.split("AS parser")[1]
    assert "secure" in app and "parse" not in app.replace("parser", "")
    assert "[parse]" in parser and "USER 10001" in app and "USER 10001" in parser
    assert "ORBIT_REQUIRE_ENCRYPTION=1" in app


def test_the_app_reaches_ollama_by_a_name_ollama_accepts():
    assert S["app"]["environment"]["OLLAMA_HOST"].startswith("http://ollama.internal:11434")  # other host names get HTTP 403 from Ollama
    assert "ollama.internal" in S["ollama"]["networks"]["private"]["aliases"]
