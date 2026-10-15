"""Password checks."""

import threading
import time

import anyio
import pytest

from backend.identity import passwords

pytestmark = pytest.mark.anyio


async def test_a_hash_checks_its_own_password_only():
    stored = await passwords.hash_password("a good password")
    assert await passwords.verify_password(stored, "a good password")
    assert not await passwords.verify_password(stored, "a wrong password")
    assert not await passwords.verify_password(None, "a good password")  # unknown email


async def test_a_burst_of_checks_runs_a_few_at_a_time(monkeypatch):
    """Each check takes 64 MiB: a burst of sign-ins must queue, not run all at once."""
    running = peak = 0
    lock = threading.Lock()

    class SlowHasher:
        def verify(self, _hash, _password):
            slow_verify()

    def slow_verify():
        nonlocal running, peak
        with lock:
            running += 1
            peak = max(peak, running)
        time.sleep(0.02)
        with lock:
            running -= 1

    monkeypatch.setattr(passwords, "_hasher", SlowHasher())
    async with anyio.create_task_group() as burst:
        for _ in range(20):
            burst.start_soon(passwords.verify_password, None, "guess")
    assert 1 < peak <= passwords.MAX_CONCURRENT_CHECKS
