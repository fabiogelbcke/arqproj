"""Password hashing with Argon2.

Checking a password is deliberately slow (that is what makes stolen hashes hard to
crack), so it runs in a worker thread instead of blocking other requests.
"""

from __future__ import annotations

from anyio import to_thread
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

_hasher = PasswordHasher()
# Checked when the email is unknown, so a wrong email takes as long as a wrong
# password and response times do not reveal which accounts exist.
_DUMMY_HASH = _hasher.hash("not a real password")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


async def verify_password(password_hash: str | None, password: str) -> bool:
    def check() -> bool:
        try:
            _hasher.verify(password_hash or _DUMMY_HASH, password)
        except (VerificationError, InvalidHashError):
            return False
        return password_hash is not None

    return await to_thread.run_sync(check)
