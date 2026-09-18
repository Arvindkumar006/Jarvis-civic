"""Live LocalStack Integration Tests for DynamoDB and S3.

Phase 4 Integration Suite:
Executes real AWS SDK calls against a local LocalStack instance if reachable.
Skips explicitly with a clear message if LocalStack is not currently running.
"""

import urllib.request
import pytest

from app.config.settings import settings
from app.models.enums import CaseStatus, ControlledDepartment
from app.models.security import CivicCaseCreateRequest
from app.services.persistence.dynamodb_repository import DynamoDBCaseRepository
from app.services.persistence.s3_evidence_repository import S3EvidenceRepository
from app.services.persistence.localstack_init import init_localstack_resources


def is_localstack_running() -> bool:
    """Check if LocalStack is responding on the configured endpoint."""
    try:
        health_url = f"{settings.LOCALSTACK_ENDPOINT_URL}/_localstack/health"
        with urllib.request.urlopen(health_url, timeout=0.5) as response:
            return response.status == 200
    except Exception:
        return False


@pytest.fixture(scope="module")
def require_localstack():
    """Skip test module if LocalStack is not active on http://localhost:4566."""
    if not is_localstack_running():
        pytest.skip(
            f"LocalStack is not reachable at '{settings.LOCALSTACK_ENDPOINT_URL}'. "
            "Skipping live LocalStack integration tests (Unit tests use local repository fallback)."
        )


def test_live_localstack_resource_initialization(require_localstack):
    """Verify idempotent creation of DynamoDB table and S3 bucket on live LocalStack."""
    assert init_localstack_resources() is True


def test_live_localstack_dynamodb_crud(require_localstack):
    """Verify real DynamoDB operations: put_item, get_item, conditional update."""
    repo = DynamoDBCaseRepository()
    test_id = "NS-TST-2026-LIVE"
    repo.clear()

    # 1. Create
    req = CivicCaseCreateRequest(
        description="Live LocalStack integration test case",
        location="Indiranagar 100ft Rd",
        department=ControlledDepartment.PWD_ROADS,
        pincode="560038",
        is_public=True,
    )
    created = repo.create_case(req, owner_id="cit-live-1", case_id=test_id)
    assert created.case_id == test_id

    # 2. Read
    fetched = repo.get_case(test_id)
    assert fetched is not None
    assert fetched.case_id == test_id
    assert fetched.pincode == "560038"
    assert fetched.status == CaseStatus.DOCKET_CREATED

    # 3. Update status
    updated = repo.update_case_status(test_id, CaseStatus.UNDER_REVIEW, note="Live update note")
    assert updated is not None
    assert updated.status == CaseStatus.UNDER_REVIEW

    # Verify persisted in DynamoDB
    refetched = repo.get_case(test_id)
    assert refetched.status == CaseStatus.UNDER_REVIEW
    assert "Live update note" in refetched.resolution_notes


def test_live_localstack_s3_upload(require_localstack):
    """Verify real S3 put_object and head_object on live LocalStack."""
    s3_repo = S3EvidenceRepository()
    test_case_id = "NS-TST-2026-LIVE"
    payload = b"Sample binary JPEG payload for live S3 integration test"

    meta = s3_repo.upload_evidence(
        case_id=test_case_id,
        file_bytes=payload,
        filename="live_pothole.jpg",
        content_type="image/jpeg",
    )
    assert meta.case_id == test_case_id
    assert meta.filename == "live_pothole.jpg"
    assert meta.size_bytes == len(payload)

    # Fetch metadata via head_object
    fetched_meta = s3_repo.get_evidence_metadata(test_case_id, meta.evidence_id)
    assert fetched_meta is not None
    assert fetched_meta.evidence_id == meta.evidence_id


