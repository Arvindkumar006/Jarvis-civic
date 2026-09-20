"""Security, Authorization, and Principal Models for JARVIS Civic.

Phase 3: AWS Cedar Policy Enforcement Point (PEP) and Policy Decision Point (PDP).

NOTE ON APPLICATION ROLES:
These roles (CITIZEN, AUTHORITY_OFFICER, MUNICIPAL_SUPERVISOR, ADMINISTRATOR, PUBLIC)
are strictly application-level authorization roles within the JARVIS Civic software.
They do NOT represent official government credentials, government identity verification,
proof of civil service employment, or municipal legal authority.
"""

import re
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator

from app.models.enums import CaseStatus, ControlledDepartment


class ApplicationRole(str, Enum):
    """Application-level roles for Cedar policy evaluation."""

    CITIZEN = "CITIZEN"
    AUTHORITY_OFFICER = "AUTHORITY_OFFICER"
    MUNICIPAL_SUPERVISOR = "MUNICIPAL_SUPERVISOR"
    ADMINISTRATOR = "ADMINISTRATOR"
    PUBLIC = "PUBLIC"


class CivicAction(str, Enum):
    """Explicit civic operations protected by Cedar policies."""

    CREATE_CASE = "create_case"
    READ_OWN_CASE = "read_own_case"
    UPDATE_OWN_CASE = "update_own_case"
    READ_PUBLIC_TRACKING = "read_public_tracking"
    READ_AUTHORITY_CASE = "read_authority_case"
    UPDATE_CASE_STATUS = "update_case_status"
    ADD_RESOLUTION_NOTE = "add_resolution_note"
    ADD_EVIDENCE = "add_evidence"
    ADD_RESOLUTION_EVIDENCE = "add_resolution_evidence"
    READ_EVIDENCE = "read_evidence"
    READ_AUDIT_LOG = "read_audit_log"
    SEARCH_DOCKETS = "search_dockets"
    ACCEPT_RESOLUTION = "accept_resolution"
    REJECT_RESOLUTION = "reject_resolution"
    REQUEST_CITIZEN_CONFIRMATION = "request_citizen_confirmation"


class ApplicationPrincipal(BaseModel):
    """Application-level principal identity for request authorization.

    WARNING: In Phase 3, this is a local development/test identity mechanism.
    Production authentication (e.g. verified login) is outside Phase 3.
    """

    principal_id: str = Field(..., description="Unique principal identifier (e.g., citizen-123, officer-45)")
    role: ApplicationRole = Field(default=ApplicationRole.PUBLIC, description="Application role")
    department: Optional[str] = Field(default=None, description="Assigned department/jurisdiction for authority roles")

    @property
    def cedar_entity_type(self) -> str:
        """Map ApplicationRole to Cedar schema entity type."""
        mapping = {
            ApplicationRole.CITIZEN: "Citizen",
            ApplicationRole.AUTHORITY_OFFICER: "AuthorityOfficer",
            ApplicationRole.MUNICIPAL_SUPERVISOR: "MunicipalSupervisor",
            ApplicationRole.ADMINISTRATOR: "Administrator",
            ApplicationRole.PUBLIC: "PublicUser",
        }
        return mapping.get(self.role, "PublicUser")


class AuthorizationRequest(BaseModel):
    """Input parameters passed to Cedar Policy Decision Point (PDP)."""

    principal: ApplicationPrincipal
    action: Any = Field(..., description="CivicAction or action string")
    resource_type: str = Field(default="CivicCase", description="Cedar entity type: CivicCase or AuditRecord")
    resource_id: str = Field(..., description="Target resource identifier")
    resource_owner: Optional[str] = Field(default=None, description="Principal ID of resource owner (for CivicCase)")
    resource_department: Optional[str] = Field(default=None, description="Department handling the resource")
    resource_status: Optional[str] = Field(default=None, description="Current lifecycle status")
    is_public: bool = Field(default=False, description="Whether resource allows public tracking projection")
    context: Dict[str, Any] = Field(default_factory=dict, description="Optional request context")


