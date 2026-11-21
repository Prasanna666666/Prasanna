"""Validation against the language-neutral contracts: API 1.0 (contracts/atlas-contracts.schema.json, frozen) and API 1.1 (the 1.0 document with the definitions of
contracts/atlas-contracts.1.1.delta.schema.json applied by `build_1_1`). `validate(name, value)` means 1.0; 1.1 is only ever used when asked for by name."""

from __future__ import annotations

import copy
import json
import os
from collections.abc import Iterable
from functools import cache, lru_cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError

ENV_DIR = "ATLAS_CONTRACTS_DIR"
DEFAULT_DIR = Path(__file__).resolve().parents[2] / "contracts"
SCHEMA_FILE = "atlas-contracts.schema.json"
DELTA_FILE = "atlas-contracts.1.1.delta.schema.json"
VERSIONS = ("1.0", "1.1")  # the contracts that exist; the versions the Core serves are `SUPPORTED_VERSIONS` in the package, and 1.1 is not among them yet


class ContractError(ValueError):
    """The value does not match the contract. Carries the location only, never the offending value (it may be content of the owner)."""

    def __init__(self, where: str) -> None:
        super().__init__(f"does not match the contract at {where}")
        self.where = where


def contracts_dir() -> Path:
    return Path(os.environ.get(ENV_DIR) or DEFAULT_DIR)


class ContractBuildError(ValueError):
    """The 1.1 delta does not apply cleanly to the 1.0 document."""


class UnsupportedVersion(ValueError):
    """The requested API version is not one this function accepts."""


def _refs(node: Any) -> Iterable[str]:
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "$ref" and isinstance(value, str):
                yield value
            else:
                yield from _refs(value)
    elif isinstance(node, list):
        for item in node:
            yield from _refs(item)


def _names(delta: dict[str, Any], key: str) -> list[str]:
    names = delta.get(key)
    if not isinstance(names, list) or not all(isinstance(n, str) for n in names):
        raise ContractBuildError(f"{key} must be a list of definition names")
    if len(set(names)) != len(names):
        raise ContractBuildError(f"{key} contains a duplicate name")
    return names


def build_1_1(base: dict[str, Any], delta: dict[str, Any]) -> dict[str, Any]:
    """The 1.1 document: a deep copy of the 1.0 document with ONLY the definitions the delta names replaced or added. Pure and deterministic; the base is never changed.

    The root metadata of the base is kept. The delta lists `x-overrides` (1.0 names to replace) and `x-additions` (new names) and holds their definitions in `$defs`.
    Refused: a duplicate name, an override that is not a 1.0 definition, an addition that already is one, a name in both lists, a definition in neither list or a listed
    name without a definition, a reference that does not resolve, or a definition that is not a valid Draft 2020-12 schema."""
    overrides, additions = _names(delta, "x-overrides"), _names(delta, "x-additions")
    defs = delta.get("$defs")
    if not isinstance(defs, dict):
        raise ContractBuildError("the delta has no $defs")
    old = base["$defs"]
    if set(overrides) & set(additions):
        raise ContractBuildError("a name is both an override and an addition")
    if [n for n in overrides if n not in old]:
        raise ContractBuildError("an override names a definition that 1.0 does not have")
    if [n for n in additions if n in old]:
        raise ContractBuildError("an addition names a definition that 1.0 already has")
    if set(defs) != set(overrides) | set(additions):
        raise ContractBuildError("the delta's $defs and its two name lists differ")
    merged = copy.deepcopy(base)
    merged["$defs"] = {name: copy.deepcopy(defs[name]) if name in defs else merged["$defs"][name] for name in sorted(set(old) | set(additions))}
    for ref in _refs(merged):
        if not ref.startswith("#/$defs/") or ref.removeprefix("#/$defs/") not in merged["$defs"]:
            raise ContractBuildError("a reference does not resolve")
    for definition in merged["$defs"].values():
        try:
            Draft202012Validator.check_schema(definition)
        except SchemaError:
            raise ContractBuildError("a definition is not a valid schema") from None
    return merged


def negotiate(requested: object, advertised: Iterable[str]) -> str:
    """Which contract version applies to a request. No header means 1.0; 1.0 is always available; 1.1 only when `advertised`. Anything else (another version, an empty
    or repeated or non-text value) is refused, never guessed."""
    if requested is None:
        return "1.0"
    if requested == "1.0" or (requested == "1.1" and "1.1" in set(advertised)):
        return str(requested)
    raise UnsupportedVersion("unsupported API version")


@lru_cache(maxsize=2)
def _document(version: str = "1.0") -> dict[str, Any]:
    base = json.loads((contracts_dir() / SCHEMA_FILE).read_text(encoding="utf-8"))
    if version == "1.0":
        return base
    if version == "1.1":
        return build_1_1(base, json.loads((contracts_dir() / DELTA_FILE).read_text(encoding="utf-8")))
    raise UnsupportedVersion("no such contract version")


def type_names(version: str = "1.0") -> list[str]:
    return sorted(_document(version)["$defs"])


@cache
def _validator(name: str, version: str = "1.0") -> Draft202012Validator:
    document = _document(version)
    schema = {"$schema": document["$schema"], "$ref": f"#/$defs/{name}", "$defs": document["$defs"]}
    return Draft202012Validator(schema, format_checker=FormatChecker())


def validate(name: str, value: Any, version: str = "1.0") -> None:
    """Raise ContractError if the value is not a `name` of the contract of `version` (1.0 unless asked otherwise)."""
    error = next(iter(sorted(_validator(name, version).iter_errors(value), key=lambda e: list(map(str, e.absolute_path)))), None)
    if error is not None:
        raise ContractError("/".join(str(p) for p in error.absolute_path) or "(root)")
