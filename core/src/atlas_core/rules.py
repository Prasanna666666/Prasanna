"""The policy and limits as data (policy-rules.json), not as lists in code."""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

RULES_FILE = Path(__file__).with_name("policy-rules.json")


@dataclass(frozen=True)
class Rules:
    raw: dict[str, Any]

    @property
    def version(self) -> str:
        return str(self.raw["policy_version"])

    def rank(self, sensitivity: str) -> int:
        return list(self.raw["sensitivity_order"]).index(sensitivity)

    def sensitivity_of(self, source_type: str) -> str | None:
        entry = self.raw["source_types"].get(source_type)
        return None if entry is None else str(entry["sensitivity"])

    def is_restricted(self, source_type: str) -> bool:
        return source_type in self.raw["restricted_domains"]

    def deferred_to(self, source_type: str) -> str | None:
        decision = self.raw["deferred"].get(source_type)
        return None if decision is None else str(decision)

    def device_may_ask(self, requested: Sequence[str]) -> bool:
        """A paired (non-owner) device may put a task over only the sources the policy names for devices; anything else, Finance, Health and Photos included, is refused whatever the device signs."""
        allowed = set(self.raw["device_task_sources"])
        return all(s in allowed for s in requested)

    def limit(self, name: str) -> int:
        return int(self.raw["limits"][name])

    @property
    def attachment_type(self) -> str:
        return str(self.raw["disclosures"]["attachment_type"])

    def discloses_attachments(self, requested: Sequence[str]) -> bool:
        """Attachment contents are not searched whenever any of these source types was asked for; the answer must say so."""
        return any(t in self.raw["disclosures"]["attachments_not_searched_when_requested"] for t in requested)

    @property
    def measured_languages(self) -> frozenset[str]:
        return frozenset(str(x).lower() for x in self.raw["language"]["measured"])

    @property
    def low_confidence_below(self) -> float:
        return float(self.raw["language"]["low_confidence_below"])


@lru_cache(maxsize=1)
def load_rules(path: Path = RULES_FILE) -> Rules:
    return Rules(json.loads(path.read_text(encoding="utf-8")))
