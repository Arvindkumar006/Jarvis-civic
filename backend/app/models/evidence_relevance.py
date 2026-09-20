"""Evidence Relevance Domain Models for JARVIS Civic.

Citizen Evidence Vision AI Relevance Pipeline.
Classifies citizen query + attached image into:
- RELATED: Image visually confirms the reported civic problem.
- NOT_RELATED: Image is clearly off-topic, contradictory, or unrelated.
- UNCERTAIN: Image is ambiguous, blurry, unrecognizable, or Vision AI is unavailable.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field, field_validator


class EvidenceRelevanceOutcome(str, Enum):
    """Categorical outcomes for citizen evidence relevance assessment."""

    RELATED = "RELATED"
    NOT_RELATED = "NOT_RELATED"
    UNCERTAIN = "UNCERTAIN"


class CitizenEvidenceAssessment(BaseModel):
    """Advisory Vision AI assessment for citizen attached evidence."""

    relevance: EvidenceRelevanceOutcome = Field(
        ...,
        description="Tripartite visual relevance outcome: RELATED, NOT_RELATED, or UNCERTAIN",
    )
    reason: str = Field(
        ...,
        description="Explainable advisory assessment summary",
    )
    detected_features: List[str] = Field(
        default_factory=list,
        description="Visual features or keywords detected in the image",
    )
    confidence: Optional[float] = Field(
        default=None,
        description="Advisory model confidence between 0.0 and 1.0",
    )
    model_id: Optional[str] = Field(
        default=None,
        description="Configured vision model identifier if AI assessment executed",
    )
    ai_available: bool = Field(
        default=False,
        description="Whether a genuine vision-capable AI provider was available and used",
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timezone-aware timestamp of the assessment",
    )

    @field_validator("confidence", mode="after")
    @classmethod
    def validate_confidence(cls, v: Optional[float]) -> Optional[float]:
        if v is not None:
            if v < 0.0 or v > 1.0:
                raise ValueError("Confidence must be between 0.0 and 1.0")
        return v
