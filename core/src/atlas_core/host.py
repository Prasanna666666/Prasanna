"""The machine-specific part of a real Core: where its keys, its rollback anchor, its OS-permission provider, its mailbox adapter and its model engine come from.

On a Mac these are the Keychain (`macos.KeychainItems`, `macos.KeychainAnchor`), a folder-permission probe (`macos.FolderPermissions`), the Apple Mail reader (`macos.EmlxMailbox`) and
the MLX engine in the isolated worker. The Keychain, the sandboxed MLX worker and the whole production Core as a child process are CI-verified on a macOS runner; the folder-permission probe against real TCC and the Mail reader against a real Mail store are not. On any other platform the production factory refuses to build a Core;
it never falls back to a development stand-in. Tests and development supply their own factory with the explicit `--allow-custom-factory` flag of `serve`.

Source type names (which folder is "documents", which is "mail") come from the caller, never from this file: the policy rules are the only place they are defined.
"""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from .access import GRANTED, PermissionEvidence
from .app import CoreConfig
from .browser_engine import WorkerBrowser
from .finance_calc import MONEY_DOMAIN
from .health_calc import HEALTH_DOMAIN
from .intelligence import ModelRuntime
from .isolated import IsolatedEngine
from .macos import EmlxMailbox, FolderPermissions, KeychainAnchor, KeychainError, KeychainItems, KeychainSecrets, Runner
from .macos_sources import DOMAINS as NATIVE_DOMAINS
from .macos_sources import MacPermissions, NativeRecords, ObjcPlatform, Platform
from .mlx_runtime import MlxRuntime
from .models import Manifest, ModelRejected
from .recordstore import RecordStore, StoredRecords
from .updater import Installer, UpdateOperations

MANIFEST_FILE, SIGNATURE_FILE = "manifest.json", "manifest.sig"


class HostUnavailable(RuntimeError):
    """This machine cannot provide the real platform parts."""


class KeychainLocked(HostUnavailable):
    """The Keychain would not give the store keys. On a Mac that has just restarted this is the normal state until the owner signs in (FileVault stays on; there is no auto-login): the Core does not start,
    says so with its own exit code, and the app shows "Mac needs owner sign-in"."""


@dataclass
class HostOptions:
    documents: tuple[str, Path] | None = None  # (source type name from the policy rules, the folder designated for it)
    mail: tuple[str, Path] | None = None  # (source type name, the Apple Mail folder)
    manifest_pubkey: Path | None = None  # the installed public key (32 raw bytes) that signed the model manifest
    update_root: Path | None = None  # where the app's own versions live (`versions/`, `current`, `previous`); without it the Core offers no update screen
    update_pubkey: Path | None = None  # the installed public key (32 raw bytes) that signs releases


@dataclass
class HostEnv:
    platform: str = sys.platform
    runner: Runner = field(default=subprocess.run)
    account: str | None = None
    runtime: ModelRuntime | None = None  # None: the MLX engine in the isolated worker
    native: Platform | None = None  # None: the real platform when its frameworks can be loaded, else no native sources


class OwnStorePermissions:
    """Atlas's own stores (the Finance records) have no operating-system permission to ask for: the owner's grant in Atlas, judged by the policy (a grant for exactly that domain with a `restricted`
    ceiling, and a passed restore drill), is the whole decision. Every other source type is delegated to the platform provider (folders, TCC)."""

    def __init__(self, own: frozenset[str], inner: FolderPermissions) -> None:
        self._own, self._inner = own, inner

    def current(self, source_type: str) -> PermissionEvidence:
        if source_type in self._own:
            return PermissionEvidence(source_type, GRANTED, datetime.now(UTC))
        return self._inner.current(source_type)


def load_manifest(models_dir: Path, pubkey: Path | None) -> Manifest:
    """The signed manifest installed next to the models, or an EMPTY manifest (no model: answers say the local model is unavailable while typed functions continue). A manifest that
    is missing, unsigned or fails its signature gives no models, never a crash and never an unsigned model."""
    try:
        key = Ed25519PublicKey.from_public_bytes((pubkey or Path("/nonexistent")).read_bytes())
        return Manifest.from_signed((models_dir / MANIFEST_FILE).read_bytes(), (models_dir / SIGNATURE_FILE).read_bytes(), key)
    except (OSError, ValueError, ModelRejected):
        return Manifest([])


