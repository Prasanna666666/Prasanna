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
    assert a["environment"]["ATLAS_DB_KEY"].startswith("${ATLAS_DB_KEY:?") and "secrets" not in C
    assert S["gateway"]["ports"] == ["127.0.0.1:8502:8502"]


def test_the_app_image_has_no_parsing_libraries_and_the_parser_image_has_no_shared_code():
    d = (ROOT / "Dockerfile").read_text()
    app = d.split("AS app")[1].split("AS parser")[0]
    parser = d.split("AS parser")[1].split("AS indexer")[0]
    assert "parse]" not in app and "USER 10001" in app and "USER 10001" in parser and "ATLAS_REQUIRE_ENCRYPTION=1" in app
    assert "[parse]" in parser and "finance" not in parser  # the sealed reader carries only its own code


def test_the_picture_indexer_has_no_network_and_reads_the_photos_read_only():
    pictures = yaml.safe_load((ROOT / "docker-compose.pictures.yml").read_text())
    i = pictures["services"]["indexer"]
    assert i["network_mode"] == "none" and i["read_only"] is True and i["cap_drop"] == ["ALL"]
    assert any(v.endswith("/Photos:/Volumes/Expansion/Photos:ro") for v in i["volumes"]) and any(v.endswith("/models:ro") for v in i["volumes"])
    assert pictures["volumes"]["library-pictures"]["name"] == "library-pictures"  # a fixed name, so Photos can open the same index
    assert "ATLAS_DB_KEY" in pictures["services"]["app"]["environment"]


def test_only_the_service_can_write_to_the_photos_and_only_for_changes_you_confirm():
    pictures = yaml.safe_load((ROOT / "docker-compose.pictures.yml").read_text())["services"]
    assert all(v.endswith(":ro") for v in pictures["indexer"]["volumes"] if "/Photos" in v or "AtlasInbox" in v)  # the reader of pictures can never change them
    writable = [
        v for v in pictures["app"]["volumes"] if v.endswith(("/Photos:/Volumes/Expansion/Photos", "/Aperture_Exports:/Volumes/Expansion/Aperture_Exports"))
    ]
    assert len(writable) == 2  # the service: moves and exports, after a confirmation (library/changes.py)


def test_atlas_starts_by_itself_at_login_and_everything_restarts_with_docker():
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    installer = (root / "scripts" / "install-autostart.sh").read_text()
    assert "RunAtLoad" in installer and "local.atlas.start" in installer and "osacompile" in installer
    for compose in ("finance", "library", "atlas"):
        assert "restart: unless-stopped" in (root / compose / "docker-compose.yml").read_text()
    login = (root / "scripts" / "start-at-login.sh").read_text()
    assert "ATLAS_NO_BUILD=1 ./up.sh" in login and "sleep" in login  # waits for the computer to start, and never rebuilds at login


def test_the_slow_installs_come_before_the_code_so_a_code_change_does_not_rebuild_them():
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    for name, slow in (("library/Dockerfile", ("sqlcipher3", "torch")), ("finance/Dockerfile", ("sqlcipher3",))):
        text = (root / name).read_text()
        copy_at = text.index("COPY kit")
        assert all(text.index(f"pip install {word}") < copy_at for word in slow)
        assert "--no-cache-dir" not in text  # downloads are kept between builds in a build cache, not in the image


def test_the_reader_gets_category_folders_and_listed_folders_only_read_only():
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    up = (root / "library" / "scripts" / "up.sh").read_text()
    assert "folders-compose.sh docker-compose.folders.yml" in up and "-f docker-compose.folders.yml" in up
    script = (root / "scripts" / "folders-compose.sh").read_text()
    assert ":ro" in script and "AtlasFolders.txt" in script
    assert "docker-compose.folders.yml" in (root / ".gitignore").read_text()


def test_one_command_starts_and_updates_and_a_start_without_changes_does_not_rebuild():
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    up = (root / "up.sh").read_text()
    assert "git rev-parse HEAD" in up and "ATLAS_NO_BUILD=1" in up and "ATLAS_REBUILD" in up
    update = (root / "update.sh").read_text()
    assert "git fetch origin" in update and "git checkout -B atlas origin/atlas" in update and "./up.sh" in update
    assert "atlas-migrated" in (root / "finance" / "scripts" / "up.sh").read_text()  # the one-time clean-up of the old names runs once
