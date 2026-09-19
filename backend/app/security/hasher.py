"""Password Hashing Abstraction for JARVIS Civic.

Phase 8.1: Argon2id Password Hashing.
Enforces modern, memory-hard Argon2id password hashing and constant-time verification.

SECURITY INVARIANTS:
1. Passwords are never logged or persisted in plaintext.
2. Verification exceptions are caught safely and return boolean without leaking details.
"""

import logging
from typing import Optional
from argon2 import PasswordHasher as _Argon2PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

logger = logging.getLogger("jarvis.security.hasher")


class PasswordHasher:
    """Argon2id password hashing and verification abstraction."""

    def __init__(
        self,
        time_cost: int = 2,
        memory_cost: int = 19456,  # 19 MiB
        parallelism: int = 1,
        hash_len: int = 32,
        salt_len: int = 16,
    ):
        self._hasher = _Argon2PasswordHasher(
            time_cost=time_cost,
            memory_cost=memory_cost,
            parallelism=parallelism,
            hash_len=hash_len,
            salt_len=salt_len,
        )

    def hash_password(self, password: str) -> str:
        """Generate a secure Argon2id hash for the given password."""
        if not password or not isinstance(password, str):
            raise ValueError("Password must be a non-empty string.")
        return self._hasher.hash(password)

    def verify_password(self, password: str, password_hash: str) -> bool:
        """Verify a password against a stored Argon2id hash in constant time."""
        if not password or not password_hash:
            return False
        try:
            return self._hasher.verify(password_hash, password)
        except VerifyMismatchError:
            return False
        except (InvalidHashError, VerificationError) as exc:
            logger.warning("Password verification failure due to invalid hash structure: %s", type(exc).__name__)
            return False
        except Exception as exc:
            logger.error("Unexpected error during password verification: %s", type(exc).__name__)
            return False


# Default singleton instance
password_hasher = PasswordHasher()