class AuthorizationDecision(BaseModel):
    """Structured result returned by Cedar Policy Decision Point."""

    allowed: bool
    decision: str = Field(..., description="'ALLOW' or 'DENY'")
    reason: Optional[str] = Field(default=None, description="Internal evaluation explanation or matched policy")
    policy_id: Optional[str] = Field(default=None, description="Matched Cedar policy identifier if available")
    diagnostics: Optional[str] = Field(default=None, description="Internal diagnostics (never leaked to end users)")


# ---------------------------------------------------------------------------
# API Projections & Case Demonstration Models
# ---------------------------------------------------------------------------

class CivicCaseCreateRequest(BaseModel):
    """Payload to create a new civic case."""

    description: str = Field(..., min_length=5, max_length=5000, description="Citizen's problem statement")
    location: str = Field(..., min_length=2, max_length=500, description="Street, landmark, or area")
    department: ControlledDepartment = Field(default=ControlledDepartment.DRAINAGE_STORMWATER)
    pincode: Optional[str] = Field(default=None, description="6-digit PIN code")
    is_public: bool = Field(default=True, description="Whether tracking is publicly accessible")
    latitude: Optional[float] = Field(default=None, ge=-90.0, le=90.0, description="Confirmed latitude coordinate")
    longitude: Optional[float] = Field(default=None, ge=-180.0, le=180.0, description="Confirmed longitude coordinate")
    location_source: Optional[str] = Field(default=None, description="Source of coordinates e.g. MAP_SELECTED")

    @field_validator("description", mode="after")
    @classmethod
    def validate_description(cls, v: str) -> str:
        cleaned = v.strip()
        if len(cleaned) < 5:
            raise ValueError("Description must contain at least 5 non-whitespace characters.")
        return cleaned

    @field_validator("location", mode="after")
    @classmethod
    def validate_location(cls, v: str) -> str:
        cleaned = v.strip()
        if len(cleaned) < 2:
            raise ValueError("Location must contain at least 2 non-whitespace characters.")
        return cleaned

    @field_validator("pincode", mode="after")
    @classmethod
    def validate_pincode(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            cleaned = v.strip()
            if not cleaned:
                return None
            if not re.match(r"^[1-9][0-9]{5}$", cleaned):
                raise ValueError(
                    f"Invalid PIN code '{cleaned}'. Must be a 6-digit Indian postal code starting with 1-9 (e.g. '560038')."
                )
            return cleaned
        return v


class CivicCaseUpdateRequest(BaseModel):
    """Payload to update citizen's own case details."""

    description: Optional[str] = Field(default=None, min_length=5, max_length=5000)
    location: Optional[str] = Field(default=None, min_length=2, max_length=500)
    pincode: Optional[str] = Field(default=None)

    @field_validator("description", mode="after")
    @classmethod
    def validate_update_desc(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            cleaned = v.strip()
            if len(cleaned) < 5:
                raise ValueError("Description must contain at least 5 non-whitespace characters.")
            return cleaned
        return v

    @field_validator("location", mode="after")
    @classmethod
    def validate_update_loc(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            cleaned = v.strip()
            if len(cleaned) < 2:
                raise ValueError("Location must contain at least 2 non-whitespace characters.")
            return cleaned
        return v

    @field_validator("pincode", mode="after")
    @classmethod
    def validate_update_pincode(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            cleaned = v.strip()
            if not cleaned:
                return None
            if not re.match(r"^[1-9][0-9]{5}$", cleaned):
                raise ValueError(
                    f"Invalid PIN code '{cleaned}'. Must be a 6-digit Indian postal code starting with 1-9 (e.g. '560038')."
                )
            return cleaned
        return v


class CivicCaseStatusUpdateRequest(BaseModel):
    """Payload for authority status update."""

    status: CaseStatus = Field(..., description="Target case lifecycle status")
    note: Optional[str] = Field(default=None, max_length=2000, description="Optional transition note")

    @field_validator("note", mode="after")
    @classmethod
    def clean_note(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            cleaned = v.strip()
            return cleaned if cleaned else None
        return v


class ResolutionNoteRequest(BaseModel):
    """Payload for authority resolution note."""

    note: str = Field(..., min_length=3, max_length=2000, description="Authority resolution or inspection note")

    @field_validator("note", mode="after")
    @classmethod
    def validate_note(cls, v: str) -> str:
        cleaned = v.strip()
        if len(cleaned) < 3:
            raise ValueError("Resolution note must contain at least 3 non-whitespace characters.")
        return cleaned


class CitizenResolutionAcceptRequest(BaseModel):
    """Payload for authenticated citizen accepting case resolution."""

    feedback: Optional[str] = Field(default=None, max_length=2000, description="Optional citizen resolution feedback")

    @field_validator("feedback", mode="after")
    @classmethod
    def clean_feedback(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            cleaned = v.strip()
            return cleaned if cleaned else None
        return v


class CitizenResolutionRejectRequest(BaseModel):
    """Payload for authenticated citizen rejecting case resolution."""

    reason: str = Field(..., min_length=5, max_length=2000, description="Substantive reason explaining why resolution is rejected")

    @field_validator("reason", mode="after")
    @classmethod
    def validate_reason(cls, v: str) -> str:
        cleaned = v.strip()
        if len(cleaned) < 5:
            raise ValueError("Rejection reason must contain at least 5 non-whitespace characters explaining what remains unresolved.")
        return cleaned


class ResolutionConfirmationRequest(BaseModel):
    """Payload for authority requesting citizen confirmation."""

    message: Optional[str] = Field(default=None, max_length=2000, description="Optional confirming resolution message")

    @field_validator("message", mode="after")
    @classmethod
    def clean_message(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            cleaned = v.strip()
            return cleaned if cleaned else None
        return v


class CivicCaseRecord(BaseModel):
    """Full civic case representation stored in application layer."""

    case_id: str
    owner_id: str
    department: str
    status: CaseStatus = CaseStatus.DOCKET_CREATED
    description: str
    location: str
    landmark: Optional[str] = None
    pincode: Optional[str] = None
    urgency: Optional[str] = None
    urgency_rationale: Optional[str] = None
    session_id: Optional[str] = None
    is_public: bool = True
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    location_source: Optional[str] = None
    evidence_uris: List[str] = Field(default_factory=list)
    resolution_notes: List[str] = Field(default_factory=list)
    resolution_confirmed: bool = False
    resolution_confirmed_at: Optional[datetime] = None
    resolution_rejected_at: Optional[datetime] = None
    citizen_feedback: Optional[str] = None
    rejection_count: int = 0
    active_resolution_attempt: Optional[str] = None
    confirmation_requested: bool = False
    confirmation_requested_at: Optional[datetime] = None
    resolution_message: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class EvidenceMetadata(BaseModel):
    """Server-side generated metadata for uploaded evidence object."""

    evidence_id: str
    case_id: str
    object_key: str
    s3_uri: str
    filename: str
    content_type: str
    size_bytes: int
    uploaded_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PublicTrackingProjection(BaseModel):
    """Safe, redacted public tracking projection.

    CRITICAL SECURITY INVARIANT:
    Must NEVER expose private citizen identifiers, contact details, private notes,
    evidence URIs, or internal authorization metadata to public tracking queries.
    """

    case_id: str
    status: str
    recommended_department: str
    created_at: datetime
    updated_at: datetime


class CaseHistoryItem(BaseModel):
    """Canonical representation of a civic case lifecycle milestone."""

    milestone_id: str = Field(..., description="Unique milestone or event identifier")
    status: str = Field(..., description="Lifecycle status code")
    label: str = Field(..., description="Human-readable stage title")
    timestamp: datetime = Field(..., description="UTC timestamp when milestone occurred")
    department: Optional[str] = Field(default=None, description="Department context")
    description: str = Field(..., description="Neutral explanation of stage")
    actor_role: Optional[str] = Field(default=None, description="General actor role category")
    note: Optional[str] = Field(default=None, description="Safe summary note if applicable")


class PublicCaseHistoryItem(BaseModel):
    """Sanitized public projection of a case lifecycle milestone.

    Strictly withholds internal actor_role, notes, principal identifiers, and metadata.
    """

    milestone_id: str = Field(..., description="Milestone identifier")
    status: str = Field(..., description="Lifecycle status code")
    label: str = Field(..., description="Human-readable stage title")
    timestamp: datetime = Field(..., description="UTC timestamp when milestone occurred")
    description: str = Field(..., description="Neutral public-safe explanation of stage")


class AuthorizedCaseHistoryItem(CaseHistoryItem):
    """Department-scoped or administrator authorized case lifecycle milestone."""

    pass
