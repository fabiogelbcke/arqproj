"""Slowing down password guessing on client pages (step 2.4).

Five wrong passwords from one device (its address) for one project within 15
minutes, then that device waits 15 minutes from the fifth. Kept in this
server's memory: Cloud Run runs at most a couple of instances, so a guesser gets
at most a few more tries; a shared link's password guarded this way is
proportional to the risk (AGENTS.md). Staff sign-in, Google's returns and
other limited requests count the same way, each under its own key.
"""

from __future__ import annotations

import time
from collections import defaultdict
from collections.abc import Iterator
from contextlib import contextmanager

from fastapi import Request

LIMIT = 5
WINDOW_SECONDS = 15 * 60

# (project id, device) -> times of recent wrong passwords
_failures: dict[tuple[str, str], list[float]] = defaultdict(list)
# (project id, device) -> when its wait ends: 15 minutes after the fifth wrong try
_blocked_until: dict[tuple[str, str], float] = {}
# (project id, device) -> tries being checked right now: they count too, so a
# batch sent at once can't all slip past the limit while the hashes run.
_in_flight: dict[tuple[str, str], int] = defaultdict(int)


def device(request: Request) -> str:
    """The visitor's address. Each Google proxy in front appends the address it saw
    to X-Forwarded-For, after anything the visitor sent (which can be faked): the
    visitor's own is `forwarded_hops` entries from the end (1 with Cloud Run
    alone, 2 behind the A21 load balancer). Locally, the socket's."""
    settings = request.app.state.settings
    if settings.deployed:
        entries = [e.strip() for e in request.headers.get("x-forwarded-for", "").split(",")]
        hops = settings.forwarded_hops
        # Too few entries: "unknown", never the socket's (that's the last proxy).
        return entries[-hops] if len(entries) >= hops and entries[-hops] else "unknown"
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


def admit(project_id: str, who: str, now: float | None = None) -> bool:
    """Reserve one try before checking the password, or False if this device
    must wait. No await between the check and the reservation, so concurrent
    requests can't all pass. Every admitted try ends in `failed` or `succeeded`."""
    now = time.monotonic() if now is None else now
    key = (project_id, who)
    if blocked(project_id, who, now) or len(_recent(key, now)) + _in_flight[key] >= LIMIT:
        return False
    _in_flight[key] += 1
    return True


def _release(key: tuple[str, str]) -> None:
    _in_flight[key] -= 1
    if _in_flight[key] <= 0:
        _in_flight.pop(key, None)


def failed(project_id: str, who: str, now: float | None = None) -> None:
    now = time.monotonic() if now is None else now
    key = (project_id, who)
    _release(key)
    _recent(key, now)
    _failures[key].append(now)
    if len(_failures[key]) >= LIMIT:  # the fifth within 15 minutes: wait from now
        _blocked_until[key] = now + WINDOW_SECONDS
        _failures.pop(key, None)


def succeeded(project_id: str, who: str) -> None:
    _release((project_id, who))
    _failures.pop((project_id, who), None)


class Try:
    """A try `admit` reserved, being checked: end it with `failed` or `succeeded`."""

    def __init__(self, project_id: str, who: str) -> None:
        self.key = (project_id, who)
        self.ended = False

    def failed(self) -> None:
        if not self.ended:
            self.ended = True
            failed(*self.key)

    def succeeded(self) -> None:
        if not self.ended:
            self.ended = True
            succeeded(*self.key)


@contextmanager
def trying(project_id: str, who: str) -> Iterator[Try]:
    """Around the check of a try `admit` reserved. A try the block leaves unended
    (an unexpected error, a cancelled request) counts as failed: it is never left
    reserved, which would shrink the device's tries for good, and an error is
    never a free guess."""
    attempt = Try(project_id, who)
    try:
        yield attempt
    finally:
        attempt.failed()  # nothing if it ended already


def reset() -> None:
    """For tests."""
    _failures.clear()
    _blocked_until.clear()
    _in_flight.clear()
