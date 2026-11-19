"""Shared helpers for agent nodes: bounded retry + structured error capture."""
from __future__ import annotations

import time
from functools import wraps
from typing import Any, Callable

from ..core.logging import get_logger

log = get_logger("agent")


def with_retries(retries: int = 2, backoff: float = 0.2):
    """Wrap a node fn(state, db)->dict so transient errors are retried.

    A node that exhausts retries returns ``{"status": "error", "error": ...}``
    rather than raising, so the graph keeps flowing.
    """
    def deco(fn: Callable[..., dict]):
        @wraps(fn)
        def wrapper(state: dict, db) -> dict:
            last_err = None
            for attempt in range(retries + 1):
                try:
                    return fn(state, db)
                except Exception as e:  # noqa: BLE001
                    last_err = e
                    log.warning("agent.node_error", node=fn.__name__,
                                attempt=attempt, error=str(e))
                    if attempt < retries:
                        time.sleep(backoff * (attempt + 1))
            errors = list(state.get("errors", []))
            errors.append(f"{fn.__name__}: {last_err}")
            return {"errors": errors, "error": str(last_err), "status": "error"}
        return wrapper
    return deco
