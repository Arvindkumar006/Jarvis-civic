"""Unit Tests for Persistence Serialization and Local Case Repository.

Phase 4 Test Suite:
Verifies serialization invariants (string PIN preservation, enum mappings,
UTC timestamps) and LocalCaseRepository contract operations.
"""

from datetime import datetime, timezone
import pytest

from app.models.enums import CaseStatus, ControlledDepartment
from app.models.security import CivicCaseCreateRequest, CivicCaseRecord
from app.services.persistence.local_repository import LocalCaseRepository
from app.services.persistence.serialization import (
    case_record_to_dynamodb,
    dynamodb_to_case_record,
)


def test_serialization_pincode_leading_zero_preserved():
    """CRITICAL SECURITY/DATA INVARIANT: PIN code '012345' must NEVER become integer 12345."""
    record = CivicCaseRecord(
        case_id="NS-CHN-2026-9E4B",
        owner_id="citizen-101",
        department="DRAINAGE_STORMWATER",
        status=CaseStatus.DOCKET_CREATED,
        description="Drain clogged with mud",
        location="Anna Salai",
        pincode="012345",  # Leading zero
        is_public=True,
    )

    dynamo_item = case_record_to_dynamodb(record)
    assert dynamo_item["pincode"] == "012345"
    assert isinstance(dynamo_item["pincode"], str)

    restored = dynamodb_to_case_record(dynamo_item)
    assert restored.pincode == "012345"
    assert isinstance(restored.pincode, str)


def test_serialization_round_trip_complete():
    """Verify all fields serialize and deserialize losslessly."""
    created = datetime(2026, 9, 17, 10, 0, 0, tzinfo=timezone.utc)
    updated = datetime(2026, 9, 17, 10, 30, 0, tzinfo=timezone.utc)

    record = CivicCaseRecord(
        case_id="NS-BLR-2026-A1B2",
        owner_id="citizen-202",
        department="WASTE_MANAGEMENT",
        status=CaseStatus.UNDER_REVIEW,
        description="Overflowing dumpster on 12th Cross",
        location="Indiranagar",
        landmark="Behind Metro Station",
        pincode="560038",
        urgency="MEDIUM",
        urgency_rationale="Waste accumulation attracting pests",
        session_id="session-xyz-789",
        is_public=True,
        resolution_notes=["Inspection assigned to Ward 85"],
        evidence_uris=["s3://jarvis-civic-evidence/cases/NS-BLR-2026-A1B2/evidence/ev1/photo.jpg"],
        created_at=created,
        updated_at=updated,
    )

    item = case_record_to_dynamodb(record)
    assert item["status"] == "UNDER_REVIEW"
    assert item["department"] == "WASTE_MANAGEMENT"
    assert item["is_public"] is True
    assert len(item["evidence_uris"]) == 1
    assert len(item["resolution_notes"]) == 1

    restored = dynamodb_to_case_record(item)
    assert restored.case_id == record.case_id
    assert restored.owner_id == record.owner_id
    assert restored.status == CaseStatus.UNDER_REVIEW
    assert restored.landmark == "Behind Metro Station"
    assert restored.urgency == "MEDIUM"
    assert restored.session_id == "session-xyz-789"
    assert restored.evidence_uris == record.evidence_uris
    assert restored.resolution_notes == record.resolution_notes
    assert restored.created_at == created
    assert restored.updated_at == updated


def test_local_case_repository_operations():
    """Verify LocalCaseRepository implements the full CaseRepository contract."""
    repo = LocalCaseRepository()
    repo.clear()

    # 1. Create case
    req = CivicCaseCreateRequest(
        description="Pothole on 100 Feet Road",
        location="Indiranagar",
        department=ControlledDepartment.PWD_ROADS,
        pincode="560038",
        is_public=True,
    )
    created = repo.create_case(req, owner_id="citizen-arun")
    cid = created.case_id
    assert cid.startswith("NS-")
    assert created.status == CaseStatus.DOCKET_CREATED

    # 2. Get case
    fetched = repo.get_case(cid)
    assert fetched is not None
    assert fetched.owner_id == "citizen-arun"
    assert fetched.description == "Pothole on 100 Feet Road"

    # 3. Update case details
    updated = repo.update_case(cid, description="Deep dangerous pothole", location="Indiranagar 100ft Rd")
    assert updated is not None
    assert updated.description == "Deep dangerous pothole"
    assert updated.location == "Indiranagar 100ft Rd"

    # 4. Update status
    status_updated = repo.update_case_status(cid, CaseStatus.UNDER_REVIEW, note="Engineer dispatched")
    assert status_updated is not None
    assert status_updated.status == CaseStatus.UNDER_REVIEW
    assert "Engineer dispatched" in status_updated.resolution_notes

    # 5. Add resolution note
    note_updated = repo.add_resolution_note(cid, "Patchwork completed")
    assert note_updated is not None
    assert len(note_updated.resolution_notes) == 2
    assert "Patchwork completed" in note_updated.resolution_notes

    # 6. Add evidence URI
    ev_updated = repo.add_evidence_uri(cid, "s3://jarvis-civic-evidence/cases/test/ev.jpg")
    assert ev_updated is not None
    assert "s3://jarvis-civic-evidence/cases/test/ev.jpg" in ev_updated.evidence_uris

    # 7. Non-existent case
    assert repo.get_case("NS-NON-EXISTENT") is None
    assert repo.update_case("NS-NON-EXISTENT", description="xyz") is None
    assert repo.update_case_status("NS-NON-EXISTENT", CaseStatus.RESOLVED) is None
