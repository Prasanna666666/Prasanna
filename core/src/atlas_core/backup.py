"""Backup, restore and key recovery of the Core's NON-derivable state (Stage 4; UC-L15, UC-040).

What is backed up: the task store (`tasks.db`), the client registry (`clients.json`) and, as history only, the designation store (`designation.db`). What is NOT backed up: the document and mail indexes
(derived: rebuilt from the owner's own sources by the progressive indexer), the model folder (re-imported from the signed manifest) and the originals (they are the owner's files and mail, never copied here).

Rules this module enforces:

* **Integrity before trust.** A backup carries a manifest with the size and SHA-256 of every file and the row count of every table of each database. `verify_backup` checks all of it; a restore verifies
  first and refuses on any problem. Given the recovery passphrase it also authenticates the manifest (HMAC) and opens every database with its recovered key.
* **Key recovery.** The store keys live in the Keychain on the Mac. The backup carries them in `keys.enc`, wrapped with AES-256-GCM under a key derived (scrypt) from an owner-held recovery passphrase, so a
  replacement Mac can recover them. Without the passphrase nothing in the bundle is readable; a wrong passphrase reveals nothing but the fact it is wrong.
* **Grants are never restored.** A restored copy of the designation store would be a rollback, which the store's external anchor exists to detect (a revoked permission must never come back). The backup's
  copy is restored as read-only history, NOT as the live store; the new Core starts with an empty, freshly anchored designation store, so every source is off until the owner turns it on again.
* **No silent deletion, no overwrite.** A backup is written to a temporary folder and renamed once complete. A restore goes only into a folder that does not exist or is empty, and removes only what it
  created if it fails. Nothing here deletes an original or touches the live data folder (the online SQLite backup API reads it).
* **Content-free errors.** Every failure is a short code; no path, key, passphrase or row is ever in a message or a log.

The platform seam is `provision_keys`: on the Mac it writes the recovered keys into the Keychain; in CI it is a fake. The module touches no Keychain itself.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import shutil
import tempfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
from kit.db import EncryptionError, connect

FORMAT = 1
MIN_PASSPHRASE = 12
SCRYPT_N, SCRYPT_R, SCRYPT_P = 2**15, 8, 1
SPACE_MARGIN = 1.5  # free space required, as a multiple of what is copied
MANIFEST, KEYS_FILE = "manifest.json", "keys.enc"
DB_FILES = ("tasks.db", "designation.db")  # each opens with the key of the same name in `db_keys`
PLAIN_FILES = ("clients.json",)
HISTORY_DIR, HISTORY_NAME = "history", "designation-history.db"
DERIVED = ("documents.db", "mail.db", "models")  # named in the manifest so a reader can see they are deliberately absent


class BackupError(Exception):
    """A backup or restore step was refused. Carries only a code."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class VerifyResult:
    ok: bool
    problems: tuple[str, ...]
    authenticated: bool  # True only if the passphrase was given and the manifest MAC and every database checked out


@dataclass
class RestoreReport:
    target: Path
    files: dict[str, int] = field(default_factory=dict)  # file name -> bytes
    rows: dict[str, dict[str, int]] = field(default_factory=dict)  # database -> table -> rows, as verified after the copy
    grants_restored: bool = False  # always False: see the module docstring


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def _unb64(text: str) -> bytes:
    return base64.b64decode(text.encode("ascii"), validate=True)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while block := f.read(1 << 20):
            h.update(block)
    return h.hexdigest()


def _derive(passphrase: str, salt: bytes) -> tuple[bytes, bytes]:
    """Two independent 32-byte keys from the recovery passphrase: one wraps the key bundle, one authenticates the manifest."""
    raw = Scrypt(salt=salt, length=64, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P).derive(passphrase.encode("utf-8"))
    return raw[:32], raw[32:]


def _canonical(manifest: Mapping[str, Any]) -> bytes:
    body = {k: v for k, v in manifest.items() if k != "mac"}
    return json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _tables(conn: Any) -> dict[str, int]:
    names = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
    return {n: int(conn.execute(f'SELECT count(*) FROM "{n}"').fetchone()[0]) for n in names}


