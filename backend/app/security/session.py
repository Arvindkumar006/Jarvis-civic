"""Server-Managed Authenticated Session Storage for JARVIS Civic.

Phase 8.1: Server-Side Session Management.
Manages cryptographically secure sessions with server-side expiration and revocation.

SECURITY INVARIANTS:
1. Session IDs are high-entropy cryptographic random tokens.
2. Expired or revoked sessions cannot authenticate requests.
3. Thread-safe operations for concurrent request environments.
"""

from datetime import datetime, timedelta, timezone
import logging
import secrets
import threading
from typing import Dict, Optional
from pydantic import BaseModel, Field

from app.config.settings import settings
from app.models.account import UserAccount
from app.models.security import ApplicationRole

logger = logging.getLogger("jarvis.security.session")


class AuthSession(BaseModel):
    """Server-side representation of an authenticated user session."""

    session_id: str = Field(..., description="Cryptographically random session token")
    principal_id: str = Field(..., description="Principal ID of authenticated user")
    email: str = Field(..., description="Account email")
    display_name: str = Field(..., description="Account display name")
    role: ApplicationRole = Field(..., description="Authoritative account role")
    department: Optional[str] = Field(default=None, description="Department scope if applicable")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime = Field(..., description="Expiration timestamp")
    is_active: bool = Field(default=True, description="Active status; False when revoked/logged out")

    def is_valid(self) -> bool:
        """Check if session is active and not expired."""
        now = datetime.now(timezone.utc)
        return self.is_active and self.expires_at > now


class SessionStore:
    """Thread-safe server-side session repository."""

    def __init__(self, default_ttl_seconds: Optional[int] = None):
        self._ttl_seconds = default_ttl_seconds or settings.AUTH_SESSION_TTL_SECONDS
        self._sessions: Dict[str, AuthSession] = {}
        self._lock = threading.Lock()

    def create_session(
        self,
        account: UserAccount,
        ttl_seconds: Optional[int] = None,
    ) -> AuthSession:
        """Generate a new secure authenticated session for the given account."""
        ttl = ttl_seconds if ttl_seconds is not None else self._ttl_seconds
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(seconds=ttl)
        session_id = secrets.token_urlsafe(32)

        session = AuthSession(
            session_id=session_id,
            principal_id=account.principal_id,
            email=account.email,
            display_name=account.display_name,
            role=account.role,
            department=account.department,
            created_at=now,
            expires_at=expires_at,
            is_active=True,
        )

        with self._lock:
            self._sessions[session_id] = session

        logger.info("Session created for principal '%s' (expires in %ds)", account.principal_id, ttl)
        return session

    def get_session(self, session_id: Optional[str]) -> Optional[AuthSession]:
        """Retrieve an active, non-expired session by ID. Returns None if invalid or expired."""
        if not session_id or not isinstance(session_id, str):
            return None

        with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                return None

            if not session.is_valid():
                # Clean up expired or revoked session
                logger.debug("Session '%s' is expired or inactive", session_id[:8])
                return None

            return session

    def invalidate_session(self, session_id: Optional[str]) -> bool:
        """Revoke a session immediately upon logout or invalidation."""
        if not session_id or not isinstance(session_id, str):
            return False

        with self._lock:
            session = self._sessions.get(session_id)
            if session:
                session.is_active = False
                self._sessions.pop(session_id, None)
                logger.info("Session invalidated for principal '%s'", session.principal_id)
                return True
            return False

    def cleanup_expired(self) -> int:
        """Remove all expired or inactive sessions from memory."""
        now = datetime.now(timezone.utc)
        count = 0
        with self._lock:
            expired_keys = [
                sid for sid, s in self._sessions.items()
                if not s.is_active or s.expires_at <= now
            ]
            for sid in expired_keys:
                del self._sessions[sid]
                count += 1
        return count

    def clear(self) -> None:
        """Clear all sessions (primarily for test isolation)."""
        with self._lock:
            self._sessions.clear()


# Default singleton instance
session_store = SessionStore()
