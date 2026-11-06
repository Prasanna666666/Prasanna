"""The Docker deployment cannot run in CI; check its security properties from the files."""

from pathlib import Path

import yaml

ROOT = Path(__file__).parent.parent
C = yaml.safe_load((ROOT / "docker-compose.yml").read_text())
S = C["services"]


def test_finance_opens_no_files_and_has_no_internet():
    a = S["app"]
    assert "parser" not in S  # the Documents service reads every file and mail
    assert a["networks"] == ["private"] and C["networks"]["private"]["internal"] is True
    assert not any(":/parsed" in v or ":/finance" in v for v in a["volumes"])
    assert a["build"]["target"] == "app" and a["read_only"] is True and a["cap_drop"] == ["ALL"]


def test_database_key_comes_from_the_environment_never_from_a_file_in_the_repo():
    assert "secrets" not in S["app"] and "secrets" not in C  # a read-only container cannot be given a Docker secret
    assert S["app"]["environment"]["ORBIT_DB_KEY"].startswith("${ORBIT_DB_KEY:?")  # up.sh must supply it from the Keychain
    assert not any("key" in v.lower() and "=" in v for v in S["app"].get("volumes", []))
    assert S["gateway"]["ports"] == ["127.0.0.1:8501:8501"]


def test_the_app_image_has_no_parsing_libraries():
    d = (ROOT / "Dockerfile").read_text()
    assert "secure" in d or "sqlcipher" in d
    assert "pymupdf" not in d.lower() and "tesseract" not in d.lower() and "USER 10001" in d and "ORBIT_REQUIRE_ENCRYPTION=1" in d


def test_the_app_reaches_ollama_and_the_documents_service_only_through_forwarders():
    assert S["app"]["environment"]["OLLAMA_HOST"].startswith("http://ollama.internal:11434")  # other host names get HTTP 403 from Ollama
    assert "ollama.internal" in S["ollama"]["networks"]["private"]["aliases"]
    assert S["app"]["environment"]["LIBRARY_URL"].startswith("http://library.internal:8502")
    assert "library.internal" in S["library"]["networks"]["private"]["aliases"] and "host.docker.internal:8502" in S["library"]["command"]
