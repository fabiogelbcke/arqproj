"""Tiny in-process TTL cache. Per-instance only, which is fine for a POC."""

from __future__ import annotations

import threading
import time
from typing import Callable, Hashable, TypeVar

T = TypeVar("T")


class TTLCache:
    def __init__(self, max_entries: int = 5000):
        self._data: dict[Hashable, tuple[float, object]] = {}
        self._lock = threading.Lock()
        self._max = max_entries

    def get_or_set(self, key: Hashable, ttl: float, compute: Callable[[], T]) -> T:
        now = time.monotonic()
        with self._lock:
            hit = self._data.get(key)
        if hit and hit[0] > now:
            return hit[1]  # type: ignore[return-value]
        value = compute()  # exceptions propagate and are not cached
        with self._lock:
            self._data[key] = (now + ttl, value)
            if len(self._data) > self._max:
                self._data = {k: v for k, v in self._data.items() if v[0] > now}
        return value

    def clear(self) -> None:
        with self._lock:
            self._data.clear()
