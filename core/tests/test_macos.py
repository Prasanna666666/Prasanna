"""The macOS-side providers, exercised on Linux: a fake `security` tool, folders whose permission the test controls, synthetic `.emlx` files. UNVERIFIED on a Mac."""

from __future__ import annotations

import hashlib
import os
import shlex
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

import pytest
from conftest import KEY, Clock
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from test_models import entry_dict

from atlas_core.access import GRANTED, MISSING, UNKNOWN, AllowAll
from atlas_core.designation import AnchorError, DesignationStore, Intent, OnboardingDecision
from atlas_core.host import HostEnv, HostOptions, HostUnavailable, build_config, load_manifest
from atlas_core.macos import MAX_EMLX_BYTES, EmlxMailbox, FolderPermissions, KeychainAnchor, KeychainError, KeychainItems
from atlas_core.mail import MailIndex
from atlas_core.models import canonical


class FakeSecurity:
    """Behaves like the parts of `security` this code uses, over a dict; records every command line it was given."""

    def __init__(self) -> None:
        self.items: dict[tuple[str, str], str] = {}
        self.argvs: list[list[str]] = []
        self.fail = False

    def __call__(self, argv, input=None, **kw):
        self.argvs.append(list(argv))
        done = subprocess.CompletedProcess(argv, 0, "", "")
        if self.fail:
            done.returncode = 1
            return done
        if argv[1] == "find-generic-password":
            key = (argv[argv.index("-a") + 1], argv[argv.index("-s") + 1])
            if key in self.items:
                done.stdout = self.items[key] + "\n"
            else:
                done.returncode = 44
        elif argv[1] == "delete-generic-password":
            key = (argv[argv.index("-a") + 1], argv[argv.index("-s") + 1])
            done.returncode = 0 if self.items.pop(key, None) is not None else 44
        elif argv[1] == "-i":
            parts = shlex.split(input)
            assert parts[0] == "add-generic-password"
            self.items[(parts[parts.index("-a") + 1], parts[parts.index("-s") + 1])] = parts[parts.index("-w") + 1]
        return done


# ---- Keychain items and the anchor -------------------------------------------------------------------------------------------------------------------------------------------
def test_each_store_gets_its_own_random_key_created_once_and_never_on_a_command_line():
    sec = FakeSecurity()
    items = KeychainItems("owner", sec)
    first = {n: items.secret(n) for n in ("task-store", "designation-store", "documents-index")}
    assert len(set(first.values())) == 3 and all(len(v) == 64 and int(v, 16) >= 0 for v in first.values())
    assert {n: items.secret(n) for n in first} == first  # created once, then read back
    assert not any(v in " ".join(argv) for argv in sec.argvs for v in first.values())  # the value only travels on standard input


def test_a_failing_keychain_is_a_content_free_error():
    sec = FakeSecurity()
    sec.fail = True
    with pytest.raises(KeychainError) as e:
        KeychainItems("owner", sec).secret("task-store")
    assert str(e.value) in ("read", "write")


def test_the_keychain_anchor_follows_the_two_phase_rules_and_survives_a_restart():
    sec = FakeSecurity()
    anchor = KeychainAnchor(KeychainItems("owner", sec))
    assert anchor.read() is None
    anchor.initialize(0, "genesis")
    anchor.prepare(1, "h1", Intent("documents", "owner_withdrawn", "request-00001"))
    with pytest.raises(AnchorError, match="pending"):
        anchor.prepare(2, "h2", None)  # one unresolved change at a time
    again = KeychainAnchor(KeychainItems("owner", sec))  # a new process, the same Keychain
    record = again.read()
    assert (
        record
        and (record.seq, record.head) == (0, "genesis")
        and record.pending
        and record.pending.intent == Intent("documents", "owner_withdrawn", "request-00001")
    )
    again.commit(1, "h1")
    with pytest.raises(AnchorError, match="backwards"):
        again.prepare(1, "h1", None)
    again.prepare(2, "h2", None)
    again.abort()
    assert again.read().pending is None and again.read().seq == 1
    again.reset()
    assert again.read() is None


def test_an_unavailable_keychain_makes_the_anchor_refuse_with_oserror_so_the_store_fails_closed():
    sec = FakeSecurity()
    anchor = KeychainAnchor(KeychainItems("owner", sec))
    anchor.initialize(0, "g")
    sec.fail = True
    for call in (anchor.read, lambda: anchor.prepare(1, "h", None), lambda: anchor.commit(1, "h")):
        with pytest.raises(OSError, match="anchor unavailable"):
            call()


def test_a_designation_store_runs_on_the_keychain_anchor_and_detects_a_restored_older_database(tmp_path):
    sec, clock = FakeSecurity(), Clock()
    anchor = KeychainAnchor(KeychainItems("owner", sec))
    store = DesignationStore(tmp_path / "d.db", KEY, clock, anchor=anchor)
    store.apply(OnboardingDecision(enable=frozenset({"documents"})), "request-000001")
    snapshot = (tmp_path / "d.db").read_bytes()
    store.withdraw("documents", "request-000002")
    store.close()
    (tmp_path / "d.db").write_bytes(snapshot)  # the owner (or an attacker) restores the older database where documents is still enabled
    restored = DesignationStore(tmp_path / "d.db", KEY, clock, anchor=KeychainAnchor(KeychainItems("owner", sec)))
    assert restored.grants_for("documents") == [] or all(
        g["revoked"] for g in restored.grants_for("documents")
    )  # the Keychain record says it was withdrawn: no grant is honoured


