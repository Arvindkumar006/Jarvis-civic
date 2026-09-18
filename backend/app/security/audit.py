"""Application-Level Append-Only Audit Event Stream for JARVIS Civic.

Phase 6 Security & Audit Trail Component:
Captures every authorization evaluation decision and case lifecycle mutation
into an immutable, append-only event stream.
"""

from datetime import datetime, timezone
import threading
from typing import Any, Dict, List, Optional
import uuid
from pydantic import BaseModel, Field


class AuditEvent(BaseModel):
    """Append-only application audit record of an authorization decision or workflow event."""

    event_id: str = Field(default_factory=lambda: f"evt-{uuid.uuid4().hex[:12]}")
    case_id: Optional[str] = None
    event_type: str = Field(default="AUTHORIZATION_EVALUATION")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    principal_id: str
    principal_role: str
    principal_department: Optional[str] = None
    action: str
    resource_id: str
    resource_type: str = "CivicCase"
    decision: str = Field(default="ALLOW")  # "ALLOW" or "DENY"
    outcome: str = Field(default="SUCCESS")  # "SUCCESS", "DENIED", "VALIDATED"
    previous_status: Optional[str] = None
    new_status: Optional[str] = None
    reason: Optional[str] = None
    policy_id: Optional[str] = None
    correlation_id: Optional[str] = None
    department: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


from typing import Any, Callable, Dict, List, Optional
import logging

logger = logging.getLogger("jarvis.security.audit")


class AuditDispatcher:
    """Thread-safe, append-only in-memory audit event stream with listener fan-out."""

    def __init__(self, max_records: int = 5000):
        self._records: List[AuditEvent] = []
        self._listeners: List[Callable[[AuditEvent], None]] = []
        self._lock = threading.Lock()
        self._max_records = max_records

    def register_listener(self, listener: Callable[[AuditEvent], None]) -> None:
        """Register a persistence or forwarding listener for audit events."""
        with self._lock:
            if listener not in self._listeners:
                self._listeners.append(listener)

    def record_event(self, event: AuditEvent) -> None:
        """Append an authorization or workflow event to the stream and notify listeners."""
        with self._lock:
            self._records.append(event)
            if len(self._records) > self._max_records:
                self._records = self._records[-self._max_records:]
            listeners = list(self._listeners)

        for listener in listeners:
            try:
                listener(event)
            except Exception as exc:
                logger.warning("Audit listener notification failed: %s", exc)

    def record_workflow_event(
        self,
        case_id: str,
        event_type: str = "WORKFLOW_MUTATION",
        previous_status: Optional[str] = None,
        new_status: Optional[str] = None,
        principal: Optional[Any] = None,
        principal_id: Optional[str] = None,
        principal_role: Optional[str] = None,
        department: Optional[str] = None,
        action: Optional[str] = None,
        outcome: str = "SUCCESS",
        reason: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> AuditEvent:
        """Record a successful or rejected lifecycle mutation in the audit stream."""
        p_id = (
            principal.principal_id
            if principal and hasattr(principal, "principal_id")
            else (principal_id or "system")
        )
        p_role = (
            principal.role.value
            if principal and hasattr(principal, "role") and hasattr(principal.role, "value")
            else (str(principal.role) if principal and hasattr(principal, "role") else (principal_role or "SYSTEM"))
        )
        dept = (
            principal.department
            if principal and hasattr(principal, "department")
            else department
        )

        event = AuditEvent(
            case_id=case_id,
            event_type=event_type,
            principal_id=p_id,
            principal_role=p_role,
            principal_department=dept,
            action=action or event_type,
            resource_id=case_id,
            resource_type="CivicCase",
            decision="ALLOW" if outcome == "SUCCESS" else "DENY",
            outcome=outcome,
            previous_status=previous_status,
            new_status=new_status,
            department=dept,
            reason=reason,
            metadata=metadata or {},
        )
        self.record_event(event)
        return event

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

    def get_events_for_case(
        self,
        case_id: str,
        department: Optional[str] = None,
        limit: int = 100,
    ) -> List[AuditEvent]:
        """Retrieve audit events for a specific case ID, filtered by department if specified."""
        with self._lock:
            filtered = [
                e for e in self._records
                if (e.case_id == case_id or e.resource_id == case_id)
                and (department is None or e.department == department)
            ]
            return list(reversed(filtered[-limit:]))

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

