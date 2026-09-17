"""DynamoDB Civic Case Repository for JARVIS Civic (LocalStack).

Phase 4: Provides production-structured DynamoDB persistence targeting
local LocalStack endpoint (http://localhost:4566) with zero cloud billing.
"""

from datetime import datetime, timezone
import logging
from typing import Any, Dict, Optional
import boto3
from botocore.exceptions import ClientError

from app.config.settings import settings
from app.models.common import generate_case_id
from app.models.enums import CaseStatus, ControlledDepartment
from app.models.security import CivicCaseCreateRequest, CivicCaseRecord
from app.services.persistence.interface import CaseRepository
from app.services.persistence.serialization import (
    case_record_to_dynamodb,
    dynamodb_to_case_record,
)

logger = logging.getLogger("jarvis.persistence.dynamodb")


class DynamoDBCaseRepository(CaseRepository):
    """LocalStack DynamoDB implementation of CaseRepository."""

    def __init__(
        self,
        endpoint_url: Optional[str] = None,
        table_name: Optional[str] = None,
        region_name: Optional[str] = None,
    ):
        self.endpoint_url = endpoint_url or settings.LOCALSTACK_ENDPOINT_URL
        self.table_name = table_name or settings.DYNAMODB_TABLE_NAME
        self.region_name = region_name or settings.AWS_REGION

        self.dynamodb = boto3.resource(
            "dynamodb",
            endpoint_url=self.endpoint_url,
            region_name=self.region_name,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        )
        self.table = self.dynamodb.Table(self.table_name)

    def create_case(
        self,
        request: CivicCaseCreateRequest,
        owner_id: str,
        case_id: Optional[str] = None,
    ) -> CivicCaseRecord:
        cid = case_id or generate_case_id()
        now = datetime.now(timezone.utc)

        record = CivicCaseRecord(
            case_id=cid,
            owner_id=owner_id,
            department=(
                request.department.value
                if isinstance(request.department, ControlledDepartment)
                else str(request.department)
            ),
            status=CaseStatus.DOCKET_CREATED,
            description=request.description,
            location=request.location,
            pincode=request.pincode,
            is_public=request.is_public,
            resolution_notes=[],
            evidence_uris=[],
            created_at=now,
            updated_at=now,
        )

        item = case_record_to_dynamodb(record)
        try:
            self.table.put_item(
                Item=item,
                ConditionExpression="attribute_not_exists(case_id)",
            )
            logger.info("DynamoDB: Created civic case '%s'", cid)
            return record
        except ClientError as exc:
            logger.error("DynamoDB put_item failed for case '%s': %s", cid, exc)
            raise

    def get_case(self, case_id: str) -> Optional[CivicCaseRecord]:
        try:
            response = self.table.get_item(Key={"case_id": case_id})
            item = response.get("Item")
            if not item:
                return None
            return dynamodb_to_case_record(item)
        except ClientError as exc:
            logger.error("DynamoDB get_item failed for case '%s': %s", case_id, exc)
            raise

    def update_case(
        self,
        case_id: str,
        description: Optional[str] = None,
        location: Optional[str] = None,
        pincode: Optional[str] = None,
    ) -> Optional[CivicCaseRecord]:
        record = self.get_case(case_id)
        if not record:
            return None

        if description is not None:
            record.description = description
        if location is not None:
            record.location = location
        if pincode is not None:
            record.pincode = pincode
        record.updated_at = datetime.now(timezone.utc)

        item = case_record_to_dynamodb(record)
        try:
            self.table.put_item(
                Item=item,
                ConditionExpression="attribute_exists(case_id)",
            )
            return record
        except ClientError as exc:
            logger.error("DynamoDB update_case failed for '%s': %s", case_id, exc)
            raise

    def update_case_status(
        self,
        case_id: str,
        new_status: CaseStatus,
        note: Optional[str] = None,
    ) -> Optional[CivicCaseRecord]:
        record = self.get_case(case_id)
        if not record:
            return None

        record.status = new_status
        record.updated_at = datetime.now(timezone.utc)
        if note:
            record.resolution_notes.append(note)

        item = case_record_to_dynamodb(record)
        try:
            self.table.put_item(
                Item=item,
                ConditionExpression="attribute_exists(case_id)",
            )
            return record
        except ClientError as exc:
            logger.error("DynamoDB update_case_status failed for '%s': %s", case_id, exc)
            raise

    def add_resolution_note(self, case_id: str, note: str) -> Optional[CivicCaseRecord]:
        record = self.get_case(case_id)
        if not record:
            return None

        record.resolution_notes.append(note)
        record.updated_at = datetime.now(timezone.utc)

        item = case_record_to_dynamodb(record)
        try:
            self.table.put_item(
                Item=item,
                ConditionExpression="attribute_exists(case_id)",
            )
            return record
        except ClientError as exc:
            logger.error("DynamoDB add_resolution_note failed for '%s': %s", case_id, exc)
            raise

    def add_evidence_uri(self, case_id: str, uri: str) -> Optional[CivicCaseRecord]:
        record = self.get_case(case_id)
        if not record:
            return None

        if uri not in record.evidence_uris:
            record.evidence_uris.append(uri)
        record.updated_at = datetime.now(timezone.utc)

        item = case_record_to_dynamodb(record)
        try:
            self.table.put_item(
                Item=item,
                ConditionExpression="attribute_exists(case_id)",
            )
            return record
        except ClientError as exc:
            logger.error("DynamoDB add_evidence_uri failed for '%s': %s", case_id, exc)
            raise

    def clear(self) -> None:
        """Scan and clear all items from the table."""
        try:
            scan = self.table.scan()
            with self.table.batch_writer() as batch:
                for item in scan.get("Items", []):
                    batch.delete_item(Key={"case_id": item["case_id"]})
        except Exception as exc:
            logger.warning("Failed to clear DynamoDB table: %s", exc)
