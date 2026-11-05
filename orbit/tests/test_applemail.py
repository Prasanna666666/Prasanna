import json
import subprocess

import pytest

from orbit import applemail, cli


def fake_run(records, code=0, err=""):
    seen = {}

    def run(cmd, **kw):
        seen["cmd"], seen["kw"] = cmd, kw
        return subprocess.CompletedProcess(cmd, code, json.dumps(records), err)

    return run, seen


def test_the_mail_script_gets_only_numbers_a_flag_and_a_fixed_list():
    script = applemail.build_script(30, True)
    assert "const P = {" in script and '"days": 30' in script and '"only_attachments": true' in script and "Trash" in script and "__PARAMS__" not in script
    assert '"days": 3650' in applemail.build_script(10**9, False) and '"days": 1' in applemail.build_script(-5, False)  # always bounded


def test_messages_are_fetched_through_osascript_and_written_as_eml_with_hash_names(tmp_path):
    run, seen = fake_run(
        [
            {"account": "Gmail", "mailbox": "INBOX", "id": "7", "source": "From: a@b.c\r\nSubject: Factuur\r\n\r\nhoi"},
            {"account": "Gmail", "mailbox": "INBOX", "id": "8", "source": ""},
            "junk",
        ]
    )
    records = applemail.fetch_messages(90, True, run=run)
    assert seen["cmd"][:3] == ["osascript", "-l", "JavaScript"] and seen["kw"]["timeout"] > 0
    out = tmp_path / "mail"
    assert applemail.write_messages(records, out) == {"new": 1, "already_had": 0, "skipped": 2}
    files = list(out.iterdir())
    assert (
        len(files) == 1 and files[0].suffix == ".eml" and len(files[0].stem) == 40 and files[0].read_text().startswith("From: a@b.c")
    )  # named by a hash, never by the mail's text
    assert applemail.write_messages(records, out) == {"new": 0, "already_had": 1, "skipped": 2}  # re-running adds only what is new


def test_a_refusal_from_mail_is_explained_in_plain_words():
    run, _ = fake_run([], code=1, err="Not authorized to send Apple events to Mail.")
    with pytest.raises(RuntimeError, match="Automation"):
        applemail.fetch_messages(run=run)
    bad = lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0, '{"a": 1}', "")  # noqa: E731
    with pytest.raises(RuntimeError, match="do not understand"):
        applemail.fetch_messages(run=bad)


def test_exporting_on_a_machine_without_the_mail_app_says_so(monkeypatch):
    monkeypatch.setattr("sys.platform", "linux")
    with pytest.raises(RuntimeError, match="macOS Mail"):
        applemail.fetch_messages()


def test_the_command_exports_into_the_mail_folder_of_the_inbox(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("ORBIT_INBOX", str(tmp_path / "inbox"))
    got = {}

    def fetch(days, only_attachments):
        got.update(days=days, only=only_attachments)
        return [{"account": "A", "mailbox": "INBOX", "id": "1", "source": "Subject: x\r\n\r\ny"}]

    monkeypatch.setattr(cli.applemail, "fetch_messages", fetch)
    assert cli._export_mail(["--days", "30"]) == 0
    assert got == {"days": 30, "only": True} and len(list((tmp_path / "inbox" / "mail").glob("*.eml"))) == 1
    cli._export_mail(["--all"])
    assert got == {"days": 365, "only": False}  # --all also copies messages without attachments
