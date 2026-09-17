"""In-Memory Civic Case Store for Phase 3 Authorization Demonstrations.

Stores active civic grievance records in memory for PEP demonstration.
NOTE: Persistent database storage is deferred to Phase 4.
"""

import threading
from typing import Dict, List, Optional
from datetime import datetime, timezone

from app.models.common import generate_case_id
from app.models.enums import CaseStatus, ControlledDepartment
from app.models.security import CivicCaseCreateRequest, CivicCaseRecord


class InMemoryCaseStore:
    """Thread-safe in-memory case repository."""

    def __init__(self):
        self._cases: Dict[str, CivicCaseRecord] = {}
        self._lock = threading.Lock()

    def create_case(
        self,
        request: CivicCaseCreateRequest,
        owner_id: str,
        case_id: Optional[str] = None,
    ) -> CivicCaseRecord:
        """Create and store a new civic grievance case record."""
        with self._lock:
            cid = case_id or generate_case_id()
            record = CivicCaseRecord(
                case_id=cid,
                owner_id=owner_id,
                department=request.department.value if isinstance(request.department, ControlledDepartment) else str(request.department),
                status=CaseStatus.DOCKET_CREATED,
                description=request.description,
                location=request.location,
                pincode=request.pincode,
                is_public=request.is_public,
                resolution_notes=[],
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
            self._cases[cid] = record
            return record

    def get_case(self, case_id: str) -> Optional[CivicCaseRecord]:
        """Fetch case by case_id."""
        with self._lock:
            return self._cases.get(case_id)

    def update_case_status(
        self,
        case_id: str,
        new_status: CaseStatus,
        note: Optional[str] = None,
    ) -> Optional[CivicCaseRecord]:
        """Update case status and append transition note."""
        with self._lock:
            record = self._cases.get(case_id)
            if not record:
                return None
            record.status = new_status
            record.updated_at = datetime.now(timezone.utc)
            if note:
                record.resolution_notes.append(note)
            return record

    def add_resolution_note(self, case_id: str, note: str) -> Optional[CivicCaseRecord]:
        """Append an authority resolution note."""
        with self._lock:
            record = self._cases.get(case_id)
            if not record:
                return None
            record.resolution_notes.append(note)
            record.updated_at = datetime.now(timezone.utc)
            return record

    def clear(self) -> None:
        """Clear all cases (useful for test isolation)."""
        with self._lock:
            self._cases.clear()


# Global singleton instance
case_store = InMemoryCaseStore()
