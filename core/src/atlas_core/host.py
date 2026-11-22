"""The machine-specific part of a real Core: where its keys, its rollback anchor, its OS-permission provider, its mailbox adapter and its model engine come from.

On a Mac these are the Keychain, the platform secure-storage anchor, the TCC permission provider, the Apple Mail adapter and the MLX engine. NONE of them is built, so the production
factory refuses to build a Core and says exactly what is missing (it never falls back to a development stand-in). Tests and development supply their own factory with the explicit
`--allow-custom-factory` flag of `serve`.
"""

from __future__ import annotations

from pathlib import Path

from .app import CoreConfig

MISSING = (
    "Keychain key provider for the store keys",
    "platform secure-storage rollback anchor",
    "TCC OS-permission provider",
    "Apple Mail adapter",
    "model manifest installation and the MLX engine",
)


class HostUnavailable(RuntimeError):
    """This machine has no real platform providers (they are not built yet)."""


def build_config(data_dir: Path, socket_path: Path, bootstrap_code: str | None) -> CoreConfig:
    raise HostUnavailable("not built: " + "; ".join(MISSING))
