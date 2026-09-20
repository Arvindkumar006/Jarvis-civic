"""Evidence Domain Models and Contracts for JARVIS Civic.

Phase 8.7: Production-grade backend evidence verification architecture.
Distinguishes ordinary case evidence submitted by citizens from resolution evidence
submitted by authorities. Combines deterministic validation, server-side SHA-256
hashing, and advisory AI assessment.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from app.models.evidence_relevance import EvidenceRelevanceOutcome


class EvidenceType(str, Enum):
    """Explicit distinction between citizen case evidence and authority resolution evidence."""

    CASE_EVIDENCE = "CASE_EVIDENCE"
    RESOLUTION_EVIDENCE = "RESOLUTION_EVIDENCE"


CivicEvidenceType = EvidenceType


class DeterministicValidationStatus(str, Enum):
    """Structured deterministic file validation outcomes."""

    VALID = "VALID"
    INVALID_TYPE = "INVALID_TYPE"
    MIME_MISMATCH = "MIME_MISMATCH"
    MAGIC_BYTES_MISMATCH = "MAGIC_BYTES_MISMATCH"
    FILE_TOO_LARGE = "FILE_TOO_LARGE"
    CORRUPT_FILE = "CORRUPT_FILE"
    UNSUPPORTED_FORMAT = "UNSUPPORTED_FORMAT"
    EMPTY_FILE = "EMPTY_FILE"


class VerificationOutcome(str, Enum):
    """Canonical verification outcomes for civic evidence assessment.

    VERIFIED: Deterministic validation passed and available assessment provides
              sufficient evidence consistent with expected evidence.
    LIKELY_VERIFIED: Evidence appears consistent, but confidence/strength is
                     insufficient for strongest assessment.
    UNCERTAIN: Insufficient information, unavailable AI, ambiguous evidence,
               or assessment cannot reliably determine validity.
    REJECTED: Evidence is invalid, contradictory, unusable, or fails validation.
    """

    VERIFIED = "VERIFIED"
    LIKELY_VERIFIED = "LIKELY_VERIFIED"
    UNCERTAIN = "UNCERTAIN"
    REJECTED = "REJECTED"


class DeterministicValidationResult(BaseModel):
    """Detailed evaluation result from deterministic file inspection."""

    status: DeterministicValidationStatus
    is_valid: bool
    sha256: str
    size_bytes: int
    sanitized_filename: str
    declared_content_type: str
    detected_content_type: str
    error_message: Optional[str] = None


class EvidenceVerificationRecord(BaseModel):
    """Server-side audit-ready evidence verification evaluation record."""

    verification_id: str = Field(..., description="Unique verification record ID")
    evidence_id: str = Field(..., description="Target evidence artifact ID")
    case_id: str = Field(..., description="Associated civic case ID")
    deterministic_validation_result: DeterministicValidationStatus
    verification_status: VerificationOutcome
    verification_reason: str = Field(..., description="Explainable advisory assessment summary")
    assessment_provider: str = Field(..., description="Provider identifier (e.g., ollama, mock, deterministic-fallback)")
    assessment_model: Optional[str] = Field(default=None, description="Model identifier if AI assessment executed")
    assessment_timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    ai_available: bool = Field(default=False, description="Whether advisory AI provider was reachable")
    ai_confidence: Optional[float] = Field(default=None, description="Advisory confidence score if genuinely produced")
    detected_characteristics: List[str] = Field(default_factory=list, description="Extracted features or keywords")
    relevance: Optional[EvidenceRelevanceOutcome] = Field(default=None, description="Visual relevance outcome: RELATED, NOT_RELATED, or UNCERTAIN")
    relevance_reason: Optional[str] = Field(default=None, description="Visual relevance explanation")
    relevance_detected_features: List[str] = Field(default_factory=list, description="Visual features detected in image")
    relevance_confidence: Optional[float] = Field(default=None, description="Advisory relevance confidence")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class EvidenceRecord(BaseModel):
    """Authoritative server-side trusted record for stored evidence.

    Client-supplied principal, role, department, verification status, and AI results
    are NEVER trusted; all fields are derived and validated server-side.
    """

    evidence_id: str = Field(..., description="Server-generated unique evidence ID")
    case_id: str = Field(..., description="Associated case ID")
    uploaded_by_principal: str = Field(..., description="Authenticated principal ID")
    uploader_role: str = Field(..., description="Authenticated principal role")
    evidence_type: EvidenceType = Field(..., description="CASE_EVIDENCE or RESOLUTION_EVIDENCE")
    filename: str = Field(..., description="Sanitized original filename")
    content_type: str = Field(..., description="Validated MIME type")
    size_bytes: int = Field(..., description="File size in bytes")
    storage_key: str = Field(..., description="Internal object storage path")
    s3_uri: Optional[str] = Field(default=None, description="Internal S3 URI")
    sha256: str = Field(..., description="Server-computed SHA-256 cryptographic hash")
    validation_status: DeterministicValidationStatus = Field(..., description="Deterministic validation status")
    verification_status: VerificationOutcome = Field(..., description="Canonical verification outcome")
    verification_reason: str = Field(..., description="Concise explainable assessment reasoning")
    ai_assessment: Optional[str] = Field(default=None, description="Advisory AI assessment explanation")
    ai_confidence: Optional[float] = Field(default=None, description="Advisory AI confidence score")
    relevance: Optional[EvidenceRelevanceOutcome] = Field(default=None, description="Visual relevance outcome: RELATED, NOT_RELATED, or UNCERTAIN")
    relevance_reason: Optional[str] = Field(default=None, description="Visual relevance explanation")
    relevance_detected_features: List[str] = Field(default_factory=list, description="Visual features detected in image")
    relevance_confidence: Optional[float] = Field(default=None, description="Advisory relevance confidence")
    resolution_attempt: Optional[str] = Field(default=None, description="Resolution attempt identifier for resolution evidence")
    resolution_message: Optional[str] = Field(default=None, description="Authoritative resolution message entered during evidence upload")
    submitting_authority_principal: Optional[str] = Field(default=None, description="Submitting officer principal ID")
    authority_department: Optional[str] = Field(default=None, description="Submitting officer assigned department")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    verified_at: Optional[datetime] = Field(default=None)


class EvidenceResponse(BaseModel):
    """Sanitized public/client projection of an evidence record.

    Prevents leaking internal storage keys, raw credentials, or private provider internals.
    """

    evidence_id: str
    case_id: str
    evidence_type: EvidenceType
    filename: str
    content_type: str
    size_bytes: int
    sha256: str
    validation_status: DeterministicValidationStatus
    verification_status: VerificationOutcome
    verification_reason: str
    ai_confidence: Optional[float] = None
    relevance: Optional[EvidenceRelevanceOutcome] = None
    relevance_reason: Optional[str] = None
    relevance_detected_features: List[str] = Field(default_factory=list)
    relevance_confidence: Optional[float] = None
    resolution_attempt: Optional[str] = None
    resolution_message: Optional[str] = None
    object_key: Optional[str] = None
    s3_uri: Optional[str] = None
    is_advisory: bool = True
    created_at: datetime
    verified_at: Optional[datetime] = None
