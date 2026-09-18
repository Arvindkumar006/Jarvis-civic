"""Abstract Persistence Interfaces for JARVIS Civic.

Phase 4: Decouples business logic and Cedar enforcement from underlying
storage (LocalStack DynamoDB, LocalStack S3, or In-Memory Local Fallback).
"""

from abc import ABC, abstractmethod
from typing import Any, List, Optional
from app.models.enums import CaseStatus
from app.models.security import (
    CaseHistoryItem,
    CivicCaseCreateRequest,
    CivicCaseRecord,
    EvidenceMetadata,
)


class CaseRepository(ABC):
    """Abstract repository contract for CivicCase persistence."""

    @abstractmethod
    def create_case(
        self,
        request: CivicCaseCreateRequest,
        owner_id: str,
        case_id: Optional[str] = None,
    ) -> CivicCaseRecord:
        """Persist a new civic case record."""
        pass

    @abstractmethod
    def get_case(self, case_id: str) -> Optional[CivicCaseRecord]:
        """Retrieve a civic case by unique case_id."""
        pass

    @abstractmethod
    def update_case(
        self,
        case_id: str,
        description: Optional[str] = None,
        location: Optional[str] = None,
        pincode: Optional[str] = None,
    ) -> Optional[CivicCaseRecord]:
        """Update problem statement or physical attributes of an existing case."""
        pass

    @abstractmethod
    def update_case_status(
        self,
        case_id: str,
        new_status: CaseStatus,
        note: Optional[str] = None,
        actor_label: Optional[str] = None,
        expected_current_status: Optional[CaseStatus] = None,
    ) -> Optional[CivicCaseRecord]:
        """Update case lifecycle status, append transition note, and enforce concurrency state."""
        pass

    @abstractmethod
    def add_resolution_note(self, case_id: str, note: str) -> Optional[CivicCaseRecord]:
        """Append an authority resolution note."""
        pass

    @abstractmethod
    def add_evidence_uri(self, case_id: str, uri: str) -> Optional[CivicCaseRecord]:
        """Associate an uploaded evidence storage URI with the case."""
        pass

    @abstractmethod
    def get_case_history(self, case_id: str) -> List[CaseHistoryItem]:
        """Retrieve sanitized lifecycle history for the case."""
        pass

    @abstractmethod
    def clear(self) -> None:
        """Clear all stored cases (primarily for test fixture isolation)."""
        pass


class EvidenceRepository(ABC):
    """Abstract repository contract for Evidence file storage."""

    @abstractmethod
    def upload_evidence(
        self,
        case_id: str,
        file_bytes: bytes,
        filename: str,
        content_type: str,
    ) -> EvidenceMetadata:
        """Validate and upload evidence file bytes, returning server-generated metadata."""
        pass

    @abstractmethod
    def get_evidence_metadata(self, case_id: str, evidence_id: str) -> Optional[EvidenceMetadata]:
        """Fetch metadata for an evidence item."""
        pass


class AuditRepository(ABC):
    """Abstract repository contract for append-only audit persistence."""

    @abstractmethod
    def record_event(self, event: Any) -> None:
        """Append an audit event to persistent storage."""
        pass

    @abstractmethod
    def get_events(
        self,
        department: Optional[str] = None,
        limit: int = 100,
    ) -> List[Any]:
        """Retrieve audit events, optionally filtered by department scope."""
        pass

    @abstractmethod
    def get_events_for_case(
        self,
        case_id: str,
        department: Optional[str] = None,
        limit: int = 100,
    ) -> List[Any]:
        """Retrieve audit events for a specific case ID."""
        pass

    @abstractmethod
    def clear(self) -> None:
        """Clear all stored audit events (primarily for test fixture isolation)."""
        pass

