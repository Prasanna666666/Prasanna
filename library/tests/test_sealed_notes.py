"""With sealing on, the reader's own notes (what it is reading now, its progress, the files it could not read, what it found) are sealed too, so no file name is left readable on the shared volume; the app still shows them. The mail caches that only the reader reads keep hashes, not paths (review item B1)."""

import json

import pytest

from library import appstate, batch, mailread, parser, readreport, scanstatus, seal


@pytest.fixture
def keys(monkeypatch):
    private, public = seal.generate_keypair()
    for name in ("LIBRARY_HANDOVER_PRIVATE_KEY", "LIBRARY_HANDOVER_PRIVATE_KEY_FILE", "LIBRARY_HANDOVER_PUBLIC_KEY"):
        monkeypatch.delenv(name, raising=False)
    return private, public


# ---- the note format ----------------------------------------------------------------------------------------------------------
def test_a_plain_note_is_read_as_before_and_a_sealed_one_with_the_right_key(tmp_path, keys, monkeypatch):
    private, public = keys
    plain = tmp_path / "plain"
    plain.write_text("hello\nreading")
    assert seal.read_note(plain) == "hello\nreading"
    sealed = tmp_path / "sealed"
    sealed.write_bytes(seal.seal_note("name.pdf\nreading the text", public))
    assert b"name.pdf" not in sealed.read_bytes()
    monkeypatch.setenv("LIBRARY_HANDOVER_PRIVATE_KEY", private)
    assert seal.read_note(sealed) == "name.pdf\nreading the text"


def test_a_sealed_note_without_the_key_or_with_a_wrong_one_is_an_error_a_caller_can_ignore(tmp_path, keys, monkeypatch):
    _, public = keys
    sealed = tmp_path / "sealed"
    sealed.write_bytes(seal.seal_note("secret.pdf", public))
    with pytest.raises(seal.SealError):
        seal.read_note(sealed)  # no key
    monkeypatch.setenv("LIBRARY_HANDOVER_PRIVATE_KEY", seal.generate_keypair()[0])
    with pytest.raises(seal.SealError):
        seal.read_note(sealed)  # a valid but wrong key
    monkeypatch.setenv("LIBRARY_HANDOVER_PRIVATE_KEY", "not-hex")
    with pytest.raises(seal.SealError):
        seal.read_note(sealed)  # a malformed key


def test_write_note_seals_only_when_the_public_key_is_given(tmp_path, keys, monkeypatch):
    _, public = keys
    batch.write_note(tmp_path / "a", "report.pdf\nreading")
    assert (tmp_path / "a").read_text() == "report.pdf\nreading"
    monkeypatch.setenv(batch.HANDOVER_PUBLIC_KEY, public)
    batch.write_note(tmp_path / "b", "report.pdf\nreading")
    assert (tmp_path / "b").read_bytes().startswith(seal.NOTE_MAGIC) and b"report.pdf" not in (tmp_path / "b").read_bytes()


# ---- the app still shows what the reader says -----------------------------------------------------------------------------------
def test_the_app_reads_sealed_notes_for_its_card_and_shows_nothing_when_it_cannot_open_them(tmp_path, keys, monkeypatch):
    private, public = keys
    monkeypatch.setattr(appstate, "parsed_dir", lambda: tmp_path)
    monkeypatch.setenv(batch.HANDOVER_PUBLIC_KEY, public)
    batch.write_note(tmp_path / ".now", "invoice-ACCT.pdf\nreading the text")
    batch.write_note(tmp_path / ".progress", json.dumps({"documents": 3, "mails": 2, "attachments": 1}))
    batch.write_note(tmp_path / ".unread-files", json.dumps(["locked.pdf: locked with a password"]))
    batch.write_note(tmp_path / ".found", json.dumps({"documents": 9, "mails": 4, "by_folder": {"finance": 9}}))
    batch.write_note(tmp_path / ".failed.json", json.dumps([{"name": "locked.pdf", "reason": "locked"}]))
    monkeypatch.delenv(batch.HANDOVER_PUBLIC_KEY)
    monkeypatch.setenv("ATLAS_PARSED", str(tmp_path))

    monkeypatch.setenv("LIBRARY_HANDOVER_PRIVATE_KEY", private)
    assert scanstatus._progress()["documents"] == 3
    assert scanstatus._unread_files() == ["locked.pdf: locked with a password"]
    assert scanstatus._found()["documents"] == 9
    assert readreport._json(".failed.json") == [{"name": "locked.pdf", "reason": "locked"}]
    assert scanstatus._reading_now({})["name"] == "invoice-ACCT.pdf"

    monkeypatch.delenv("LIBRARY_HANDOVER_PRIVATE_KEY")  # no key: the card shows nothing, and nothing crashes
    assert scanstatus._progress() == {} and scanstatus._unread_files() == [] and scanstatus._found() == {}
    assert readreport._json(".failed.json") is None and scanstatus._reading_now({}) is None


