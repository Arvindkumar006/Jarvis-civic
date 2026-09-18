"""Canonical Civic State Model for JARVIS Civic.

Represents the core data contract for AI-generated civic grievance records.
Supports both complete and incomplete conversational states seamlessly.
"""

from datetime import datetime, timezone
import re
from typing import Any, List, Optional
from pydantic import BaseModel, Field, field_validator

from app.models.enums import (
    CaseStatus,
    CivicIntent,
    ControlledDepartment,
    EvidenceType,
    LocationSource,
    UrgencyLevel,
)


class CanonicalCivicState(BaseModel):
    """Central state container for a citizen's civic grievance record.

    Designed to represent an incomplete conversational state gracefully
    (e.g., missing location or landmark) as well as a fully synthesized docket.
    """

    # Identifiers
    case_id: Optional[str] = Field(
        default=None,
        description="Unique case identifier: NS-<CITY>-<YEAR>-<4_HEX_CHARS>",
    )
    session_id: Optional[str] = Field(
        default=None,
        description="Active citizen conversation session token",
    )

    # Core Civic Issue Extraction
    intent: Optional[CivicIntent] = Field(
        default=None,
        description="Classified civic defect category",
    )
    department: Optional[ControlledDepartment] = Field(
        default=None,
        description="Recommended municipal department for triage (non-official recommendation)",
    )
    description: Optional[str] = Field(
        default=None,
        description="Citizen's problem statement in their words or transcribed speech",
    )

    # Physical & Geographic Attributes
    location: Optional[str] = Field(
        default=None,
        description="Street name, neighborhood, or primary geographic reference",
    )
    location_text: Optional[str] = Field(
        default=None,
        description="Raw textual location representation from user message",
    )
    landmark: Optional[str] = Field(
        default=None,
        description="Prominent nearby reference landmark (e.g. opposite temple, near water tank)",
    )
    pincode: Optional[str] = Field(
        default=None,
        description="6-digit Indian postal code (must remain a string)",
    )
    latitude: Optional[float] = Field(
        default=None,
        ge=-90.0,
        le=90.0,
        description="Latitude coordinate when explicitly confirmed or map-selected",
    )
    longitude: Optional[float] = Field(
        default=None,
        ge=-180.0,
        le=180.0,
        description="Longitude coordinate when explicitly confirmed or map-selected",
    )
    location_source: LocationSource = Field(
        default=LocationSource.UNCONFIRMED,
        description="Origin semantics for location coordinates (TEXT_REFERENCE, MAP_SELECTED, GEOCODED, UNCONFIRMED)",
    )

    # Urgency & Risk
    urgency: Optional[UrgencyLevel] = Field(
        default=None,
        description="Objective risk classification (LOW, MEDIUM, HIGH, CRITICAL)",
    )
    urgency_rationale: Optional[str] = Field(
        default=None,
        description="Explainable criteria behind urgency assignment",
    )

    # Evidence & Media
    evidence: List[EvidenceType] = Field(
        default_factory=list,
        description="Types of attached evidence provided",
    )
    evidence_uris: List[str] = Field(
        default_factory=list,
        description="Storage paths or URIs of attached evidence files",
    )

    # Language & Conversation Feedback Loop
    citizen_language: Optional[str] = Field(
        default=None,
        description="Detected or selected language of the citizen",
    )
    language: Optional[str] = Field(
        default=None,
        description="Detected or selected language of the citizen (alias for citizen_language)",
    )
    confidence: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Confidence score of AI extraction (0.0 to 1.0)",
    )
    missing_fields: List[str] = Field(
        default_factory=list,
        description="List of mandatory fields requiring citizen clarification",
    )
    followup_question: Optional[str] = Field(
        default=None,
        description="Targeted follow-up question in the citizen's language",
    )
    ready_for_action: bool = Field(
        default=False,
        description="True only when all mandatory intake criteria are satisfied",
    )

    # Lifecycle & Audit Metadata
    status: CaseStatus = Field(
        default=CaseStatus.DRAFT,
        description="Current lifecycle status of the case record",
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timezone-aware UTC timestamp of creation",
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timezone-aware UTC timestamp of last update",
    )

    @field_validator("pincode", mode="before")
    @classmethod
    def validate_pincode_type(cls, v: Any) -> Any:
        if v is not None and not isinstance(v, str):
            raise ValueError("Pincode must be provided as a string to preserve leading zeros.")
        return v

    @field_validator("pincode", mode="after")
    @classmethod
    def validate_pincode_format(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            if not re.match(r"^[1-9][0-9]{5}$", v):
                raise ValueError(
                    f"Invalid PIN code '{v}'. Must be a 6-digit Indian postal code starting with 1-9 (e.g. '600028')."
                )
        return v

    @field_validator("case_id", mode="after")
    @classmethod
    def validate_case_id_format(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            pattern = r"^NS-[A-Z]{3,4}-\d{4}-[A-F0-9]{4}$"
            if not re.match(pattern, v):
                raise ValueError(
                    f"Invalid case_id '{v}'. Expected format: NS-<CITY_CODE>-<YEAR>-<4_HEX> (e.g. 'NS-CHN-2026-9E4B')."
                )
        return v
