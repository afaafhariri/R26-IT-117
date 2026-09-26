"""Password hashing (Argon2id) and the password policy.

Hashing is deliberately slow (tens of milliseconds), so callers run it in a
worker thread rather than on the event loop.
"""

import secrets
import unicodedata

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

# argon2-cffi's defaults are the RFC 9106 low-memory profile for Argon2id.
_hasher = PasswordHasher()

MIN_LENGTH = 12
MAX_LENGTH = 128


def _normalise(password: str) -> str:
    # The same password typed on different keyboards/OSes can arrive as
    # different Unicode sequences; NFKC makes them compare equal.
    return unicodedata.normalize("NFKC", password)


def password_problem(password: str) -> str | None:
    """Returns why a new password is unacceptable, or None if it's fine.

    Length is the only rule: composition rules ("one symbol") push people to
    predictable patterns and are no longer recommended by NIST.
    """
    length = len(_normalise(password))
    if length < MIN_LENGTH:
        return f"Use at least {MIN_LENGTH} characters."
    if length > MAX_LENGTH:
        return f"Use at most {MAX_LENGTH} characters."
    return None


def hash_password(password: str) -> str:
    return _hasher.hash(_normalise(password))


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, _normalise(password))
    except (VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    """True when the hash was made with weaker parameters than today's."""
    return _hasher.check_needs_rehash(password_hash)


# Verified against when no account matches the email, so an unknown email
# takes as long to reject as a wrong password and can't be told apart.
DUMMY_HASH = hash_password(secrets.token_urlsafe(16))
