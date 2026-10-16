"""Slowing down password guessing on client pages (step 2.4).

Five wrong passwords from one device (its address) for one project, then that
device waits 15 minutes. Kept in this server's memory: Cloud Run runs at most a
couple of instances, so a guesser gets at most a few more tries; a shared link's
password guarded this way is proportional to the risk (AGENTS.md).
"""

from __future__ import annotations

import time
from collections import defaultdict

from fastapi import Request

LIMIT = 5
WINDOW_SECONDS = 15 * 60

# (project id, device) -> times of recent wrong passwords
_failures: dict[tuple[str, str], list[float]] = defaultdict(list)


def device(request: Request) -> str:
    """The visitor's address. Behind Cloud Run's front end, the first address in
    X-Forwarded-For is the visitor's; locally, the socket's."""
    if request.app.state.settings.deployed:
        forwarded = request.headers.get("x-forwarded-for", "")
        if first := forwarded.split(",")[0].strip():
            return first
    return request.client.host if request.client else "unknown"


def _recent(key: tuple[str, str], now: float) -> list[float]:
    times = [t for t in _failures.get(key, []) if now - t < WINDOW_SECONDS]
    if times:
        _failures[key] = times
    else:
        _failures.pop(key, None)
    return times


def blocked(project_id: str, who: str, now: float | None = None) -> bool:
    return len(_recent((project_id, who), now or time.monotonic())) >= LIMIT


def failed(project_id: str, who: str, now: float | None = None) -> None:
    now = now or time.monotonic()
    _recent((project_id, who), now)
    _failures[(project_id, who)].append(now)


def succeeded(project_id: str, who: str) -> None:
    _failures.pop((project_id, who), None)


def reset() -> None:
    """For tests."""
    _failures.clear()
