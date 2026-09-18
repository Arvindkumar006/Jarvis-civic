"""Unit Tests for DynamoDB Repository and LocalStack Initialization.

Phase 4 Test Suite:
Verifies DynamoDBCaseRepository operations using mocked DynamoDB Table
and validates idempotent LocalStack resource initialization.
"""

from unittest.mock import MagicMock, patch
from botocore.exceptions import ClientError
import pytest

from app.models.enums import CaseStatus, ControlledDepartment
from app.models.security import CivicCaseCreateRequest
from app.services.persistence.dynamodb_repository import DynamoDBCaseRepository
from app.services.persistence.localstack_init import init_localstack_resources


@pytest.fixture
def mock_dynamodb_repo():
    repo = DynamoDBCaseRepository()
    mock_table = MagicMock()
    repo.table = mock_table
    return repo, mock_table


def test_dynamodb_create_case_calls_put_item_with_condition(mock_dynamodb_repo):
    """Verify create_case calls put_item with attribute_not_exists condition."""
    repo, mock_table = mock_dynamodb_repo

    req = CivicCaseCreateRequest(
        description="Broken streetlight on Main Road",
        location="Anna Nagar",
        department=ControlledDepartment.MUNICIPAL_CORPORATION,
        pincode="600040",
        is_public=True,
    )
    record = repo.create_case(req, owner_id="citizen-1", case_id="NS-CHN-2026-9E4B")

    assert record.case_id == "NS-CHN-2026-9E4B"
    assert mock_table.put_item.called

    kwargs = mock_table.put_item.call_args[1]
    assert kwargs["ConditionExpression"] == "attribute_not_exists(case_id)"
    item = kwargs["Item"]
    assert item["case_id"] == "NS-CHN-2026-9E4B"
    assert item["pincode"] == "600040"
    assert item["status"] == "DOCKET_CREATED"


def test_dynamodb_get_case_returns_record_or_none(mock_dynamodb_repo):
    """Verify get_case returns parsed record when found, and None when not found."""
    repo, mock_table = mock_dynamodb_repo

    # Case 1: Item found
    mock_table.get_item.return_value = {
        "Item": {
            "case_id": "NS-CHN-2026-9E4B",
            "owner_id": "citizen-1",
            "department": "PWD_ROADS",
            "status": "DOCKET_CREATED",
            "description": "Deep pothole",
            "location": "Anna Nagar",
            "pincode": "600040",
            "is_public": True,
            "resolution_notes": [],
            "evidence_uris": [],
            "created_at": "2026-09-17T10:00:00+00:00",
            "updated_at": "2026-09-17T10:00:00+00:00",
        }
    }
    found = repo.get_case("NS-CHN-2026-9E4B")
    assert found is not None
    assert found.case_id == "NS-CHN-2026-9E4B"
    assert found.pincode == "600040"
    assert found.department == "PWD_ROADS"

    # Case 2: Item not found
    mock_table.get_item.return_value = {}
    missing = repo.get_case("NS-MISSING-001")
    assert missing is None


def test_dynamodb_update_status_calls_put_item_with_exists_condition(mock_dynamodb_repo):
    """Verify update_case_status checks existence and persists new status."""
    repo, mock_table = mock_dynamodb_repo

    # Mock get_case returning existing record
    mock_table.get_item.return_value = {
        "Item": {
            "case_id": "NS-CHN-2026-9E4B",
            "owner_id": "citizen-1",
            "department": "PWD_ROADS",
            "status": "DOCKET_CREATED",
            "description": "Deep pothole",
            "location": "Anna Nagar",
            "pincode": "600040",
            "is_public": True,
            "resolution_notes": [],
            "evidence_uris": [],
            "created_at": "2026-09-17T10:00:00+00:00",
            "updated_at": "2026-09-17T10:00:00+00:00",
        }
    }

    updated = repo.update_case_status("NS-CHN-2026-9E4B", CaseStatus.UNDER_REVIEW, note="Under inspection")
    assert updated is not None
    assert updated.status == CaseStatus.UNDER_REVIEW
    assert "Under inspection" in updated.resolution_notes

    kwargs = mock_table.put_item.call_args[1]
    assert kwargs["ConditionExpression"] == "attribute_exists(case_id)"
    assert kwargs["Item"]["status"] == "UNDER_REVIEW"


def test_init_localstack_resources_idempotent():
    """Verify init_localstack_resources checks list_tables and list_buckets and is idempotent."""
    with patch("boto3.client") as mock_boto_client:
        mock_client = MagicMock()
        mock_boto_client.return_value = mock_client

        # Simulate tables and buckets already existing
        mock_client.list_tables.return_value = {"TableNames": ["JarvisCivicCases", "JarvisCivicAudit"]}
        mock_client.list_buckets.return_value = {"Buckets": [{"Name": "jarvis-civic-evidence"}]}

        res = init_localstack_resources()
        assert res is True
        # create_table and create_bucket should NOT be called since they already exist
        assert not mock_client.create_table.called
        assert not mock_client.create_bucket.called

