"""Civic Case Store and Service Facade for JARVIS Civic.

Phase 4: Bridges API routes to the active persistence repository (LocalStack
DynamoDB or Local in-memory fallback), preserving full Phase 3 backward compatibility.
"""

from typing import Optional
from app.models.enums import CaseStatus
from app.models.security import CivicCaseCreateRequest, CivicCaseRecord
from app.services.persistence.factory import get_repositories
from app.services.persistence.interface import CaseRepository, EvidenceRepository


class CaseServiceFacade:
    """Delegates civic case operations to the configured persistence repository."""

    @property
    def _case_repo(self) -> CaseRepository:
        repo, _ = get_repositories()
        return repo

    @property
    def evidence_repo(self) -> EvidenceRepository:
        _, ev_repo = get_repositories()
        return ev_repo

    def create_case(
        self,
        request: CivicCaseCreateRequest,
        owner_id: str,
        case_id: Optional[str] = None,
    ) -> CivicCaseRecord:
        """Create and persist a new civic case record."""
        return self._case_repo.create_case(request, owner_id=owner_id, case_id=case_id)

    def get_case(self, case_id: str) -> Optional[CivicCaseRecord]:
        """Fetch case by case_id."""
        return self._case_repo.get_case(case_id)

    def update_case(
        self,
        case_id: str,
        description: Optional[str] = None,
        location: Optional[str] = None,
        pincode: Optional[str] = None,
    ) -> Optional[CivicCaseRecord]:
        """Update case details."""
        return self._case_repo.update_case(
            case_id=case_id,
            description=description,
            location=location,
            pincode=pincode,
        )

    def update_case_status(
        self,
        case_id: str,
        new_status: CaseStatus,
        note: Optional[str] = None,
    ) -> Optional[CivicCaseRecord]:
        """Update case lifecycle status."""
        return self._case_repo.update_case_status(case_id, new_status=new_status, note=note)

    def add_resolution_note(self, case_id: str, note: str) -> Optional[CivicCaseRecord]:
        """Append an authority resolution note."""
        return self._case_repo.add_resolution_note(case_id, note=note)

    def add_evidence_uri(self, case_id: str, uri: str) -> Optional[CivicCaseRecord]:
        """Attach an evidence storage URI to the case."""
        return self._case_repo.add_evidence_uri(case_id, uri=uri)

    def clear(self) -> None:
        """Clear cases (useful for test fixtures)."""
        self._case_repo.clear()


# Global facade instance preserving existing Phase 3 import path
case_store = CaseServiceFacade()