# ---- the folder-permission probe ------------------------------------------------------------------------------------------------------------------------------------------------
def test_a_listable_folder_is_evidence_of_access_a_refusal_of_its_absence_and_anything_else_is_no_evidence(tmp_path, monkeypatch):
    docs, mail, gone = tmp_path / "docs", tmp_path / "mail", tmp_path / "gone"
    docs.mkdir()
    mail.mkdir()
    probe = FolderPermissions({"documents": docs, "mail": mail, "other": gone})
    assert probe.current("documents").state == GRANTED
    assert probe.current("other").state == UNKNOWN and probe.current("nothing-configured").state == UNKNOWN
    real = os.scandir

    def refuse(path, *a, **k):
        if Path(path) == mail:
            raise PermissionError(1, "Operation not permitted")  # what macOS gives for a folder TCC has not allowed
        return real(path, *a, **k)

    monkeypatch.setattr("atlas_core.macos.os.scandir", refuse)
    evidence = probe.current("mail")
    assert evidence.state == MISSING and evidence.source_type == "mail" and probe.current("documents").state == GRANTED


def test_the_probe_asks_the_system_every_time_and_keeps_no_cache(tmp_path, monkeypatch):
    folder = tmp_path / "f"
    folder.mkdir()
    probe = FolderPermissions({"documents": folder})
    assert probe.current("documents").state == GRANTED
    folder.rmdir()
    assert probe.current("documents").state == UNKNOWN  # the folder went: no stale "granted"