def test_live_localstack_dynamodb_audit_persistence_and_gsi_query(require_localstack):
    """Verify live audit event persistence into JarvisCivicAudit and GSI querying."""
    from datetime import datetime, timezone
    from app.security.audit import AuditEvent
    from app.services.persistence.dynamodb_repository import DynamoDBAuditRepository

    audit_repo = DynamoDBAuditRepository()
    test_case_id = "NS-TST-2026-AUDIT-LIVE"

    evt1 = AuditEvent(
        event_id="evt-live-001",
        timestamp=datetime.now(timezone.utc),
        decision="ALLOW",
        principal_id="cit-live-1",
        principal_role="CITIZEN",
        action="create_case",
        resource_id=test_case_id,
        case_id=test_case_id,
        event_type="DOCKET_CREATED",
        previous_status="NONE",
        new_status="DOCKET_CREATED",
        outcome="SUCCESS",
        metadata={"location": "Indiranagar 100ft Rd"},
    )
    evt2 = AuditEvent(
        event_id="evt-live-002",
        timestamp=datetime.now(timezone.utc),
        decision="ALLOW",
        principal_id="officer-pwd-1",
        principal_role="AUTHORITY_OFFICER",
        principal_department="PWD_ROADS",
        action="update_case_status",
        resource_id=test_case_id,
        case_id=test_case_id,
        event_type="STATUS_TRANSITION",
        previous_status="DOCKET_CREATED",
        new_status="ROUTING_PREPARED",
        outcome="SUCCESS",
        metadata={"note": "Assigned to PWD team for road survey"},
    )

    # 1. Record events into live LocalStack DynamoDB table
    audit_repo.record_event(evt1)
    audit_repo.record_event(evt2)

    # 2. Query via GSI (CaseIndex)
    events = audit_repo.get_events_for_case(test_case_id)
    assert len(events) >= 2
    event_ids = [e.event_id for e in events]
    assert "evt-live-001" in event_ids
    assert "evt-live-002" in event_ids

    # 3. Verify event attributes
    t_evt = next(e for e in events if e.event_id == "evt-live-002")
    assert t_evt.case_id == test_case_id
    assert t_evt.event_type == "STATUS_TRANSITION"
    assert t_evt.previous_status == "DOCKET_CREATED"
    assert t_evt.new_status == "ROUTING_PREPARED"
    assert t_evt.principal_id == "officer-pwd-1"
    assert t_evt.principal_role == "AUTHORITY_OFFICER"
    assert t_evt.outcome == "SUCCESS"
    assert t_evt.metadata.get("note") == "Assigned to PWD team for road survey"

    # 4. Recreate repository instance and verify data persists in LocalStack (not just in-memory)
    fresh_repo = DynamoDBAuditRepository()
    reloaded_events = fresh_repo.get_events_for_case(test_case_id)
    assert len(reloaded_events) >= 2
    assert any(e.event_id == "evt-live-002" for e in reloaded_events)


def test_live_localstack_end_to_end_lifecycle_persistence(require_localstack):
    """Verify live case creation, status transition, and audit trail across re-instantiated repositories."""
    from datetime import datetime, timezone
    from app.security.audit import AuditEvent
    from app.services.persistence.dynamodb_repository import (
        DynamoDBCaseRepository,
        DynamoDBAuditRepository,
    )

    case_repo = DynamoDBCaseRepository()
    audit_repo = DynamoDBAuditRepository()
    case_id = "NS-E2E-2026-LIVE"

    # Step 1: Create case in live DynamoDB (DOCKET_CREATED)
    req = CivicCaseCreateRequest(
        description="Dangerous waterlogging on bypass",
        location="Velachery Main Rd",
        department=ControlledDepartment.DRAINAGE_STORMWATER,
        pincode="600042",
        is_public=True,
    )
    created = case_repo.create_case(req, owner_id="cit-velachery", case_id=case_id)
    assert created.status == CaseStatus.DOCKET_CREATED

    audit_repo.record_event(
        AuditEvent(
            event_id=f"evt-{case_id}-create",
            timestamp=datetime.now(timezone.utc),
            decision="ALLOW",
            principal_id="cit-velachery",
            principal_role="CITIZEN",
            action="create_case",
            resource_id=case_id,
            case_id=case_id,
            event_type="DOCKET_CREATED",
            previous_status="NONE",
            new_status="DOCKET_CREATED",
            outcome="SUCCESS",
        )
    )

    # Step 2: Transition case to ROUTING_PREPARED
    updated = case_repo.update_case_status(
        case_id=case_id,
        new_status=CaseStatus.ROUTING_PREPARED,
        note="Drainage crew triage confirmed",
        actor_label="AUTHORITY_OFFICER",
    )
    assert updated.status == CaseStatus.ROUTING_PREPARED

    audit_repo.record_event(
        AuditEvent(
            event_id=f"evt-{case_id}-transit",
            timestamp=datetime.now(timezone.utc),
            decision="ALLOW",
            principal_id="officer-drainage-1",
            principal_role="AUTHORITY_OFFICER",
            principal_department="DRAINAGE_STORMWATER",
            action="update_case_status",
            resource_id=case_id,
            case_id=case_id,
            event_type="STATUS_TRANSITION",
            previous_status="DOCKET_CREATED",
            new_status="ROUTING_PREPARED",
            outcome="SUCCESS",
            metadata={"note": "Drainage crew triage confirmed"},
        )
    )

    # Step 3: Recreate both repositories from scratch
    fresh_case_repo = DynamoDBCaseRepository()
    fresh_audit_repo = DynamoDBAuditRepository()

    persisted_case = fresh_case_repo.get_case(case_id)
    assert persisted_case is not None
    assert persisted_case.status == CaseStatus.ROUTING_PREPARED
    assert "Drainage crew triage confirmed" in persisted_case.resolution_notes

    persisted_audits = fresh_audit_repo.get_events_for_case(case_id)
    assert len(persisted_audits) == 2
    assert persisted_audits[0].event_type == "DOCKET_CREATED"
    assert persisted_audits[1].event_type == "STATUS_TRANSITION"
    assert persisted_audits[1].previous_status == "DOCKET_CREATED"
    assert persisted_audits[1].new_status == "ROUTING_PREPARED"