def _snapshot(src: Path, dst: Path, key: str) -> dict[str, int]:
    """A consistent copy of one encrypted database, made with the online backup API so a running Core is not stopped. The copy is encrypted under the same key."""
    source = connect(src, key)
    try:
        target = connect(dst, key)
        try:
            source.backup(target)
            target.commit()
            return _tables(target)
        finally:
            target.close()
    finally:
        source.close()


def _inspect(path: Path, key: str) -> tuple[str, dict[str, int]]:
    """Integrity result and row counts of an encrypted database, read from a private temporary COPY: opening the file itself switches it to WAL mode, which would change its bytes and break its hash."""
    with tempfile.TemporaryDirectory(prefix="atlbk") as scratch:
        copy = Path(scratch) / "db"
        shutil.copyfile(path, copy)
        conn = connect(copy, key)
        try:
            return str(conn.execute("PRAGMA integrity_check").fetchone()[0]), _tables(conn)
        finally:
            conn.close()


def _free_bytes(folder: Path) -> int:
    return shutil.disk_usage(folder).free


def _copy_files(data_dir: Path, temp: Path, present: list[str], db_keys: Mapping[str, str]) -> dict[str, dict[str, Any]]:
    files: dict[str, dict[str, Any]] = {}
    for name in present:
        out = temp / name
        if name in DB_FILES:
            if name not in db_keys:
                raise BackupError("missing_db_key")
            rows: dict[str, int] | None = _snapshot(data_dir / name, out, db_keys[name])
        else:
            shutil.copyfile(data_dir / name, out)
            rows = None
        os.chmod(out, 0o600)
        files[name] = {"sha256": sha256_file(out), "size": out.stat().st_size, **({"rows": rows} if rows is not None else {})}
    return files


def _seal_keys(temp: Path, bundle: Mapping[str, str], passphrase: str) -> tuple[bytes, bytes, dict[str, Any]]:
    """Write `keys.enc` (the bundle wrapped under the passphrase) and return the salt, the manifest MAC key and the file's manifest entry."""
    salt, nonce = secrets.token_bytes(16), secrets.token_bytes(12)
    wrap_key, mac_key = _derive(passphrase, salt)
    sealed = AESGCM(wrap_key).encrypt(nonce, json.dumps(dict(bundle), sort_keys=True).encode("utf-8"), KEYS_FILE.encode())
    (temp / KEYS_FILE).write_bytes(nonce + sealed)
    os.chmod(temp / KEYS_FILE, 0o600)
    return salt, mac_key, {"sha256": sha256_file(temp / KEYS_FILE), "size": (temp / KEYS_FILE).stat().st_size}


def _write_manifest(temp: Path, files: dict[str, dict[str, Any]], salt: bytes, mac_key: bytes, created_at: str) -> None:
    manifest: dict[str, Any] = {
        "format": FORMAT,
        "created_at": created_at,
        "files": files,
        "derived_not_backed_up": list(DERIVED),
        "kdf": {"name": "scrypt", "n": SCRYPT_N, "r": SCRYPT_R, "p": SCRYPT_P, "salt": _b64(salt)},
        "grants_restored": False,
    }
    manifest["mac"] = hmac.new(mac_key, _canonical(manifest), hashlib.sha256).hexdigest()
    (temp / MANIFEST).write_text(json.dumps(manifest, sort_keys=True, indent=1), encoding="utf-8")
    os.chmod(temp / MANIFEST, 0o600)


