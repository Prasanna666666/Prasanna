"""The macOS-side providers, exercised on Linux: a fake `security` tool, folders whose permission the test controls, synthetic `.emlx` files. UNVERIFIED on a Mac."""

from __future__ import annotations

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
from atlas_core.macos import EmlxMailbox, FolderPermissions, KeychainAnchor, KeychainError, KeychainItems
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


def test_the_host_builds_a_config_from_the_keychain_folders_and_an_installed_signed_manifest(tmp_path):
    docs, mail = tmp_path / "Documents", tmp_path / "Mail"
    docs.mkdir()
    mail.mkdir()
    signed_manifest(tmp_path / "data" / "models", tmp_path / "pub.key")
    sec = FakeSecurity()
    config = build_config(
        tmp_path / "data", tmp_path / "s", "boot-code-0123456789abc", HostOptions(("documents", docs), ("mail", mail), tmp_path / "pub.key"), HostEnv("darwin", sec, "owner", runtime=object())
    )  # fmt: skip
    keys = {config.task_key, config.designation_key, config.documents_key, config.mail_key}
    assert len(keys) == 4 and all(len(k) == 64 for k in keys) and len(config.model_record_key) == 32
    assert isinstance(config.anchor, KeychainAnchor) and config.bootstrap_code == "boot-code-0123456789abc"
    assert [e.model_id for e in config.manifest.entries()] == ["primary-1"] and config.documents == ("documents", docs) and config.mailbox[0] == "mail"
    assert isinstance(config.mailbox[1], EmlxMailbox) and isinstance(config.os_permissions, FolderPermissions)
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