# ---- the Apple Mail reader --------------------------------------------------------------------------------------------------------------------------------------------------------
def emlx(path: Path, message: bytes, mtime: float | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(str(len(message)).encode() + b"\n" + message + b"\n<?xml version='1.0'?><plist></plist>\n")
    if mtime is not None:
        os.utime(path, (mtime, mtime))
    return path


PLAIN = b"From: Alice <alice@example.invalid>\nTo: me@example.invalid\nSubject: Quote\nMessage-ID: <q1@example.invalid>\nDate: Sat, 14 Mar 2026 09:30:00 +0000\n\nThe total due is 1250.50 euro.\n"
MULTI = (
    b"From: Bob <bob@example.invalid>\nSubject: With attachment\nMessage-ID: <m2@example.invalid>\nDate: Sun, 15 Mar 2026 09:30:00 +0000\nMIME-Version: 1.0\n"
    b'Content-Type: multipart/mixed; boundary="B"\n\n--B\nContent-Type: text/plain\n\nBody words here.\n--B\nContent-Type: application/pdf\nContent-Disposition: attachment; filename="secret-name.pdf"\n'
    b"Content-Transfer-Encoding: base64\n\nQVRUQUNILVNFTlRJTkVMLTU1MzA=\n--B--\n"
)  # the attachment decodes to ATTACH-SENTINEL-5530


def test_the_reader_returns_only_the_five_stored_fields_and_never_an_attachment(tmp_path):
    emlx(tmp_path / "INBOX.mbox/Messages/1.emlx", PLAIN, 1_700_000_000)
    emlx(tmp_path / "INBOX.mbox/Messages/2.emlx", MULTI, 1_700_000_100)
    box = EmlxMailbox(tmp_path)
    page = box.list_page(None, 10)
    assert [i.message_id for i in page.items] == ["<m2@example.invalid>", "<q1@example.invalid>"] and page.next_cursor is None  # newest first
    one, two = box.read("<q1@example.invalid>"), box.read("<m2@example.invalid>")
    assert set(one) == {"message_id", "sender", "date", "subject", "body"} and "1250.50" in one["body"] and one["subject"] == "Quote"
    assert two["body"].strip() == "Body words here." and "ATTACH" not in str(two) and "secret-name" not in str(two)
    assert one["date"].startswith("2026-03-14T09:30:00")


def test_only_the_plain_text_part_is_read_even_when_an_html_alternative_exists_and_html_only_gives_an_empty_body(tmp_path):
    alt = (
        b"From: C <c@example.invalid>\nSubject: Alt\nMessage-ID: <alt@example.invalid>\nDate: Mon, 16 Mar 2026 09:30:00 +0000\nMIME-Version: 1.0\n"
        b'Content-Type: multipart/alternative; boundary="A"\n\n--A\nContent-Type: text/plain\n\nplain words\n--A\nContent-Type: text/html\n\n<p>HTML-ONLY-MARKER</p>\n--A--\n'
    )
    html = b"From: D <d@example.invalid>\nSubject: H\nMessage-ID: <h@example.invalid>\nDate: Mon, 16 Mar 2026 09:30:00 +0000\nContent-Type: text/html\n\n<p>only html</p>\n"
    emlx(tmp_path / "a/1.emlx", alt, 1_700_000_000)
    emlx(tmp_path / "a/2.emlx", html, 1_700_000_001)
    box = EmlxMailbox(tmp_path)
    box.list_page(None, 10)
    assert box.read("<alt@example.invalid>")["body"].strip() == "plain words"
    assert box.read("<h@example.invalid>")["body"] == ""  # no plain part: nothing is invented from the html


def test_paging_duplicates_links_oversized_and_malformed_files_are_all_handled(tmp_path):
    for n in range(7):
        emlx(tmp_path / f"a/{n}.emlx", PLAIN.replace(b"q1@", f"p{n}@".encode()), 1_700_000_000 + n)
    emlx(tmp_path / "b/older.emlx", PLAIN.replace(b"q1@", b"p6@"), 1_600_000_000)  # the same Message-ID again, older: one entry, the newest copy
    (tmp_path / "evil").symlink_to("/etc")  # a linked folder is never followed
    (tmp_path / "link.emlx").symlink_to(tmp_path / "a/0.emlx")  # nor a linked file
    (tmp_path / "bad.emlx").write_bytes(b"not a count\nbody")
    (tmp_path / "huge.emlx").write_bytes(b"99999999\n" + b"x" * (9 * 1024 * 1024))
    box = EmlxMailbox(tmp_path)
    first = box.list_page(None, 3)
    second = box.list_page(first.next_cursor, 3)
    third = box.list_page(second.next_cursor, 3)
    ids = [i.message_id for p in (first, second, third) for i in p.items]
    assert len(ids) == len(set(ids)) and "<p6@example.invalid>" in ids and third.next_cursor is None
    assert box.read("<p6@example.invalid>")["subject"] == "Quote"
    assert box.read("<nothing@example.invalid>") is None
    fallback = [i for i in ids if i.startswith("emlx.")]  # no usable Message-ID (the malformed and the oversized file): a safe name made from the file's place
    assert len(fallback) == 2 and all(all(c.isalnum() or c in "._@<>+=-" for c in i) for i in fallback)
    assert all(box.read(i) is None for i in fallback)  # and neither is readable: never truncated, never guessed


def test_a_message_that_changes_gets_a_new_change_marker(tmp_path):
    path = emlx(tmp_path / "a/1.emlx", PLAIN, 1_700_000_000)
    box = EmlxMailbox(tmp_path)
    before = box.list_page(None, 10).items[0].version
    emlx(path, PLAIN + b"more\n", 1_700_000_500)
    assert box.list_page(None, 10).items[0].version != before


def test_the_mail_index_runs_over_the_reader_and_answers_from_plain_text_only(tmp_path):
    emlx(tmp_path / "x/1.emlx", PLAIN, 1_700_000_000)
    emlx(tmp_path / "x/2.emlx", MULTI, 1_700_000_100)
    index = MailIndex(tmp_path / "mail.db", KEY, EmlxMailbox(tmp_path / "x"), "mail", access=AllowAll())
    index.scan()
    while index.run(10)["pending"]:
        pass
    assert index.coverage()["complete"] and index.coverage()["searched"] == 2
    found = list(index.search("mail", "total due euro"))
    assert found and "1250.50" in found[0]["text"]
    assert not list(index.search("mail", "ATTACH-SENTINEL-5530 secret-name"))


# ---- the host assembly -----------------------------------------------------------------------------------------------------------------------------------------------------------
def signed_manifest(models: Path, pub: Path) -> None:
    from atlas_core.models import MANIFEST_VERSION

    key = Ed25519PrivateKey.generate()
    models.mkdir(parents=True, exist_ok=True)
    doc = canonical({"manifest_version": MANIFEST_VERSION, "entries": [entry_dict("primary-1", {"w.safetensors": b"w"}, runtime="mlx")]})
    (models / "manifest.json").write_bytes(doc)
    (models / "manifest.sig").write_bytes(key.sign(doc))
    pub.write_bytes(key.public_key().public_bytes_raw())


def _folders(permissions):
    """The folder provider under whatever wrappers the host put on (the native sources' provider, the own-store provider)."""
    while not isinstance(permissions, FolderPermissions):
        permissions = permissions._inner
    return permissions


def test_the_host_builds_a_config_from_the_keychain_folders_and_an_installed_signed_manifest(tmp_path):
    docs, mail = tmp_path / "Documents", tmp_path / "Mail"
    docs.mkdir()
    mail.mkdir()
    signed_manifest(tmp_path / "data" / "models", tmp_path / "pub.key")
    sec = FakeSecurity()
    config = build_config(
        tmp_path / "data", tmp_path / "s", "boot-code-0123456789abc", HostOptions(("documents", docs), ("mail", mail), tmp_path / "pub.key"), HostEnv("darwin", sec, "owner", runtime=object())
    )  # fmt: skip
    finance_key = next(iter(config.records.values()))[1]
    keys = {config.task_key, config.designation_key, config.documents_key, config.mail_key, config.edits_key, finance_key}
    assert len(keys) == 6 and all(
        len(k) == 64 for k in keys
    )  # every store has a key of its own, including the Finance index and len(config.model_record_key) == 32
    assert (
        config.outbox is None and config.erase is None and config.require_restore_drill is True
    )  # no sender, no eraser, and restricted domains wait for a restore drill
    assert isinstance(config.anchor, KeychainAnchor) and config.bootstrap_code == "boot-code-0123456789abc"
    assert [e.model_id for e in config.manifest.entries()] == ["primary-1"] and config.documents == ("documents", docs) and config.mailbox[0] == "mail"
    assert isinstance(config.mailbox[1], EmlxMailbox) and isinstance(_folders(config.os_permissions), FolderPermissions)
    again = build_config(tmp_path / "data", tmp_path / "s", None, HostOptions(), HostEnv("darwin", sec, "owner", runtime=object()))
    assert again.task_key == config.task_key  # the same Keychain items on the next start


def test_a_missing_or_badly_signed_manifest_means_no_models_never_an_unsigned_one(tmp_path):
    assert load_manifest(tmp_path, None).entries() == []
    signed_manifest(tmp_path, tmp_path / "pub.key")
    assert len(load_manifest(tmp_path, tmp_path / "pub.key").entries()) == 1
    (tmp_path / "manifest.json").write_bytes((tmp_path / "manifest.json").read_bytes() + b" ")  # altered after signing
    assert load_manifest(tmp_path, tmp_path / "pub.key").entries() == []
    (tmp_path / "pub.key").write_bytes(b"short")
    assert load_manifest(tmp_path, tmp_path / "pub.key").entries() == []


def test_the_host_refuses_off_a_mac_and_when_the_keychain_fails(tmp_path):
    with pytest.raises(HostUnavailable, match="macOS"):
        build_config(tmp_path, tmp_path / "s", "x" * 20, HostOptions(), HostEnv("linux"))
    sec = FakeSecurity()
    sec.fail = True
    with pytest.raises(HostUnavailable, match="Keychain"):
        build_config(tmp_path, tmp_path / "s", "x" * 20, HostOptions(), HostEnv("darwin", sec, "owner"))


def test_a_whole_core_built_by_the_host_indexes_documents_and_apple_mail_after_consent_and_purges_on_withdrawal(tmp_path):
    from conftest import SENTINEL_QUESTION  # noqa: F401
    from core_factory import StubRuntime

    from atlas_core.app import Core

    docs, mail = tmp_path / "Documents", tmp_path / "Mail"
    docs.mkdir()
    (docs / "invoice.txt").write_text("Invoice ACME-2041: the total due is 1250.50 euro.")
    emlx(mail / "x/1.emlx", PLAIN, 1_700_000_000)
    sec = FakeSecurity()
    short = Path(tempfile.mkdtemp(prefix="atl", dir="/tmp"))  # macOS limits a Unix socket path to 104 bytes; pytest's tmp_path is longer
    config = build_config(
        tmp_path / "data",
        short / "s",
        "boot-code-0123456789abc",
        HostOptions(("documents", docs), ("mail", mail)),
        HostEnv("darwin", sec, "owner", runtime=StubRuntime()),
    )
    core = Core(config)
    try:
        core.start()
        core.designation.apply(OnboardingDecision(enable=frozenset({"documents", "mail"})), "request-host-001")
        for _ in range(300):
            if all(core.indexes[t].coverage()["complete"] for t in ("documents", "mail")):
                break
            time.sleep(0.02)
        assert core.indexes["documents"].coverage()["searched"] == 1 and core.indexes["mail"].coverage()["searched"] == 1
        core.designation.withdraw("mail", "request-host-002")
        assert core.indexes["mail"].coverage()["total"] == 0 and core.indexes["documents"].coverage()["searched"] == 1
    finally:
        core.close()
        shutil.rmtree(short, ignore_errors=True)


# --- path confinement: no pathname is validated and then reopened (review 6012871766) ---------------------------------------------------------------------------

OUTSIDE = (
    b"From: Mallory <mallory@example.invalid>\nSubject: OUTSIDE-SENTINEL-9917\nMessage-ID: <outside@example.invalid>\nDate: Sat, 14 Mar 2026 09:30:00 +0000\n\n"
    b"OUTSIDE-SENTINEL-9917 body that must never be read.\n"
)


def _nothing_from_outside(box: EmlxMailbox) -> None:
    page = box.list_page(None, 50)
    assert all("outside" not in item.message_id for item in page.items)  # never identified, never listed
    assert box.read("<outside@example.invalid>") is None  # never read
    for item in page.items:
        got = box.read(item.message_id)
        assert got is None or "OUTSIDE-SENTINEL-9917" not in repr(got)


def test_a_file_swapped_for_a_symlink_between_discovery_and_open_is_never_followed(tmp_path):
    root, outside = tmp_path / "Mail", tmp_path / "elsewhere"
    victim = emlx(root / "INBOX.mbox/Messages/1.emlx", PLAIN, 1_700_000_000)
    emlx(root / "INBOX.mbox/Messages/2.emlx", PLAIN.replace(b"q1@", b"q2@"), 1_700_000_100)
    target = emlx(outside / "secret.emlx", OUTSIDE, 1_700_000_200)
    box = EmlxMailbox(root)
    swapped: list[str] = []

    def race(stage: str, parts: tuple[str, ...]) -> None:  # runs after the name was discovered and before it is opened
        if parts[-1] == "1.emlx" and not swapped:
            victim.unlink()
            victim.symlink_to(target)
            swapped.append(stage)

    box._before_open = race
    page = box.list_page(None, 50)
    assert swapped and [i.message_id for i in page.items] == ["<q2@example.invalid>"]  # the swapped file is skipped; the honest one is listed
    _nothing_from_outside(box)


def test_a_parent_directory_replaced_by_a_symlink_between_discovery_and_open_is_never_followed(tmp_path):
    root, outside = tmp_path / "Mail", tmp_path / "elsewhere"
    emlx(root / "INBOX.mbox/Messages/1.emlx", PLAIN, 1_700_000_000)
    emlx(root / "OTHER.mbox/Messages/2.emlx", PLAIN.replace(b"q1@", b"q2@"), 1_700_000_100)
    emlx(outside / "Messages/1.emlx", OUTSIDE, 1_700_000_200)
    box = EmlxMailbox(root)
    swapped: list[str] = []

    def race(stage: str, parts: tuple[str, ...]) -> None:
        if parts[0] == "INBOX.mbox" and not swapped:
            shutil.rmtree(root / "INBOX.mbox")
            (root / "INBOX.mbox").symlink_to(outside)  # the whole folder now points outside the root
            swapped.append(stage)

    box._before_open = race
    page = box.list_page(None, 50)
    assert swapped and [i.message_id for i in page.items] == ["<q2@example.invalid>"]
    _nothing_from_outside(box)


def test_a_parent_directory_replaced_after_the_scan_is_never_followed_when_the_body_is_read(tmp_path):
    root, outside = tmp_path / "Mail", tmp_path / "elsewhere"
    emlx(root / "INBOX.mbox/Messages/1.emlx", PLAIN, 1_700_000_000)
    emlx(outside / "Messages/1.emlx", OUTSIDE.replace(b"outside@", b"q1@"), 1_700_000_200)  # even the identity matches the one the scan cached
    box = EmlxMailbox(root)
    assert [i.message_id for i in box.list_page(None, 10).items] == ["<q1@example.invalid>"]
    shutil.rmtree(root / "INBOX.mbox")
    (root / "INBOX.mbox").symlink_to(outside)  # after discovery, before the body is read
    assert box.read("<q1@example.invalid>") is None


def test_the_same_message_is_read_from_the_same_descriptor_that_identified_it(tmp_path):
    """The file is replaced by a different file after it was opened for identification: the answer must still be one consistent message, never a mix."""
    root = tmp_path / "Mail"
    emlx(root / "a/1.emlx", PLAIN, 1_700_000_000)
    box = EmlxMailbox(root)
    opened: list[tuple[str, ...]] = []
    box._before_open = lambda stage, parts: opened.append(parts)
    box.list_page(None, 10)
    box.read("<q1@example.invalid>")
    assert opened == [
        ("a", "1.emlx"),
        ("a", "1.emlx"),
    ]  # one confined open for the scan, one for the read, each from the pinned root: no other open of the name exists


def test_the_size_limit_and_a_fifo_and_a_symlinked_root_are_handled_without_following_or_hanging(tmp_path):
    root = tmp_path / "Mail"
    emlx(root / "a/1.emlx", PLAIN, 1_700_000_000)
    os.mkfifo(root / "a/2.emlx")  # a FIFO must not block the scan
    big = root / "a/3.emlx"
    big.write_bytes(b"9999999\n" + b"x" * (MAX_EMLX_BYTES + 10))
    box = EmlxMailbox(root)
    big_id = "emlx." + hashlib.sha256(os.sep.join(("a", "3.emlx")).encode()).hexdigest()[:24]
    assert {i.message_id for i in box.list_page(None, 10).items} == {
        "<q1@example.invalid>",
        big_id,
    }  # the FIFO was skipped; the oversized file is listed by name only
    assert box.read(big_id) is None  # and is never read (reported unreadable, not truncated)
    assert box.read("<q1@example.invalid>")["subject"] == "Quote"
    link = tmp_path / "RootLink"
    link.symlink_to(root)
    assert EmlxMailbox(link).list_page(None, 10).items == []  # a designated root that is itself a link is not followed


def test_a_value_that_is_not_plain_is_encoded_before_it_reaches_the_security_command_parser_and_decoded_on_read():
    """A real macOS run showed `security -i` does not parse single quotes or `$` as a shell does; only letters, digits `.`, `_`, `-` go through as they are."""
    sent: list[str] = []
    stored: dict[str, str] = {}

    def runner(command, input=None, **kwargs):
        if input:
            sent.append(input)
            service = input.split(" -s ")[1].split(" ")[0]
            stored[service] = input.rsplit(" -w ", 1)[1].strip()
            return subprocess.CompletedProcess(command, 0, "", "")
        return subprocess.CompletedProcess(command, 0, stored["svc"] + "\n", "")

    box = KeychainItems("owner", runner=runner)
    hostile = 'it\'s a $(whoami) "value" with spaces; and `ticks`'
    box.write("svc", hostile)
    assert hostile not in sent[0] and "$(" not in sent[0] and "'" not in sent[0].split(" -w ")[1]  # nothing the parser could misread
    assert box.read("svc") == hostile
    box.write("svc", "a" * 64)  # a hex store key travels unchanged
    assert sent[1].rstrip().endswith(" -w " + "a" * 64) and box.read("svc") == "a" * 64


OTHER = (
    b"From: Eve <eve@example.invalid>\nSubject: SWAPPED-IN-BODY-4417\nMessage-ID: <other@example.invalid>\nDate: Sat, 14 Mar 2026 09:30:00 +0000\n\n"
    b"SWAPPED-IN-BODY-4417 belongs to a different message.\n"
)


def test_a_regular_file_replaced_by_a_different_message_after_listing_is_never_returned_under_the_old_identity(tmp_path):
    root = tmp_path / "Mail"
    victim = emlx(root / "INBOX.mbox/Messages/1.emlx", PLAIN, 1_700_000_000)
    box = EmlxMailbox(root)
    assert [i.message_id for i in box.list_page(None, 10).items] == ["<q1@example.invalid>"]
    emlx(victim, OTHER, 1_700_000_500)  # a plain file replaced by another message's file (no symlink anywhere)
    got = box.read("<q1@example.invalid>")
    assert got is None or "SWAPPED-IN-BODY-4417" not in repr(got)
    assert box.read("<other@example.invalid>") is not None  # after a fresh listing the new message is read, under its own identity
    assert "SWAPPED-IN-BODY-4417" in box.read("<other@example.invalid>")["body"]


def test_the_same_message_edited_in_place_is_read_consistently(tmp_path):
    root = tmp_path / "Mail"
    path = emlx(root / "a/1.emlx", PLAIN, 1_700_000_000)
    box = EmlxMailbox(root)
    box.list_page(None, 10)
    emlx(path, PLAIN.replace(b"1250.50", b"9999.00"), 1_700_000_600)  # same Message-ID, new body
    got = box.read("<q1@example.invalid>")
    assert got is not None and "9999.00" in got["body"] and got["message_id"] == "<q1@example.invalid>"


# --- the EMLX reader reads only what it needs: attachments after the text are never read; lengths are validated (review 6013386354 / 6013411500) ------------------

SENT = b"ATTACHMENT-OCTETS-SENTINEL-7731"


def _mixed(attachment_first: bool = False, padding: int = 20_000) -> bytes:
    text = b"Content-Type: text/plain; charset=utf-8\n\nThe total due is 1250.50 euro.\n"
    attach = (
        b'Content-Type: application/pdf\nContent-Disposition: attachment; filename="a.pdf"\nContent-Transfer-Encoding: base64\n\n'
        + (b"QUJD" * 19 + b"\n") * (padding // 77)  # filler, so the sentinel lies well beyond the first chunk of the attachment
        + SENT
        + b"\n"
    )
    parts = [attach, text] if attachment_first else [text, attach]
    body = b"".join(b"--B\n" + part + b"\n" for part in parts) + b"--B--\n"
    return (
        b"From: Alice <alice@example.invalid>\nSubject: With attachment\nMessage-ID: <big@example.invalid>\nDate: Sat, 14 Mar 2026 09:30:00 +0000\nMIME-Version: 1.0\nContent-Type: multipart/mixed; boundary=B\n\n"
        + body
    )


class _Reads:
    """Records every byte the reader gets from the operating system."""

    def __init__(self, monkeypatch):
        self.chunks: list[bytes] = []
        real = os.read

        def read(fd, n):
            data = real(fd, n)
            self.chunks.append(data)
            return data

        monkeypatch.setattr("atlas_core.macos.os.read", read)

    @property
    def everything(self) -> bytes:
        return b"".join(self.chunks)


def _small_attachment_after_short_text() -> bytes:
    """A short text body immediately followed by a SMALL attachment: both lie inside one 4 KiB window, which is where a fixed-size read-ahead would swallow attachment bytes."""
    return (
        b"From: Alice <alice@example.invalid>\nSubject: Short\nMessage-ID: <short@example.invalid>\nDate: Sat, 14 Mar 2026 09:30:00 +0000\nMIME-Version: 1.0\nContent-Type: multipart/mixed; boundary=B\n\n"
        b"--B\nContent-Type: text/plain; charset=utf-8\n\nThe total due is 1250.50 euro.\n--B\n"
        b'Content-Type: application/pdf\nContent-Disposition: attachment; filename="a.pdf"\nContent-Transfer-Encoding: base64\n\n' + SENT + b"\n--B--\n"
    )


def _count_prefix(message: bytes) -> int:
    return len(str(len(message)).encode()) + 1  # the byte-count line before the message


def test_not_one_attachment_byte_is_read_even_when_it_lies_within_the_same_4k_window_as_the_text(tmp_path, monkeypatch):
    raw = _small_attachment_after_short_text()
    emlx(tmp_path / "a/1.emlx", raw, 1_700_000_000)
    box = EmlxMailbox(tmp_path)
    box.list_page(None, 10)
    reads = _Reads(monkeypatch)
    got = box.read("<short@example.invalid>")
    assert got is not None and "1250.50" in got["body"]
    assert SENT not in reads.everything and b"application/pdf" not in reads.everything  # not the sentinel, not even the next part's headers
    end_of_text_part = _count_prefix(raw) + raw.index(b"--B\nContent-Type: application/pdf") + len(b"--B\n")
    assert len(reads.everything) == end_of_text_part  # reading stopped exactly after the delimiter line that ends the text part: not one byte further


def test_listing_reads_exactly_the_count_line_and_the_headers_and_not_the_body(tmp_path, monkeypatch):
    raw = _small_attachment_after_short_text()
    emlx(tmp_path / "a/1.emlx", raw, 1_700_000_000)
    reads = _Reads(monkeypatch)
    page = EmlxMailbox(tmp_path).list_page(None, 10)
    assert [i.message_id for i in page.items] == ["<short@example.invalid>"]
    assert len(reads.everything) == _count_prefix(raw) + raw.index(b"\n\n") + 2  # through the blank line that ends the headers
    assert b"--B" not in reads.everything and SENT not in reads.everything


def test_a_header_block_is_read_up_to_its_blank_line_and_no_prefetch_reaches_the_payload_behind_it(tmp_path, monkeypatch):
    raw = (
        b"From: A <a@example.invalid>\nSubject: pdf only\nMessage-ID: <pdf@example.invalid>\nDate: Sat, 14 Mar 2026 09:30:00 +0000\nContent-Type: application/pdf\n\n"
        + SENT
        + b"\n"
    )  # a tiny payload right behind the headers
    emlx(tmp_path / "a/1.emlx", raw, 1_700_000_000)
    box = EmlxMailbox(tmp_path)
    reads = _Reads(monkeypatch)
    box.list_page(None, 10)
    got = box.read("<pdf@example.invalid>")
    assert got is not None and got["body"] == ""
    assert SENT not in reads.everything  # across both the listing and the read


def test_an_attachment_before_the_text_makes_the_message_unreadable_and_its_payload_is_never_read(tmp_path, monkeypatch):
    """Finding the text behind an attachment would mean reading the attachment, so the reader refuses: the message is unreadable (and counted as such), not scanned."""
    raw = _mixed(attachment_first=True)
    emlx(tmp_path / "a/1.emlx", raw, 1_700_000_000)
    box = EmlxMailbox(tmp_path)
    box.list_page(None, 10)
    reads = _Reads(monkeypatch)
    assert box.read("<big@example.invalid>") is None
    assert SENT not in reads.everything and b"QUJD" not in reads.everything  # not one byte of the payload
    assert len(reads.everything) <= _count_prefix(raw) + raw.index(b"Content-Transfer-Encoding: base64\n\n") + len(b"Content-Transfer-Encoding: base64\n\n")


def test_in_a_nested_multipart_reading_stops_at_the_delimiter_after_the_text_and_never_reaches_the_html_or_the_attachment(tmp_path, monkeypatch):
    raw = (
        b"From: A <a@example.invalid>\nSubject: Nested\nMessage-ID: <nest2@example.invalid>\nDate: Sat, 14 Mar 2026 09:30:00 +0000\nMIME-Version: 1.0\nContent-Type: multipart/mixed; boundary=OUT\n\n"
        b"--OUT\nContent-Type: multipart/alternative; boundary=IN\n\n--IN\nContent-Type: text/plain; charset=utf-8\n\nThe total due is 1250.50 euro.\n--IN\n"
        b"Content-Type: text/html\n\n<p>HTML-AFTER-TEXT</p>\n--IN--\n--OUT\nContent-Type: application/pdf\nContent-Disposition: attachment; filename=a.pdf\n\n"
        + SENT
        + b"\n--OUT--\n"
    )
    emlx(tmp_path / "a/1.emlx", raw, 1_700_000_000)
    box = EmlxMailbox(tmp_path)
    box.list_page(None, 10)
    reads = _Reads(monkeypatch)
    got = box.read("<nest2@example.invalid>")
    assert got is not None and "1250.50" in got["body"]
    assert SENT not in reads.everything and b"HTML-AFTER-TEXT" not in reads.everything and b"application/pdf" not in reads.everything
    assert len(reads.everything) == _count_prefix(raw) + raw.index(b"--IN\nContent-Type: text/html") + len(
        b"--IN\n"
    )  # exactly through the delimiter line that ends the text part


@pytest.mark.parametrize(
    "tail",
    [
        b"",  # the file ends right after the text part: no closing delimiter at all
        b"--B\nContent-Type: application/pdf\nContent-Disp",  # truncated in the middle of the next part's headers
    ],
    ids=["no-closing-delimiter", "truncated-next-headers"],
)
def test_a_truncated_message_never_reads_beyond_the_end_of_the_file_and_is_not_an_exception(tmp_path, monkeypatch, tail):
    head = (
        b"From: A <a@example.invalid>\nSubject: Cut\nMessage-ID: <cut@example.invalid>\nDate: Sat, 14 Mar 2026 09:30:00 +0000\nMIME-Version: 1.0\nContent-Type: multipart/mixed; boundary=B\n\n"
        b"--B\nContent-Type: text/plain; charset=utf-8\n\nThe total due is 1250.50 euro.\n"
    )
    emlx(tmp_path / "a/1.emlx", head + tail, 1_700_000_000)
    box = EmlxMailbox(tmp_path)
    box.list_page(None, 10)
    reads = _Reads(monkeypatch)
    got = box.read(
        "<cut@example.invalid>"
    )  # unreadable, text, or an empty body (a text part never closed by a delimiter): any is acceptable, an exception is not
    assert got is None or got["body"] in ("", "The total due is 1250.50 euro.") or "1250.50" in got["body"]
    assert len(reads.everything) <= _count_prefix(head + tail) + len(head + tail)


def test_a_multipart_without_a_boundary_never_reads_a_following_attachment(tmp_path, monkeypatch):
    raw = (
        b"From: A <a@example.invalid>\nSubject: NoB\nMessage-ID: <nob@example.invalid>\nDate: Sat, 14 Mar 2026 09:30:00 +0000\nMIME-Version: 1.0\nContent-Type: multipart/mixed\n\n"
        b"--B\nContent-Type: application/pdf\nContent-Disposition: attachment; filename=a.pdf\n\n" + SENT + b"\n--B--\n"
    )
    emlx(tmp_path / "a/1.emlx", raw, 1_700_000_000)
    box = EmlxMailbox(tmp_path)
    box.list_page(None, 10)
    reads = _Reads(monkeypatch)
    got = box.read("<nob@example.invalid>")
    assert got is None or SENT.decode() not in got["body"]
    assert SENT not in reads.everything


def test_reading_a_large_text_body_stays_fast_enough_to_index(tmp_path):
    import time

    body = b"The total due is 1250.50 euro and the rest of the line is ordinary words.\n" * 3000  # about 220 KB of text
    raw = (
        b"From: A <a@example.invalid>\nSubject: Long\nMessage-ID: <long@example.invalid>\nDate: Sat, 14 Mar 2026 09:30:00 +0000\nContent-Type: text/plain; charset=utf-8\n\n"
        + body
    )
    emlx(tmp_path / "a/1.emlx", raw, 1_700_000_000)
    box = EmlxMailbox(tmp_path)
    box.list_page(None, 10)
    started = time.monotonic()
    got = box.read("<long@example.invalid>")
    assert got is not None and got["body"].count("1250.50") == 3000
    assert time.monotonic() - started < 2.0


def test_nested_alternative_parts_choose_the_plain_text_and_skip_html_and_attachments(tmp_path):
    raw = (
        b"From: A <a@example.invalid>\nSubject: Nested\nMessage-ID: <nest@example.invalid>\nDate: Sat, 14 Mar 2026 09:30:00 +0000\nMIME-Version: 1.0\n"
        b"Content-Type: multipart/mixed; boundary=OUT\n\n--OUT\nContent-Type: multipart/alternative; boundary=IN\n\n"
        b"--IN\nContent-Type: text/plain; charset=utf-8\nContent-Transfer-Encoding: quoted-printable\n\nTotal =E2=82=AC1250.50 due\n--IN\nContent-Type: text/html\n\n<p>HTML-NEVER-READ-5512</p>\n--IN--\n"
        b"--OUT\nContent-Type: application/zip\nContent-Disposition: attachment\n\n" + SENT + b"\n--OUT--\n"
    )
    emlx(tmp_path / "a/1.emlx", raw, 1_700_000_000)
    box = EmlxMailbox(tmp_path)
    box.list_page(None, 10)
    got = box.read("<nest@example.invalid>")
    assert got is not None and "€1250.50 due" in got["body"]
    assert b"HTML-NEVER-READ-5512" not in got["body"].encode() and SENT.decode() not in repr(got)


@pytest.mark.parametrize("count_line", [b"9" * 5000, b"\xd9\xa3\xd9\xa0", b"-5", b"12 34", b"", b"0x20"])
def test_a_malformed_or_huge_byte_count_is_unreadable_not_an_exception(tmp_path, count_line):
    path = tmp_path / "a/1.emlx"
    path.parent.mkdir(parents=True)
    path.write_bytes(count_line + b"\n" + PLAIN)
    box = EmlxMailbox(tmp_path)
    page = box.list_page(None, 10)  # listed under its place, never raises
    assert len(page.items) == 1 and page.items[0].message_id.startswith("emlx.")
    assert box.read(page.items[0].message_id) is None


def test_a_declared_length_longer_than_the_file_is_unreadable_never_a_partial_message(tmp_path):
    path = tmp_path / "a/1.emlx"
    path.parent.mkdir(parents=True)
    path.write_bytes(str(len(PLAIN) + 500).encode() + b"\n" + PLAIN)  # claims 500 bytes more than exist
    box = EmlxMailbox(tmp_path)
    page = box.list_page(None, 10)
    assert box.read(page.items[0].message_id) is None


def test_bytes_after_the_declared_length_are_not_part_of_the_message(tmp_path):
    path = tmp_path / "a/1.emlx"
    path.parent.mkdir(parents=True)
    path.write_bytes(str(len(PLAIN)).encode() + b"\n" + PLAIN + b"TRAILER-OUTSIDE-THE-COUNT-9921 <?xml plist ?>")
    box = EmlxMailbox(tmp_path)
    box.list_page(None, 10)
    got = box.read("<q1@example.invalid>")
    assert got is not None and "TRAILER-OUTSIDE" not in got["body"]


@pytest.mark.parametrize(
    "premature",
    [b"--OUT--\n", b"--OUT\n"],
    ids=["outer-closing-while-inner-open", "outer-opening-while-inner-open"],
)
def test_a_delimiter_of_an_enclosing_multipart_while_an_inner_one_is_open_ends_the_read_without_reading_a_byte_more(tmp_path, monkeypatch, premature):
    """ATLAS-MAIL-032: delimiters nest last-in first-out; a malformed nesting fails closed and the sibling attachment's bytes (and even its headers) are never read."""
    raw = (
        b"From: A <a@example.invalid>\nSubject: Bad nesting\nMessage-ID: <bad@example.invalid>\nDate: Sat, 14 Mar 2026 09:30:00 +0000\nMIME-Version: 1.0\nContent-Type: multipart/mixed; boundary=OUT\n\n"
        b"--OUT\nContent-Type: multipart/alternative; boundary=IN\n\n--IN\nContent-Type: text/html\n\n<p>only html</p>\n"
        + premature
        + b"Content-Type: application/pdf\nContent-Disposition: attachment; filename=a.pdf\n\n"
        + SENT
        + b"\n--OUT--\n"
    )
    emlx(tmp_path / "a/1.emlx", raw, 1_700_000_000)
    box = EmlxMailbox(tmp_path)
    box.list_page(None, 10)
    reads = _Reads(monkeypatch)
    assert box.read("<bad@example.invalid>") is None  # unreadable, never a guess
    assert SENT not in reads.everything and b"application/pdf" not in reads.everything
    assert len(reads.everything) <= _count_prefix(raw) + raw.index(premature, raw.index(b"only html")) + len(
        premature
    )  # not one byte after the premature delimiter line


def test_a_same_size_edit_that_keeps_the_mtime_is_refused_at_once_and_indexed_again_without_a_new_marker(tmp_path):
    """ATLAS-MAIL-024: the change marker (size and mtime) cannot see this edit; the guarded read can, so the row goes back to pending and the new text becomes searchable."""
    path = emlx(tmp_path / "x/1.emlx", PLAIN, 1_700_000_000)
    index = MailIndex(tmp_path / "mail.db", KEY, EmlxMailbox(tmp_path / "x"), "mail", access=AllowAll())
    index.scan()
    while index.run(10)["pending"]:
        pass
    assert list(index.search("mail", "total due euro"))
    stat = os.stat(path)
    path.write_bytes(path.read_bytes().replace(b"1250.50", b"1250.99"))  # the same length
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns))  # and the very same modification time
    assert not list(index.search("mail", "total due euro"))  # never the old text, never a guess, in the meantime
    assert index.coverage()["pending"] == 1 and not index.coverage()["complete"]  # and coverage says so
    index.scan()
    while index.run(10)["pending"]:
        pass
    found = list(index.search("mail", "total due euro"))
    assert found and "1250.99" in found[0]["text"] and "1250.50" not in found[0]["text"]
