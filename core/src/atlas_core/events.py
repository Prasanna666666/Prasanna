"""Privacy-safe events: redaction by construction.

An event is built only from the allow-listed fields of SafeEvent in the contract. A field that is not in the list, or a value outside its
enumeration or pattern, is refused (UnsafeEvent), so free text of the owner (a question, a file name, a subject, an address, a passage, a secret)
cannot be logged by mistake: there is no field for it.
"""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import Callable
from typing import Any

from .contracts import ContractError, validate

LOGGER = logging.getLogger("atlas_core.events")


class UnsafeEvent(ValueError):
    """The event does not fit the allow-list. The message names the field's place, never its value."""


def new_id() -> str:
    return uuid.uuid4().hex


def _to_logger(line: str) -> None:
    LOGGER.info(line)


class SafeLog:
    def __init__(self, sink: Callable[[str], None] = _to_logger) -> None:
        self._sink = sink

    def emit(self, event: str, component: str, correlation_id: str, **fields: Any) -> None:
        record = {"event": event, "component": component, "correlation_id": correlation_id, **fields}
        try:
            validate("SafeEvent", record)
        except ContractError as e:
            raise UnsafeEvent(f"event does not fit the allow-list at {e.where}") from None
        self._sink(json.dumps(record, sort_keys=True, separators=(",", ":")))