def _restricted_stores(data_dir: Path, keys: dict[str, str]) -> tuple[dict[str, Any], tuple[Callable[[], None], ...]]:
    """The owner's Finance and Health records, each in its own encrypted store with its own key (imported with the maintenance commands), each indexed under its own key."""
    records: dict[str, Any] = {}
    closers: list[Callable[[], None]] = []
    for domain in (MONEY_DOMAIN, HEALTH_DOMAIN):  # the store, key and index key are named after the domain
        store = RecordStore(data_dir / f"{domain}-records.db", keys[f"{domain}-records"], frozenset({domain}))
        records[domain] = (StoredRecords(store, domain), keys[f"{domain}-index"])
        closers.append(store.close)
    return records, tuple(closers)


def _web_engine(hosts: frozenset[str]) -> WorkerBrowser:
    """An isolated browser for one allowed host: its own process, https only, no redirect off the host. If no browser is installed the worker stops and the read says so plainly."""
    return WorkerBrowser(hosts, ["https"])


def _updates(options: HostOptions) -> UpdateOperations | None:
    """Updates are offered only when the host was told both where the app's versions live and which key signs releases."""
    if options.update_root is None or options.update_pubkey is None:
        return None
    key = Ed25519PublicKey.from_public_bytes(options.update_pubkey.read_bytes())
    return UpdateOperations(Installer(options.update_root), key)


KEY_NAMES = (
    "task-store",
    "designation-store",
    "documents-index",
    "mail-index",
    "edits-store",
    "finance-records",
    "finance-index",
    "health-records",
    "health-index",
    *(f"{domain}-index" for domain in NATIVE_DOMAINS),
)


def _native(env: HostEnv, keys: dict[str, str], folders: Any, own: frozenset[str]) -> tuple[Any, dict[str, Any], Callable[[str], None] | None]:
    """The owner's Calendar, Contacts, Notes and Photos, when the platform's frameworks can be loaded: their permission provider, their sources (each with its own index key) and the request made when the owner turns one on."""
    inner = OwnStorePermissions(own, FolderPermissions(folders))
    platform = env.native
    if platform is None:
        try:
            platform = ObjcPlatform()
        except ImportError:
            return inner, {}, None  # no frameworks (an unsupported system): these sources are simply not offered
    sources = {domain: (NativeRecords(platform, domain), keys[f"{domain}-index"]) for domain in NATIVE_DOMAINS}
    return MacPermissions(platform, inner), sources, platform.request


def build_config(data_dir: Path, socket_path: Path, bootstrap_code: str | None, options: HostOptions | None = None, env: HostEnv | None = None) -> CoreConfig:
    options, env = options or HostOptions(), env or HostEnv()
    if env.platform != "darwin":
        raise HostUnavailable("the real platform providers exist only for macOS")
    items = KeychainItems(env.account, env.runner)
    try:
        keys = {name: items.secret(name) for name in KEY_NAMES}
        record_key = bytes.fromhex(items.secret("model-record"))
    except KeychainError:
        raise KeychainLocked("the Keychain could not provide the store keys") from None
    folders = dict(entry for entry in (options.documents, options.mail) if entry is not None)
    data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    records, closers = _restricted_stores(data_dir, keys)
    permissions, native_sources, requester = _native(env, keys, folders, frozenset({MONEY_DOMAIN, HEALTH_DOMAIN}))
    records.update(native_sources)
    return CoreConfig(
        data_dir=data_dir,
        socket_path=socket_path,
        task_key=keys["task-store"],
        designation_key=keys["designation-store"],
        documents_key=keys["documents-index"],
        mail_key=keys["mail-index"],
        anchor=KeychainAnchor(items),
        os_permissions=permissions,
        os_requester=requester,
        secrets=KeychainSecrets(items),
        records=records,
        closers=closers,
        manifest=load_manifest(data_dir / "models", options.manifest_pubkey),
        model_record_key=record_key,
        runtime=env.runtime or MlxRuntime(IsolatedEngine("mlx")),
        documents=options.documents,
        mailbox=None if options.mail is None else (options.mail[0], EmlxMailbox(options.mail[1])),
        edits_key=keys[
            "edits-store"
        ],  # the owner's own edits store: Calendar, Contacts and Notes actions and device sync. No sender and no eraser are provided, so sending and permanent erasure do not exist here
        require_restore_drill=True,  # Finance and Health wait for a passed restore drill (G-O05)
        bootstrap_code=bootstrap_code,
        updates=_updates(options),
        web_engine=_web_engine,
    )
