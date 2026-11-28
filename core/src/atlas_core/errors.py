"""The error taxonomy: a fixed code, an HTTP status and a message in plain words. Nothing from a source, a question or an exception ever reaches a message."""

from __future__ import annotations

from typing import Any

# code -> (http status, message for the owner, retryable)
TABLE: dict[str, tuple[int, str, bool]] = {
    "invalid_request": (400, "The request was not understood.", False),
    "unsupported_version": (426, "This app and Atlas speak different versions. Update the app or Atlas.", False),
    "unauthenticated": (401, "This device is not recognised by Atlas.", False),
    "forbidden": (403, "This device is not allowed to do that.", False),
    "not_found": (404, "That does not exist.", False),
    "conflict": (409, "That cannot be done in the current state.", False),
    "source_denied": (403, "Atlas is not allowed to search that kind of source.", False),
    "task_cancelled": (200, "The task was cancelled.", False),
    "task_expired": (200, "The task ran out of time.", True),
    "task_failed": (200, "The task could not be finished.", True),
    "needs_attention": (200, "The task was interrupted and needs a new request.", True),
    "model_unavailable": (503, "The local model is not available right now.", True),
    "citation_failed": (200, "The answer could not be checked against your sources.", False),
    "timeout": (504, "That took too long.", True),
    "internal_error": (500, "Something went wrong inside Atlas.", True),
}


class CoreError(Exception):
    """An error with a code from the taxonomy. The text of the exception is the code only."""

    def __init__(self, code: str, task_id: str | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.task_id = task_id


def status_of(code: str) -> int:
    return TABLE[code][0]


def user_error(code: str, task_id: str | None = None) -> dict[str, Any]:
    _, message, retryable = TABLE[code]
    out: dict[str, Any] = {"code": code, "message": message, "retryable": retryable}
    if task_id:
        out["task_id"] = task_id
    return out


class UpdateError(Exception):
    """An update step was refused. Carries a code and nothing else."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code
