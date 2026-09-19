"""Worker Event Contract for JARVIS Civic Phase 8.5.

Defines the strongly typed event contract consumed by the SAM CLI local serverless worker.
Enforces minimal payload design, versioning, and validation.
Strictly ignores any client-supplied recipient, role, or department fields in favor
of backend-authoritative CaseStore persistence.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator


class WorkerEventType(str, Enum):
    CASE_CREATED = "CASE_CREATED"
    WORKFLOW_STAGE_CHANGED = "WORKFLOW_STAGE_CHANGED"
    EVIDENCE_AVAILABLE = "EVIDENCE_AVAILABLE"
    RESOLUTION_READY = "RESOLUTION_READY"


class NotificationWorkEvent(BaseModel):
    """Strongly typed notification work item dispatched to the serverless worker."""

    event_id: str = Field(..., description="Unique event execution ID (UUID or deterministic ID)")
    event_type: WorkerEventType = Field(..., description="Target notification lifecycle event type")
    case_id: str = Field(..., description="Target civic case ID")
    event_version: int = Field(default=1, description="Event schema version")
    requested_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="ISO 8601 UTC timestamp of event creation",
    )
    source: str = Field(default="jarvis-civic", description="Originating event source")
    payload: Dict[str, Any] = Field(
        default_factory=dict,
        description="Optional auxiliary data (e.g. stage transition names). Client recipient/department fields are ignored.",
    )

    @field_validator("event_id")
    @classmethod
    def validate_event_id(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("event_id cannot be empty")
        return v.strip()

    @field_validator("case_id")
    @classmethod
    def validate_case_id(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("case_id cannot be empty")
        return v.strip()

    @field_validator("event_version")
    @classmethod
    def validate_event_version(cls, v: int) -> int:
        if v < 1:
            raise ValueError("event_version must be an integer >= 1")
        return v

    def sanitize_payload(self) -> Dict[str, Any]:
        """Strip any spoofed recipient or department overrides to ensure backend authority."""
        untrusted_keys = {
            "recipient_email",
            "recipient_role",
            "department",
            "principal_id",
            "owner_id",
            "session_id",
            "password",
            "token",
        }
        return {k: v for k, v in self.payload.items() if k.lower() not in untrusted_keys}


class WorkerExecutionStatus(str, Enum):
    SENT = "SENT"
    DUPLICATE_SUPPRESSED = "DUPLICATE_SUPPRESSED"
    FAILED = "FAILED"
    REJECTED = "REJECTED"


class WorkerResponse(BaseModel):
    """Structured result returned by the Lambda handler."""

    status: WorkerExecutionStatus
    event_id: str
    case_id: Optional[str] = None
    notification_ids: List[str] = Field(default_factory=list)
    count: int = 0
    reason: Optional[str] = None
    errors: List[str] = Field(default_factory=list)
    message: Optional[str] = None
