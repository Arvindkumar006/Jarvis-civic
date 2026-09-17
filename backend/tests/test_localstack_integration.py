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
