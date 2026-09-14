"""Password hashing for local (Postgres-backed) accounts.

Replaces the plaintext comparison ``PasswordIdentityProvider`` used against
``config.yml``'s ``local-users`` (a documented dev-only weakness carried over
from Chainlit) -- passwords are now hashed at rest with bcrypt, never stored
or compared in cleartext.
"""

from __future__ import annotations

import bcrypt


def hash_password(plaintext: str) -> str:
    """Return a bcrypt hash of *plaintext*, suitable for ``User.password_hash``."""
    return bcrypt.hashpw(plaintext.encode(), bcrypt.gensalt()).decode()


def verify_password(plaintext: str, password_hash: str) -> bool:
    """Return True if *plaintext* matches *password_hash*.

    Uses bcrypt's own constant-time comparison internally -- no separate
    ``hmac.compare_digest`` needed (unlike the old plaintext-vs-plaintext
    check this replaces).
    """
    try:
        return bcrypt.checkpw(plaintext.encode(), password_hash.encode())
    except ValueError:
        # Malformed hash (e.g. empty string / not a bcrypt hash) -- never
        # authenticate against a bad hash, but don't raise into the caller.
        return False
