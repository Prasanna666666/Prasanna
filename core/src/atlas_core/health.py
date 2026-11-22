"""Health checks, redacted diagnostics and a permission reset (Stage 7).

`health` answers "is the Core fit to serve?" with named checks and CODES. `diagnostics` is what the owner may attach to a bug report: it is assembled ONLY from allow-listed, structured, content-free
fields (versions, check codes, sizes, counts), never from logs, questions, passages, file or message names, keys or paths, and is then passed through `redact` as a second line of defence. A permission reset
withdraws every grant through the normal audited path (so every index and everything tasks derived from it is purged), and changes nothing else.
"""

from __future__ import annotations

import json
import platform
import re
import shutil
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from .storage import report as storage_report

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_NUMBER = re.compile(r"\d[\d \-]{5,}\d")
_TOKEN = re.compile(r"\b[A-Za-z0-9_-]{24,}\b")


@dataclass(frozen=True)
class Check:
    name: str
    status: str  # ok | degraded | failed
    code: str = ""


class _Designation(Protocol):
    def health(self) -> str: ...
    def designable(self) -> list[str]: ...
    def lifecycle(self, source_type: str) -> str: ...
    def withdraw(self, source_type: str, request_id: str) -> bool: ...


def redact(text: str, home: Path | None = None) -> str:
    """Second line of defence: the home folder becomes `~`, e-mail addresses, long digit runs and long tokens are replaced."""
    if home is not None:
        text = text.replace(str(home), "~")
    return _TOKEN.sub("<token>", _NUMBER.sub("<number>", _EMAIL.sub("<email>", text)))


def health(core: Any, usage: Callable[[Path], tuple[int, int, int]] = shutil.disk_usage) -> list[Check]:
    checks = [Check("designation_store", "ok" if core.designation.health() == "ok" else "failed", "" if core.designation.health() == "ok" else "corrupt")]
    for name, index in sorted(core.indexes.items()):
        cov = index.coverage()
        failed, pending = int(cov.get("failed", 0)), int(cov.get("pending", 0))
        status, code = ("ok", "") if not failed and not pending else ("degraded", "partial_coverage" if pending else "unreadable_items")
        checks.append(Check(f"index_{name}", status, code))
    pressure = storage_report(core.config.data_dir, usage=usage).pressure
    checks.append(Check("disk", "ok" if pressure == "ok" else "degraded", "" if pressure == "ok" else f"disk_{pressure}"))
    return checks


def diagnostics(core: Any, home: Path, versions: dict[str, str] | None = None, usage: Callable[[Path], tuple[int, int, int]] = shutil.disk_usage) -> str:
    """A JSON document of allow-listed fields only, redacted."""
    disk = storage_report(core.config.data_dir, usage=usage)
    body = {
        "versions": {**(versions or {}), "python": platform.python_version(), "platform": platform.system()},
        "checks": [{"name": c.name, "status": c.status, "code": c.code} for c in health(core, usage)],
        "storage": {"bytes_by_category": disk.bytes_by_category, "pressure": disk.pressure},
        "indexes": {n: {k: i.coverage().get(k) for k in ("total", "searched", "pending", "failed", "complete")} for n, i in sorted(core.indexes.items())},
    }
    return redact(json.dumps(body, sort_keys=True, indent=1), home)


def reset_permissions(designation: _Designation, request_ids: Callable[[str], str], types: Iterable[str] | None = None) -> list[str]:
    """Withdraw every enabled source (or the named ones) through the audited path. Returns the source types that were withdrawn."""
    withdrawn = []
    for source_type in sorted(types if types is not None else designation.designable()):
        if designation.lifecycle(source_type) == "enabled" and designation.withdraw(source_type, request_ids(source_type)):
            withdrawn.append(source_type)
    return withdrawn
