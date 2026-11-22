"""The machine-specific part of a real Core: where its keys, its rollback anchor, its OS-permission provider, its mailbox adapter and its model engine come from.

On a Mac these are the Keychain (`macos.KeychainItems`, `macos.KeychainAnchor`), a folder-permission probe (`macos.FolderPermissions`), the Apple Mail reader (`macos.EmlxMailbox`) and
the MLX engine in the isolated worker. The Keychain, the sandboxed MLX worker and the whole production Core as a child process are CI-verified on a macOS runner; the folder-permission probe against real TCC and the Mail reader against a real Mail store are not. On any other platform the production factory refuses to build a Core;
it never falls back to a development stand-in. Tests and development supply their own factory with the explicit `--allow-custom-factory` flag of `serve`.

Source type names (which folder is "documents", which is "mail") come from the caller, never from this file: the policy rules are the only place they are defined.
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from .app import CoreConfig
from .intelligence import ModelRuntime
from .isolated import IsolatedEngine
from .macos import EmlxMailbox, FolderPermissions, KeychainAnchor, KeychainError, KeychainItems, Runner
from .mlx_runtime import MlxRuntime
from .models import Manifest, ModelRejected

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


@dataclass
class HostEnv:
    platform: str = sys.platform
    runner: Runner = field(default=subprocess.run)
    account: str | None = None
    runtime: ModelRuntime | None = None  # None: the MLX engine in the isolated worker


def load_manifest(models_dir: Path, pubkey: Path | None) -> Manifest:
    """The signed manifest installed next to the models, or an EMPTY manifest (no model: answers say the local model is unavailable while typed functions continue). A manifest that
    is missing, unsigned or fails its signature gives no models, never a crash and never an unsigned model."""
    try:
        key = Ed25519PublicKey.from_public_bytes((pubkey or Path("/nonexistent")).read_bytes())
        return Manifest.from_signed((models_dir / MANIFEST_FILE).read_bytes(), (models_dir / SIGNATURE_FILE).read_bytes(), key)
    except (OSError, ValueError, ModelRejected):
        return Manifest([])


def build_config(data_dir: Path, socket_path: Path, bootstrap_code: str | None, options: HostOptions | None = None, env: HostEnv | None = None) -> CoreConfig:
    options, env = options or HostOptions(), env or HostEnv()
    if env.platform != "darwin":
        raise HostUnavailable("the real platform providers exist only for macOS")
    items = KeychainItems(env.account, env.runner)
    try:
        keys = {name: items.secret(name) for name in ("task-store", "designation-store", "documents-index", "mail-index", "edits-store")}
        record_key = bytes.fromhex(items.secret("model-record"))
    except KeychainError:
        raise KeychainLocked("the Keychain could not provide the store keys") from None
    folders = dict(entry for entry in (options.documents, options.mail) if entry is not None)
    return CoreConfig(
        data_dir=data_dir,
        socket_path=socket_path,
        task_key=keys["task-store"],
        designation_key=keys["designation-store"],
        documents_key=keys["documents-index"],
        mail_key=keys["mail-index"],
        anchor=KeychainAnchor(items),
        os_permissions=FolderPermissions(folders),
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
    )
