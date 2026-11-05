import json
import subprocess

import pytest

from orbit import applemail, cli

MSG = {"account": "Gmail", "mailbox": "INBOX", "id": "7", "source": "From: a@b.c\r\nSubject: Boeking\r\n\r\nUw vlucht vertrekt om 10:45"}


def fake_run(mailboxes, by_mailbox, code=0, err=""):
    """Stands in for osascript: lists the mailboxes, then answers each mailbox question."""
    calls = []

    def run(cmd, **kw):
        script = cmd[-1]
        calls.append(script)
        if "P.account" in script:
            params = json.loads(script.split("const P = ")[1].split(";\n")[0])
            out = by_mailbox.get((params["account"], params["mailbox"]), [])
        else:
            out = [{"account": a, "mailbox": m} for a, m in mailboxes]
        return subprocess.CompletedProcess(cmd, code, json.dumps(out), err)

    return run, calls


def test_a_mailbox_script_gets_its_names_as_data_and_its_limits_as_numbers():
    script = applemail.build_script('Gmail"; evil();//', "INBOX", 30, False)
    params = json.loads(script.split("const P = ")[1].split(";\n")[0])
    assert params == {"account": 'Gmail"; evil();//', "mailbox": "INBOX", "days": 30, "only_attachments": False}  # a hostile name stays inside a string
    assert applemail.build_script("a", "b", 10**9, True).count('"days": 18250') == 1 and '"days": 1,' in applemail.build_script("a", "b", -5, True)


def test_all_mail_is_copied_by_default_mailbox_by_mailbox_and_junk_trash_and_drafts_are_skipped(tmp_path):
    run, calls = fake_run(
        [("Gmail", "INBOX"), ("Gmail", "Trash"), ("Gmail", "Drafts"), ("iCloud", "Bills")],
        {
            ("Gmail", "INBOX"): [MSG, {"account": "Gmail", "mailbox": "INBOX", "id": "8", "source": ""}],
            ("iCloud", "Bills"): [{**MSG, "account": "iCloud", "mailbox": "Bills", "id": "1"}],
        },
    )
    lines: list[str] = []
    out = tmp_path / "mail"
    total = applemail.export(out, run=run, progress=lines.append)
    assert total == {"new": 2, "already_had": 0, "skipped": 1, "mailboxes": 2}  # Trash and Drafts were never even asked for
    assert all("Trash" not in c.split("const P = ")[-1].split(";\n")[0] and "Drafts" not in c.split("const P = ")[-1].split(";\n")[0] for c in calls[1:])
    assert all('"only_attachments": false' in c for c in calls[1:])  # the text of an email can be the crucial information: nothing is filtered out
    files = list(out.iterdir())
    assert len(files) == 2 and all(f.suffix == ".eml" and len(f.stem) == 40 for f in files) and len(lines) == 2  # named by a hash, never by the mail's text
    assert applemail.export(out, run=run, progress=lambda _: None)["new"] == 0  # re-running adds only what is new


def test_only_messages_with_an_attachment_can_be_asked_for(tmp_path):
    run, calls = fake_run([("Gmail", "INBOX")], {})
    applemail.export(tmp_path, only_attachments=True, run=run, progress=lambda _: None)
    assert '"only_attachments": true' in calls[1]


def test_a_refusal_from_mail_is_explained_in_plain_words():
    run, _ = fake_run([], {}, code=1, err="Not authorized to send Apple events to Mail.")
    with pytest.raises(RuntimeError, match="Automation"):
        applemail.list_mailboxes(run)
    bad = lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0, '{"a": 1}', "")  # noqa: E731
    with pytest.raises(RuntimeError, match="do not understand"):
        applemail.list_mailboxes(bad)


def test_exporting_on_a_machine_without_the_mail_app_says_so(monkeypatch):
    monkeypatch.setattr("sys.platform", "linux")
    with pytest.raises(RuntimeError, match="macOS Mail"):
        applemail.list_mailboxes()


def test_the_command_copies_all_mail_into_the_mail_folder_unless_told_to_keep_to_attachments(tmp_path, monkeypatch):
    monkeypatch.setenv("ORBIT_INBOX", str(tmp_path / "inbox"))
    got = {}

    def export(out, days, only_attachments):
        got.update(out=out, days=days, only=only_attachments)
        return {"new": 0}

    monkeypatch.setattr(cli.applemail, "export", export)
    assert cli._export_mail(["--days", "30"]) == 0
    assert got == {"out": tmp_path / "inbox" / "mail", "days": 30, "only": False}
    cli._export_mail(["--attachments-only"])
    assert got["days"] == 3650 and got["only"] is True
