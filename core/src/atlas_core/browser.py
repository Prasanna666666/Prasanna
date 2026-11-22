"""Browser and app workflows (Stage 6; PRD 4.5): the owner's steps are followed, page content is data.

A workflow is a list of steps the OWNER (or the owner's policy) wrote: open an allowed page, read it, fill a field, press a control. Every step that changes something outside the Mac goes through the Action
Gateway like any other action. What a page says is returned as UNTRUSTED text with its provenance; any instruction in it is flagged and never obeyed, and anything the page "asks for" can only be proposed with the
origin `untrusted_content`, which the gateway refuses outright. Destinations are public https hosts the owner has allowed; a redirect to anywhere else ends the workflow.

The real engine (a local Playwright adapter, or the narrowest macOS automation API) is a separate, isolated, platform-dependent seam that is not built here: `Browser` is that seam, and `FakeBrowser` serves
synthetic pages.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any, Protocol
from urllib.parse import urlsplit

from .actions import ActionGateway, Outcome
from .egress import INSTRUCTION_LIKE

MAX_STEPS = 40


class Browser(Protocol):
    def open(self, url: str) -> tuple[str, str]:
        """Returns the final URL (after redirects) and the page's visible text."""
        ...

    def fill(self, field_name: str, value: str) -> None: ...

    def press(self, control: str) -> None: ...


@dataclass(frozen=True)
class Page:
    url: str
    text: str
    trust: str = "untrusted"
    authority: str = "none"
    instruction_like: bool = False


@dataclass
class WorkflowResult:
    status: str  # completed | blocked | failed
    code: str = ""
    pages: list[Page] = field(default_factory=list)
    outcomes: list[Outcome] = field(default_factory=list)
    suggestions_refused: int = 0


def _host(url: str) -> str:
    return urlsplit(url).hostname or ""


def run_browser_workflow(
    browser: Browser,
    steps: Iterable[tuple[str, ...]],
    *,
    allowed_hosts: frozenset[str],
    gateway: ActionGateway,
    is_public: Callable[[str], bool] = lambda host: True,
    suggestions: Callable[[Page], list[tuple[str, dict[str, Any]]]] = lambda page: [],
) -> WorkflowResult:
    """Steps: ("open", url) | ("fill", name, value) | ("press", control) | ("act", action_name, payload_json_key) handled by the caller as gateway actions. `suggestions` is whatever turns a page into proposed actions
    (a model, a parser): every one of them is proposed as untrusted content and therefore refused."""
    result = WorkflowResult("completed")
    for count, step in enumerate(steps, start=1):
        if count > MAX_STEPS:
            return WorkflowResult("failed", "too_many_steps", result.pages, result.outcomes, result.suggestions_refused)
        kind = step[0]
        if kind == "open":
            url = step[1]
            parts = urlsplit(url)
            if parts.scheme != "https" or parts.hostname not in allowed_hosts or not is_public(parts.hostname or ""):
                return WorkflowResult("blocked", "destination_not_allowed", result.pages, result.outcomes, result.suggestions_refused)
            final, text = browser.open(url)
            if _host(final) not in allowed_hosts or urlsplit(final).scheme != "https":
                return WorkflowResult(
                    "blocked", "redirected_off_allow_list", result.pages, result.outcomes, result.suggestions_refused
                )  # the page it landed on is not read
            page = Page(final, re.sub(r"\s+", " ", text).strip()[:200_000], instruction_like=bool(INSTRUCTION_LIKE.search(text)))
            result.pages.append(page)
            for name, payload in suggestions(page):
                outcome = gateway.propose(name, payload, origin="untrusted_content", idempotency_key=f"page-{count}-{name}")
                result.suggestions_refused += outcome.status == "refused"
        elif kind == "fill":
            browser.fill(step[1], step[2])
        elif kind == "press":
            browser.press(step[1])
        else:
            return WorkflowResult("failed", "unknown_step", result.pages, result.outcomes, result.suggestions_refused)
    return result


class FakeBrowser:
    """SYNTHETIC pages. `redirects` maps a url to the url the 'browser' ends up on."""

    def __init__(self, pages: dict[str, str], redirects: dict[str, str] | None = None) -> None:
        self.pages, self.redirects = pages, redirects or {}
        self.filled: list[tuple[str, str]] = []
        self.pressed: list[str] = []
        self.opened: list[str] = []

    def open(self, url: str) -> tuple[str, str]:
        self.opened.append(url)
        final = self.redirects.get(url, url)
        return final, self.pages.get(final, "")

    def fill(self, field_name: str, value: str) -> None:
        self.filled.append((field_name, value))

    def press(self, control: str) -> None:
        self.pressed.append(control)