def create_backup(
    data_dir: Path,
    destination: Path,
    *,
    db_keys: Mapping[str, str],
    keys: Mapping[str, str],
    passphrase: str,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> Path:
    """Write a verified backup folder under `destination` and return its path. `db_keys` maps each database file name to its key (used to snapshot it); `keys` is the whole bundle to protect
    (every store key the replacement Mac will need). Refuses a weak passphrase, a destination without room, or a name that already exists."""
    if len(passphrase) < MIN_PASSPHRASE:
        raise BackupError("weak_passphrase")
    present = [n for n in DB_FILES + PLAIN_FILES if (data_dir / n).exists()]
    if "tasks.db" not in present:
        raise BackupError("nothing_to_back_up")
    destination.mkdir(parents=True, exist_ok=True, mode=0o700)
    if _free_bytes(destination) < sum((data_dir / n).stat().st_size for n in present) * SPACE_MARGIN:
        raise BackupError("not_enough_space")
    final = destination / f"atlas-backup-{clock().strftime('%Y%m%dT%H%M%SZ')}"
    if final.exists():
        raise BackupError("backup_exists")
    temp = destination / f".incomplete-{secrets.token_hex(6)}"
    temp.mkdir(mode=0o700)
    try:
        files = _copy_files(data_dir, temp, present, db_keys)
        salt, mac_key, files[KEYS_FILE] = _seal_keys(
            temp, {**keys, **{f"db:{n}": k for n, k in db_keys.items()}}, passphrase
        )  # the database keys travel in the bundle under "db:<file>"
        _write_manifest(temp, files, salt, mac_key, clock().isoformat())
        if not verify_backup(temp, passphrase, db_keys=None).ok:  # a backup that does not verify is not a backup
            raise BackupError("verification_failed")
        os.rename(temp, final)
        return final
    except BaseException:
        shutil.rmtree(temp, ignore_errors=True)  # only the folder this call created
        raise


def _load_manifest(folder: Path) -> dict[str, Any] | None:
    try:
        data = json.loads((folder / MANIFEST).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return (
        data if isinstance(data, dict) and data.get("format") == FORMAT and isinstance(data.get("files"), dict) and isinstance(data.get("kdf"), dict) else None
    )


def recover_keys(folder: Path, passphrase: str) -> dict[str, str]:
    """The key bundle, recovered with the owner's passphrase. A wrong passphrase, a damaged bundle or a manifest that does not authenticate all raise the same code."""
    manifest = _load_manifest(folder)
    if manifest is None:
        raise BackupError("bad_manifest")
    try:
        wrap_key, mac_key = _derive(passphrase, _unb64(manifest["kdf"]["salt"]))
        blob = (folder / KEYS_FILE).read_bytes()
        plain = AESGCM(wrap_key).decrypt(blob[:12], blob[12:], KEYS_FILE.encode())
    except (OSError, ValueError, KeyError, InvalidTag):
        raise BackupError("bad_passphrase") from None
    if not hmac.compare_digest(hmac.new(mac_key, _canonical(manifest), hashlib.sha256).hexdigest(), str(manifest.get("mac", ""))):
        raise BackupError("manifest_not_authentic")
    try:
        bundle = json.loads(plain)
    except ValueError:
        raise BackupError("bad_passphrase") from None
    return {str(k): str(v) for k, v in bundle.items()}


def verify_backup(folder: Path, passphrase: str | None = None, *, db_keys: Mapping[str, str] | None = None) -> VerifyResult:
    """Check a backup. Without a passphrase: every file present, with the recorded size and SHA-256 (corruption). With the passphrase: also the manifest MAC (tampering), and every database opened
    with its recovered key, integrity-checked and compared with the recorded row counts. `db_keys` lets a caller that already holds the keys name them for the database check."""
    manifest = _load_manifest(folder)
    if manifest is None:
        return VerifyResult(False, ("bad_manifest",), False)
    problems: list[str] = []
    for name, entry in manifest["files"].items():
        path = folder / name
        if not path.is_file():
            problems.append("missing_file")
            continue
        if path.stat().st_size != entry.get("size"):
            problems.append("size_mismatch")
        elif sha256_file(path) != entry.get("sha256"):
            problems.append("hash_mismatch")
    authenticated = False
    if passphrase is not None and not problems:
        try:
            bundle = recover_keys(folder, passphrase)
        except BackupError as error:
            return VerifyResult(False, (error.code,), False)
        keys = dict(db_keys or {}) or {n: bundle.get(f"db:{n}", "") for n in DB_FILES}
        for name in DB_FILES:
            entry = manifest["files"].get(name)
            if entry is None:
                continue
            try:
                verdict, rows = _inspect(folder / name, keys[name])
            except (EncryptionError, KeyError):
                problems.append("db_unreadable")
                continue
            if verdict != "ok":
                problems.append("integrity_failed")
            elif rows != entry.get("rows"):
                problems.append("count_mismatch")
        authenticated = not problems
    return VerifyResult(not problems, tuple(dict.fromkeys(problems)), authenticated)


def _copy_state(folder: Path, target: Path, manifest: dict[str, Any], made: list[Path], report: RestoreReport) -> None:
    for name in ("tasks.db", "clients.json"):
        if name in manifest["files"]:
            out = target / name
            shutil.copyfile(folder / name, out)
            made.append(out)
            os.chmod(out, 0o600)
            report.files[name] = out.stat().st_size
    if "designation.db" in manifest["files"]:
        history = target / HISTORY_DIR
        history.mkdir(mode=0o700, exist_ok=True)
        made.append(history)
        out = history / HISTORY_NAME
        shutil.copyfile(folder / "designation.db", out)
        os.chmod(out, 0o400)  # read-only: it is history, never the live store
        report.files[HISTORY_NAME] = out.stat().st_size


def _check_copies(target: Path, manifest: dict[str, Any], bundle: Mapping[str, str], report: RestoreReport) -> None:
    for name in DB_FILES:
        entry = manifest["files"].get(name)
        if entry is None:
            continue
        copy = target / ("tasks.db" if name == "tasks.db" else f"{HISTORY_DIR}/{HISTORY_NAME}")
        verdict, report.rows[name] = _inspect(copy, bundle[f"db:{name}"])
        if verdict != "ok" or report.rows[name] != entry["rows"]:
            raise BackupError("count_mismatch")


def _remove_made(made: list[Path], target: Path, created_target: bool) -> None:
    for path in reversed(made):
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
        else:
            path.chmod(0o600)
            path.unlink(missing_ok=True)
    for leftover in (target / "tasks.db-wal", target / "tasks.db-shm"):
        leftover.unlink(missing_ok=True)
    if created_target:
        shutil.rmtree(target, ignore_errors=True)


def restore_backup(
    folder: Path,
    passphrase: str,
    target: Path,
    *,
    provision_keys: Callable[[Mapping[str, str]], None],
) -> RestoreReport:
    """Restore into `target` (which must not exist or be empty). Verifies everything first, then copies, then re-verifies the copy and hands the recovered keys to `provision_keys` (the Keychain on a
    Mac). On any failure removes only what this call created and re-raises. The designation store is restored as history only; the new Core starts with every source off."""
    result = verify_backup(folder, passphrase)
    if not result.ok:
        raise BackupError(result.problems[0])
    if target.exists() and (not target.is_dir() or any(target.iterdir())):
        raise BackupError("target_not_empty")
    manifest = _load_manifest(folder)
    assert manifest is not None  # verified above
    bundle = recover_keys(folder, passphrase)
    created_target = not target.exists()
    target.mkdir(parents=True, exist_ok=True, mode=0o700)
    made: list[Path] = []
    report = RestoreReport(target)
    try:
        _copy_state(folder, target, manifest, made, report)
        _check_copies(target, manifest, bundle, report)
        provision_keys(bundle)
        return report
    except BaseException:
        _remove_made(made, target, created_target)
        raise


DRILL_FILE = "restore-drill.json"
DRILL_VALID_DAYS = 90


@dataclass(frozen=True)
class DrillResult:
    ok: bool
    code: str = ""


def run_restore_drill(folder: Path, passphrase: str, scratch: Path, data_dir: Path, clock: Callable[[], datetime] = lambda: datetime.now(UTC)) -> DrillResult:
    """Prove a backup can really be restored: restore it into `scratch` (a place that must not exist or be empty), check the copy, then remove what the drill created. On success the live data folder gets a
    small marker (the manifest's hash and the time) that the Core reads to allow sensitive domains. Nothing in the live data folder other than that marker is touched."""
    try:
        report = restore_backup(folder, passphrase, scratch, provision_keys=lambda keys: None)
    except BackupError as error:
        return DrillResult(False, error.code)
    shutil.rmtree(report.target, ignore_errors=True)
    manifest_hash = hashlib.sha256((folder / MANIFEST).read_bytes()).hexdigest()
    marker = data_dir / DRILL_FILE
    marker.write_text(json.dumps({"manifest_sha256": manifest_hash, "at": clock().isoformat()}), encoding="utf-8")
    os.chmod(marker, 0o600)
    return DrillResult(True)


def drill_passed(data_dir: Path, clock: Callable[[], datetime] = lambda: datetime.now(UTC)) -> bool:
    """True if a restore drill succeeded within the last 90 days. A missing, unreadable or old marker is False."""
    try:
        marker = json.loads((data_dir / DRILL_FILE).read_text(encoding="utf-8"))
        at = datetime.fromisoformat(marker["at"])
    except (OSError, ValueError, KeyError, TypeError):
        return False
    return (clock() - at).days <= DRILL_VALID_DAYS
