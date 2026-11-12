"""Password hashing with Argon2.

Checking a password is deliberately slow (that is what makes stolen hashes hard to
crack), so it runs in a worker thread instead of blocking other requests. Each
check also uses a lot of memory (64 MiB), so only a few run at once per instance:
a burst of sign-in attempts waits in line instead of exhausting the instance.
"""

from __future__ import annotations

from anyio import CapacityLimiter, to_thread
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

_hasher = PasswordHasher()
# Checked when the email is unknown, so a wrong email takes as long as a wrong
# password and response times do not reveal which accounts exist.
_DUMMY_HASH = _hasher.hash("not a real password")
# Stored instead of a hash when an account's password is taken away (an
# unconfirmed sign-up that Google confirmed, `accounts.confirm_by_google`): not a
# hash, so no password matches it. Not None, which is an invite not yet accepted.
NO_PASSWORD = "!"
MAX_CONCURRENT_CHECKS = 4
_checks = CapacityLimiter(MAX_CONCURRENT_CHECKS)  # hashing new passwords too


async def hash_password(password: str) -> str:
    return await to_thread.run_sync(_hasher.hash, password, limiter=_checks)


async def verify_password(password_hash: str | None, password: str) -> bool:
    usable = password_hash is not None and password_hash != NO_PASSWORD

    def check() -> bool:
        try:
            # The dummy too without a password, so the answer takes as long.
            _hasher.verify(password_hash if usable else _DUMMY_HASH, password)
        except (VerificationError, InvalidHashError):
            return False
        return usable

    return await to_thread.run_sync(check, limiter=_checks)
