"""Conversation Session Repository for JARVIS Civic.

Manages conversational state across multi-turn citizen interactions, ensuring
seamless information accumulation (defect intent, physical location, postal code)
without losing earlier context.
"""

from abc import ABC, abstractmethod
from datetime import datetime, timezone
import re
import threading
from typing import Dict, Optional
from pydantic import BaseModel, Field

from app.models.civic_state import CanonicalCivicState


def validate_session_id(session_id: str) -> str:
    """Validate session token security properties.

    Rejects malformed, path-traversing, or oversized session identifiers.
    """
    if not session_id or not isinstance(session_id, str):
        raise ValueError("Session ID must be a non-empty string.")

    cleaned = session_id.strip()
    if len(cleaned) < 3 or len(cleaned) > 128:
        raise ValueError("Session ID length must be between 3 and 128 characters.")

    if not re.match(r"^[a-zA-Z0-9_\-]+$", cleaned):
        raise ValueError("Session ID contains invalid characters. Allowed: alphanumeric, hyphens, underscores.")

    return cleaned


class ConversationSession(BaseModel):
    """Container for active citizen session state."""

    session_id: str
    state: CanonicalCivicState
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ConversationSessionRepository(ABC):
    """Abstract interface for multi-turn conversation session storage."""

    @abstractmethod
    def get_session(self, session_id: str) -> Optional[CanonicalCivicState]:
        """Retrieve stored canonical civic state for session."""
        pass

    @abstractmethod
    def save_session(self, session_id: str, state: CanonicalCivicState) -> None:
        """Persist or update conversational state for session."""
        pass

    @abstractmethod
    def delete_session(self, session_id: str) -> bool:
        """Delete stored session state."""
        pass

    @abstractmethod
    def clear(self) -> None:
        """Clear all stored sessions (useful for isolated tests)."""
        pass


class LocalConversationSessionRepository(ConversationSessionRepository):
    """Thread-safe, in-memory implementation of ConversationSessionRepository."""

    def __init__(self, max_sessions: int = 2000):
        self._sessions: Dict[str, ConversationSession] = {}
        self._lock = threading.Lock()
        self._max_sessions = max_sessions

    def get_session(self, session_id: str) -> Optional[CanonicalCivicState]:
        clean_id = validate_session_id(session_id)
        with self._lock:
            session = self._sessions.get(clean_id)
            if not session:
                return None
            # Return a copy to prevent mutation outside save_session
            return session.state.model_copy(deep=True)

    def save_session(self, session_id: str, state: CanonicalCivicState) -> None:
        clean_id = validate_session_id(session_id)
        with self._lock:
            now = datetime.now(timezone.utc)
            if clean_id in self._sessions:
                self._sessions[clean_id].state = state.model_copy(deep=True)
                self._sessions[clean_id].updated_at = now
            else:
                if len(self._sessions) >= self._max_sessions:
                    # Evict oldest session
                    oldest_id = min(self._sessions.keys(), key=lambda k: self._sessions[k].updated_at)
                    del self._sessions[oldest_id]

                self._sessions[clean_id] = ConversationSession(
                    session_id=clean_id,
                    state=state.model_copy(deep=True),
                    created_at=now,
                    updated_at=now,
                )

    def delete_session(self, session_id: str) -> bool:
        clean_id = validate_session_id(session_id)
        with self._lock:
            return self._sessions.pop(clean_id, None) is not None

    def clear(self) -> None:
        with self._lock:
            self._sessions.clear()


# Global thread-safe session repository instance
session_repository = LocalConversationSessionRepository()
conversation_session_repository = session_repository
