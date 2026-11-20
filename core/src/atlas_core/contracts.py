"""Validation against the language-neutral contract (contracts/atlas-contracts.schema.json)."""

from __future__ import annotations

import json
import os
from functools import cache, lru_cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

ENV_DIR = "ATLAS_CONTRACTS_DIR"
DEFAULT_DIR = Path(__file__).resolve().parents[2] / "contracts"
SCHEMA_FILE = "atlas-contracts.schema.json"


class ContractError(ValueError):
    """The value does not match the contract. Carries the location only, never the offending value (it may be content of the owner)."""

    def __init__(self, where: str) -> None:
        super().__init__(f"does not match the contract at {where}")
        self.where = where


def contracts_dir() -> Path:
    return Path(os.environ.get(ENV_DIR) or DEFAULT_DIR)


@lru_cache(maxsize=1)
def _document() -> dict[str, Any]:
    return json.loads((contracts_dir() / SCHEMA_FILE).read_text(encoding="utf-8"))


def type_names() -> list[str]:
    return sorted(_document()["$defs"])


@cache
def _validator(name: str) -> Draft202012Validator:
    document = _document()
    schema = {"$schema": document["$schema"], "$ref": f"#/$defs/{name}", "$defs": document["$defs"]}
    return Draft202012Validator(schema, format_checker=FormatChecker())


def validate(name: str, value: Any) -> None:
    """Raise ContractError if the value is not a `name` of the contract."""
    error = next(iter(sorted(_validator(name).iter_errors(value), key=lambda e: list(map(str, e.absolute_path)))), None)
    if error is not None:
        raise ContractError("/".join(str(p) for p in error.absolute_path) or "(root)")
