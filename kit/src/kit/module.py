"""The extension point. A feature (money, health, home...) is a Module: its schema plus its tools.

Tools are the single source of truth: the UI, the CLI and the AI assistant all call the same functions.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

ToolFn = Callable[[sqlite3.Connection, dict[str, Any]], Any]


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    properties: dict[str, dict[str, Any]]
    fn: ToolFn
    required: tuple[str, ...] = ()

    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {"type": "object", "properties": self.properties, "required": list(self.required)},
            },
        }


@dataclass(frozen=True)
class Module:
    name: str
    migrations: tuple[str, ...] = ()  # append-only; index+1 is the schema version
    tools: tuple[Tool, ...] = field(default_factory=tuple)


def S(description: str, **extra: Any) -> dict[str, Any]:
    return {"type": "string", "description": description, **extra}


def N(description: str) -> dict[str, Any]:
    return {"type": "number", "description": description}


def INT(description: str) -> dict[str, Any]:
    return {"type": "integer", "description": description}
