"""Security, Authorization, and Principal Models for JARVIS Civic.

Phase 3: AWS Cedar Policy Enforcement Point (PEP) and Policy Decision Point (PDP).

NOTE ON APPLICATION ROLES:
These roles (CITIZEN, AUTHORITY_OFFICER, MUNICIPAL_SUPERVISOR, ADMINISTRATOR, PUBLIC)
are strictly application-level authorization roles within the JARVIS Civic software.
They do NOT represent official government credentials, government identity verification,
proof of civil service employment, or municipal legal authority.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

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
    READ_AUDIT_LOG = "read_audit_log"


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

    description: str = Field(..., min_length=5, description="Citizen's problem statement")
    location: str = Field(..., min_length=2, description="Street, landmark, or area")
    department: ControlledDepartment = Field(default=ControlledDepartment.DRAINAGE_STORMWATER)
    pincode: Optional[str] = Field(default=None, description="6-digit PIN code")
    is_public: bool = Field(default=True, description="Whether tracking is publicly accessible")


class CivicCaseUpdateRequest(BaseModel):
    """Payload to update citizen's own case details."""

    description: Optional[str] = Field(default=None, min_length=5)
    location: Optional[str] = Field(default=None, min_length=2)
    pincode: Optional[str] = Field(default=None)


class CivicCaseStatusUpdateRequest(BaseModel):
    """Payload for authority status update."""

    status: CaseStatus = Field(..., description="Target case lifecycle status")
    note: Optional[str] = Field(default=None, description="Optional transition note")


class ResolutionNoteRequest(BaseModel):
    """Payload for authority resolution note."""

    note: str = Field(..., min_length=3, description="Authority resolution or inspection note")


class CivicCaseRecord(BaseModel):
    """Full civic case representation stored in application layer."""

    case_id: str
    owner_id: str
    department: str
    status: CaseStatus = CaseStatus.DOCKET_CREATED
    description: str
    location: str
    pincode: Optional[str] = None
    is_public: bool = True
    resolution_notes: List[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PublicTrackingProjection(BaseModel):
    """Safe, redacted public tracking projection.

    CRITICAL SECURITY INVARIANT:
    Must NEVER expose private citizen identifiers, contact details, private notes,
    or internal authorization metadata to public tracking queries.
    """

    case_id: str
    status: str
    recommended_department: str
    created_at: datetime
    updated_at: datetime
