"""Structured Intermediate Reasoning Models for Phase 2.

These models enforce strict schema validation on intermediate agent outputs
before consolidating them into CanonicalCivicState.
"""

from typing import List, Optional
from pydantic import BaseModel, Field

from app.models.enums import CivicIntent, ControlledDepartment, UrgencyLevel


class IntentAnalysis(BaseModel):
    """Output of the Requirement & Intent Analyzer agent."""

    intent: CivicIntent = Field(
        default=CivicIntent.OTHER_CIVIC_ISSUE,
        description="Classified controlled civic intent",
    )
    is_civic: bool = Field(
        default=True,
        description="Whether the citizen input describes a genuine civic issue",
    )
    language: str = Field(
        default="English",
        description="Detected natural language or dialect",
    )
    confidence: float = Field(
        default=0.8,
        ge=0.0,
        le=1.0,
        description="Model confidence score for the extraction",
    )
    initial_description: str = Field(
        ...,
        description="Summary problem description extracted from citizen input",
    )


class CivicExtraction(BaseModel):
    """Output of the Civic Information Extractor agent."""

    description: Optional[str] = Field(
        default=None,
        description="Refined factual problem description",
    )
    location: Optional[str] = Field(
        default=None,
        description="Explicit street name or primary geographic location",
    )
    landmark: Optional[str] = Field(
        default=None,
        description="Prominent physical landmark mentioned by citizen",
    )
    pincode: Optional[str] = Field(
        default=None,
        description="6-digit Indian postal code if explicitly stated",
    )
    street: Optional[str] = Field(
        default=None,
        description="Explicit street or road name in citizen's original language",
    )
    area: Optional[str] = Field(
        default=None,
        description="Neighborhood, sector, ward, or sub-area in original language",
    )
    locality: Optional[str] = Field(
        default=None,
        description="City, town, or primary administrative locality in original language",
    )
    hazard_flags: List[str] = Field(
        default_factory=list,
        description="Factual safety hazard indicators explicitly reported by citizen",
    )



class ClassificationResult(BaseModel):
    """Output of the Department & Urgency Classifier agent."""

    department: ControlledDepartment = Field(
        default=ControlledDepartment.OTHER_MANUAL_REVIEW,
        description="Recommended municipal department for triage (non-official recommendation)",
    )
    urgency: UrgencyLevel = Field(
        default=UrgencyLevel.LOW,
        description="Objective risk classification",
    )
    urgency_rationale: str = Field(
        ...,
        description="Concise factual explanation for the assigned urgency level",
    )


class FollowUpResult(BaseModel):
    """Output of the Clarification & Follow-Up agent."""

    missing_fields: List[str] = Field(
        default_factory=list,
        description="Mandatory civic attributes absent from the complaint",
    )
    followup_question: Optional[str] = Field(
        default=None,
        description="Targeted clarification question in the citizen's language",
    )
    ready_for_action: bool = Field(
        default=False,
        description="True only when all mandatory intake criteria are satisfied",
    )
