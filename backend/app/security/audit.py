"""Application-Level Append-Only Audit Event Stream for JARVIS Civic.

Phase 3 Security Component:
Captures every authorization evaluation decision into an in-memory, thread-safe
append-only event stream.

NOTE: This is an application-level in-memory stream for local prototype auditing.
It does NOT claim cryptographic immutability and does NOT use persistent database storage.
"""

from datetime import datetime, timezone
import threading
from typing import List, Optional
from pydantic import BaseModel, Field


class AuditEvent(BaseModel):
    """Immutable record of an authorization decision event."""

    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    principal_id: str
    principal_role: str
    action: str
    resource_id: str
    resource_type: str = "CivicCase"
    decision: str  # "ALLOW" or "DENY"
    reason: Optional[str] = None
    policy_id: Optional[str] = None
    correlation_id: Optional[str] = None
    department: Optional[str] = None


class AuditDispatcher:
    """Thread-safe, append-only in-memory audit event stream."""

    def __init__(self, max_records: int = 5000):
        self._records: List[AuditEvent] = []
        self._lock = threading.Lock()
        self._max_records = max_records

    def record_event(self, event: AuditEvent) -> None:
        """Append an authorization event to the stream."""
        with self._lock:
            self._records.append(event)
            # Bound memory growth if needed
            if len(self._records) > self._max_records:
                self._records = self._records[-self._max_records:]

    def get_events(
        self,
        department: Optional[str] = None,
        limit: int = 100,
    ) -> List[AuditEvent]:
        """Retrieve audit events, optionally filtered by department scope."""
        with self._lock:
            if department:
                filtered = [e for e in self._records if e.department == department]
                return list(reversed(filtered[-limit:]))
            return list(reversed(self._records[-limit:]))

    def clear(self) -> None:
        """Clear events (primarily for isolated test fixtures)."""
        with self._lock:
            self._records.clear()

    def count(self) -> int:
        """Total count of recorded audit events."""
        with self._lock:
            return len(self._records)


# Global singleton dispatcher instance
audit_dispatcher = AuditDispatcher()
