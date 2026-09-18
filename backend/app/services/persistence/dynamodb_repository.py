"""DynamoDB Civic Case Repository for JARVIS Civic (LocalStack).

Phase 4: Provides production-structured DynamoDB persistence targeting
local LocalStack endpoint (http://localhost:4566) with zero cloud billing.
"""

from datetime import datetime, timezone
import json
import logging
from typing import Any, Dict, List, Optional
import boto3
from botocore.exceptions import ClientError

from app.config.settings import settings
from app.models.common import generate_case_id
from app.models.enums import CaseStatus, ControlledDepartment
from app.models.security import CaseHistoryItem, CivicCaseCreateRequest, CivicCaseRecord
from app.security.audit import AuditEvent
from app.services.persistence.interface import AuditRepository, CaseRepository
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

    def get_case_history(self, case_id: str) -> List[CaseHistoryItem]:
        record = self.get_case(case_id)
        if not record:
            return []
        
        # Build milestones from persistent record state
        items: List[CaseHistoryItem] = [
            CaseHistoryItem(
                status=CaseStatus.DOCKET_CREATED.value,
                label="Docket Created",
                timestamp=record.created_at,
                description="Initial Civic Docket recorded in system",
                actor_role="CITIZEN",
                note="Initial Civic Docket Created",
            )
        ]

        # If current status is beyond created, reflect intermediate and current
        if record.status != CaseStatus.DOCKET_CREATED:
            status_val = record.status.value if isinstance(record.status, CaseStatus) else str(record.status)
            status_title = status_val.replace("_", " ").title()
            items.append(
                CaseHistoryItem(
                    status=status_val,
                    label=status_title,
                    timestamp=record.updated_at,
                    description=f"Case transitioned to {status_title}",
                    actor_role="AUTHORITY_OFFICER",
                    note=record.resolution_notes[-1] if record.resolution_notes else None,
                )
            )

        return items

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
        actor_label: Optional[str] = None,
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

    def add_resolution_note(
        self,
        case_id: str,
        note: str,
        actor_label: Optional[str] = None,
    ) -> Optional[CivicCaseRecord]:
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


class DynamoDBAuditRepository(AuditRepository):
    """LocalStack DynamoDB implementation of AuditRepository targeting JarvisCivicAudit."""

    def __init__(
        self,
        endpoint_url: Optional[str] = None,
        table_name: Optional[str] = None,
        region_name: Optional[str] = None,
    ):
        self.endpoint_url = endpoint_url or settings.LOCALSTACK_ENDPOINT_URL
        self.table_name = table_name or settings.DYNAMODB_AUDIT_TABLE_NAME
        self.region_name = region_name or settings.AWS_REGION

        self.dynamodb = boto3.resource(
            "dynamodb",
            endpoint_url=self.endpoint_url,
            region_name=self.region_name,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        )
        self.table = self.dynamodb.Table(self.table_name)

    def record_event(self, event: AuditEvent) -> AuditEvent:
        item: Dict[str, Any] = {
            "event_id": str(event.event_id),
            "timestamp": event.timestamp.isoformat(),
            "decision": str(event.decision),
            "principal_id": str(event.principal_id),
            "principal_role": str(event.principal_role),
            "action": str(event.action),
            "resource_id": str(event.resource_id),
            "resource_type": getattr(event, "resource_type", "CivicCase"),
        }
        if getattr(event, "reason", None):
            item["reason"] = event.reason
        if getattr(event, "policy_id", None):
            item["policy_id"] = event.policy_id
        if getattr(event, "department", None):
            item["department"] = event.department
        if event.case_id:
            item["case_id"] = str(event.case_id)
        if event.event_type:
            item["event_type"] = str(event.event_type)
        if event.previous_status:
            item["previous_status"] = str(event.previous_status)
        if event.new_status:
            item["new_status"] = str(event.new_status)
        if event.outcome:
            item["outcome"] = str(event.outcome)
        if event.metadata:
            item["metadata"] = event.metadata

        try:
            self.table.put_item(Item=item)
            return event
        except ClientError as exc:
            logger.error("DynamoDB record_event failed for '%s': %s", event.event_id, exc)
            raise

    def get_events(self, limit: int = 100) -> List[AuditEvent]:
        try:
            response = self.table.scan(Limit=limit)
            items = response.get("Items", [])
            events = [self._item_to_audit_event(i) for i in items]
            events.sort(key=lambda e: e.timestamp, reverse=True)
            return events[:limit]
        except ClientError as exc:
            logger.error("DynamoDB get_events scan failed: %s", exc)
            return []

    def get_events_for_case(self, case_id: str) -> List[AuditEvent]:
        try:
            # Try query using GSI CaseIndex if available, otherwise fallback to filter scan
            try:
                response = self.table.query(
                    IndexName="CaseIndex",
                    KeyConditionExpression="case_id = :cid",
                    ExpressionAttributeValues={":cid": case_id},
                )
                items = response.get("Items", [])
            except ClientError:
                # Fallback to scan if index not yet populated
                response = self.table.scan(
                    FilterExpression="case_id = :cid",
                    ExpressionAttributeValues={":cid": case_id},
                )
                items = response.get("Items", [])

            events = [self._item_to_audit_event(i) for i in items]
            events.sort(key=lambda e: e.timestamp)
            return events
        except ClientError as exc:
            logger.error("DynamoDB get_events_for_case failed for '%s': %s", case_id, exc)
            return []

    def _item_to_audit_event(self, item: Dict[str, Any]) -> AuditEvent:
        ts_str = item.get("timestamp")
        try:
            ts = datetime.fromisoformat(ts_str) if ts_str else datetime.now(timezone.utc)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
        except Exception:
            ts = datetime.now(timezone.utc)

        return AuditEvent(
            event_id=item.get("event_id", "evt_unknown"),
            timestamp=ts,
            decision=item.get("decision", "DENY"),
            principal_id=item.get("principal_id", "unknown"),
            principal_role=item.get("principal_role", "PUBLIC"),
            action=item.get("action", "unknown"),
            resource_id=item.get("resource_id", "unknown"),
            diagnostics=item.get("diagnostics", {}),
            case_id=item.get("case_id"),
            event_type=item.get("event_type"),
            previous_status=item.get("previous_status"),
            new_status=item.get("new_status"),
            outcome=item.get("outcome"),
            metadata=item.get("metadata", {}),
        )

    def clear(self) -> None:
        try:
            scan = self.table.scan()
            with self.table.batch_writer() as batch:
                for item in scan.get("Items", []):
                    batch.delete_item(Key={"event_id": item["event_id"]})
        except Exception as exc:
            logger.warning("Failed to clear DynamoDB audit table: %s", exc)