# ---- what the reader cannot seal to a public key: hashed, not plain ---------------------------------------------------------------
def test_the_mail_cache_keeps_hashes_of_the_paths_and_still_answers_have_i_seen_this(tmp_path):
    out, root = tmp_path / "out", tmp_path / "Mail"
    cache_file, seen = mailread._seen_cache(out, root)
    seen["Mailboxes/Work-Account-GUID/INBOX.mbox/Messages/179240.emlx"] = "stamp-1"
    seen.update({"Mailboxes/Work-Account-GUID/Sent.mbox/Messages/1.emlx": "bulk:stamp-2"})
    mailread.bulkmail._save_seen(cache_file, seen)
    text = cache_file.read_text()
    assert "Work-Account-GUID" not in text and "179240" not in text and "INBOX" not in text
    _, again = mailread._seen_cache(out, root)
    assert again.get("Mailboxes/Work-Account-GUID/INBOX.mbox/Messages/179240.emlx") == "stamp-1"
    assert again.get("Mailboxes/Work-Account-GUID/INBOX.mbox/Messages/other.emlx") is None


def test_the_old_caches_that_kept_plain_paths_are_removed_at_the_start_of_a_round(tmp_path):
    for legacy in batch.LEGACY_STATE:
        (tmp_path / legacy).mkdir()
        (tmp_path / legacy / "x.json").write_text('{"Mailboxes/Work-Account-GUID/1.emlx": "s"}')
    batch.forget_legacy_state(tmp_path)
    assert not any((tmp_path / legacy).exists() for legacy in batch.LEGACY_STATE)


# ---- the whole reader, then everything on the volume ------------------------------------------------------------------------------
def test_after_a_real_round_with_sealing_on_no_file_name_and_no_text_is_readable_anywhere_on_the_volume(tmp_path, keys, monkeypatch):
    private, public = keys
    inbox, out = tmp_path / "in", tmp_path / "out"
    inbox.mkdir()
    (inbox / "ACCTNAME9999-report.txt").write_text("Marker word ZEBRAQUARTZ here. Glucose 5,2 mmol/L.")
    (inbox / "secret-STATEMENT8888.pdf").write_bytes(b"%PDF-1.4 this is not a real pdf")  # cannot be read: its name goes into the notes
    monkeypatch.setenv(batch.HANDOVER_PUBLIC_KEY, public)
    parser.main(["--once", "--inbox", str(inbox), "--out", str(out)])
    needles = (b"ACCTNAME9999", b"STATEMENT8888", b"ZEBRAQUARTZ", b"report.txt", b"Glucose")
    found = []
    for f in out.rglob("*"):
        if f.is_file():
            data = f.read_bytes() + str(f.relative_to(out)).encode()
            found += [(str(f.relative_to(out))[:30], n.decode()) for n in needles if n in data]
    assert found == []
    assert any(f.name.endswith(".sealed") for f in out.iterdir())  # the sealed result is there
    monkeypatch.setenv("LIBRARY_HANDOVER_PRIVATE_KEY", private)  # and the right key still reads the note about the unread file
    assert "STATEMENT8888" in seal.read_note(out / ".unread-files")


def test_the_same_round_without_sealing_still_leaves_notes_readable_so_the_test_above_proves_something(tmp_path, keys):
    inbox, out = tmp_path / "in", tmp_path / "out"
    inbox.mkdir()
    (inbox / "secret-STATEMENT8888.pdf").write_bytes(b"%PDF-1.4 this is not a real pdf")
    parser.main(["--once", "--inbox", str(inbox), "--out", str(out)])
    assert b"STATEMENT8888" in (out / ".unread-files").read_bytes()
