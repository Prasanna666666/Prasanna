"""A Core configuration for the launcher tests: deterministic fakes where the Mac pieces would be (anchor, OS permissions), no sources, a stub model. Used only with `--allow-custom-factory`."""

from __future__ import annotations

from pathlib import Path

from test_models import entry_dict, signed

from atlas_core.access import FakeOSPermissions
from atlas_core.app import CoreConfig
from atlas_core.designation import InMemoryAnchor


class StubRuntime:
    def __init__(self) -> None:
        self._loaded: set[str] = set()

    def load(self, verified):
        self._loaded.add(verified.entry.model_id)

    def unload(self, model_id):
        self._loaded.discard(model_id)

    def loaded(self):
        return frozenset(self._loaded)

    def complete(self, model_id, context, max_context, should_stop=lambda: False):
        raise RuntimeError("not used")


def build_config(data_dir: Path, socket_path: Path, bootstrap_code: str | None) -> CoreConfig:
    manifest = signed([entry_dict("primary-1", {"w.safetensors": b"w"}, runtime="stub")])
    return CoreConfig(
        data_dir=data_dir, socket_path=socket_path, task_key="t" * 40, designation_key="d" * 40, documents_key="o" * 40, mail_key="m" * 40, anchor=InMemoryAnchor(),
        os_permissions=FakeOSPermissions(), manifest=manifest, model_record_key=b"k" * 32, runtime=StubRuntime(), bootstrap_code=bootstrap_code,
    )  # fmt: skip
