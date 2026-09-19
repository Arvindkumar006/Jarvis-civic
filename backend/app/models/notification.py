"""Notification Domain Models for JARVIS Civic.

Phase 8.4: Strongly typed notification entities, statuses, event types,
and sanitized delivery history projections.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from app.models.security import ApplicationRole


class NotificationStatus(str, Enum):
    """Lifecycle status of an individual notification delivery attempt."""

    PENDING = "PENDING"
    SENT = "SENT"
    FAILED = "FAILED"


class NotificationEventType(str, Enum):
    """Supported civic notification event types."""

    CASE_CREATED = "CASE_CREATED"
    WORKFLOW_STAGE_CHANGED = "WORKFLOW_STAGE_CHANGED"
    EVIDENCE_AVAILABLE = "EVIDENCE_AVAILABLE"
    RESOLUTION_READY = "RESOLUTION_READY"


class NotificationAttachmentMetadata(BaseModel):
    """Metadata representing a validated, persisted case artifact for attachment."""

    filename: str = Field(..., description="Sanitized attachment filename")
    content_type: str = Field(..., description="MIME content type")
    size_bytes: int = Field(..., ge=0, description="Size of artifact in bytes")
    s3_uri: Optional[str] = Field(default=None, description="Backend storage URI if stored in object store")


class NotificationRecord(BaseModel):
    """Authoritative notification delivery record stored in persistence."""

    notification_id: str = Field(..., description="Unique notification identifier")
    case_id: str = Field(..., description="Associated civic grievance case ID")
    event_type: NotificationEventType = Field(..., description="Event trigger type")
    recipient_email: str = Field(..., description="Target recipient email address")
    recipient_role: ApplicationRole = Field(..., description="Target recipient role")
    recipient_principal_id: str = Field(..., description="Target recipient principal identifier")
    subject: str = Field(..., description="Subject line of sent email")
    template_name: str = Field(..., description="Template identifier used to generate content")
    status: NotificationStatus = Field(default=NotificationStatus.PENDING, description="Delivery status")
    provider: str = Field(default="mailpit-smtp", description="Active delivery provider")
    idempotency_key: str = Field(..., description="Deterministic idempotency token")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    sent_at: Optional[datetime] = Field(default=None, description="Timestamp of successful SMTP transfer")
    failed_at: Optional[datetime] = Field(default=None, description="Timestamp of last failed attempt")
    error_message: Optional[str] = Field(default=None, description="Sanitized diagnostic error summary")
    attachment_metadata: List[NotificationAttachmentMetadata] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Safe context metadata")


class SanitizedNotificationItem(BaseModel):
    """Public/authorized projection of notification history (never leaks secrets/credentials)."""

    notification_id: str
    case_id: str
    event_type: NotificationEventType
    recipient_role: ApplicationRole
    recipient_masked_email: str
    subject: str
    status: NotificationStatus
    created_at: datetime
    sent_at: Optional[datetime] = None
    failed_at: Optional[datetime] = None


def mask_email(email: str) -> str:
    """Mask email address for sanitized public/authorized display (e.g. j***@example.com)."""
    if not email or "@" not in email:
        return "hidden@domain"
    parts = email.split("@", 1)
    user, domain = parts[0], parts[1]
    if len(user) <= 2:
        masked_user = user[0] + "*" if user else "*"
    else:
        masked_user = user[0] + "*" * (len(user) - 2) + user[-1]
    return f"{masked_user}@{domain}"
