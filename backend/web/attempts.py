"""Slowing down password guessing on client pages (step 2.4).

Five wrong passwords from one device (its address) for one project within 15
minutes, then that device waits 15 minutes from the fifth. Kept in this
server's memory: Cloud Run runs at most a couple of instances, so a guesser gets
at most a few more tries; a shared link's password guarded this way is
proportional to the risk (AGENTS.md).
"""

from __future__ import annotations

import time
from collections import defaultdict

from fastapi import Request

LIMIT = 5
WINDOW_SECONDS = 15 * 60

# (project id, device) -> times of recent wrong passwords
_failures: dict[tuple[str, str], list[float]] = defaultdict(list)
# (project id, device) -> when its wait ends: 15 minutes after the fifth wrong try
_blocked_until: dict[tuple[str, str], float] = {}


def device(request: Request) -> str:
    """The visitor's address. Google's front end appends the address it saw to
    X-Forwarded-For, after anything the visitor sent (which can be faked), so
    the last entry is the trustworthy one with Cloud Run alone. With an external
    load balancer in front (A21 option A), the second to last is: revisit then.
    Locally, the socket's."""
    if request.app.state.settings.deployed:
        entries = [e.strip() for e in request.headers.get("x-forwarded-for", "").split(",")]
        if entries and entries[-1]:
            return entries[-1]
    return request.client.host if request.client else "unknown"


def _recent(key: tuple[str, str], now: float) -> list[float]:
    times = [t for t in _failures.get(key, []) if now - t < WINDOW_SECONDS]
    if times:
        _failures[key] = times
    else:
        _failures.pop(key, None)
    return times


def blocked(project_id: str, who: str, now: float | None = None) -> bool:
    now = time.monotonic() if now is None else now
    until = _blocked_until.get((project_id, who))
    if until is None:
        return False
    if now < until:
        return True
    _blocked_until.pop((project_id, who), None)
    return False


def failed(project_id: str, who: str, now: float | None = None) -> None:
    now = time.monotonic() if now is None else now
    key = (project_id, who)
    _recent(key, now)
    _failures[key].append(now)
    if len(_failures[key]) >= LIMIT:  # the fifth within 15 minutes: wait from now
        _blocked_until[key] = now + WINDOW_SECONDS
        _failures.pop(key, None)


def succeeded(project_id: str, who: str) -> None:
    _failures.pop((project_id, who), None)


def reset() -> None:
    """For tests."""
    _failures.clear()
    _blocked_until.clear()
