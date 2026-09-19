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
            latitude=request.latitude,
            longitude=request.longitude,
            location_source=request.location_source,
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

        # Reconstruct durable history from persisted audit events
        from app.services.persistence.factory import get_audit_repository
        audit_repo = get_audit_repository()
        audit_events = audit_repo.get_events_for_case(case_id)

        items: List[CaseHistoryItem] = []
        seen_statuses = set()

        for ev in audit_events:
            ev_type = getattr(ev, "event_type", None) or getattr(ev, "action", None)
            new_st = getattr(ev, "new_status", None)

            if new_st and new_st not in seen_statuses:
                seen_statuses.add(new_st)
                st_title = new_st.replace("_", " ").title()
                items.append(
                    CaseHistoryItem(
                        milestone_id=getattr(ev, "event_id", f"ms-{secrets.token_hex(6)}"),
                        status=new_st,
                        label=st_title,
                        timestamp=getattr(ev, "timestamp", record.created_at),
                        department=record.department,
                        description=(
                            "Initial Civic Docket recorded in system"
                            if new_st == CaseStatus.DOCKET_CREATED.value
                            else f"Case transitioned to {st_title}"
                        ),
                        actor_role=getattr(ev, "principal_role", "CITIZEN"),
                        note=(getattr(ev, "metadata", {}) or {}).get("note") if getattr(ev, "metadata", None) else None,
                    )
                )
            elif ev_type == "RESOLUTION_NOTE_ADDED":
                note_text = (getattr(ev, "metadata", {}) or {}).get("note") if getattr(ev, "metadata", None) else None
                items.append(
                    CaseHistoryItem(
                        milestone_id=getattr(ev, "event_id", f"ms-{secrets.token_hex(6)}"),
                        status=record.status.value if isinstance(record.status, CaseStatus) else str(record.status),
                        label="Resolution Note Added",
                        timestamp=getattr(ev, "timestamp", record.updated_at),
                        department=record.department,
                        description="Official workflow note appended by authority",
                        actor_role=getattr(ev, "principal_role", "AUTHORITY_OFFICER"),
                        note=note_text,
                    )
                )

        # Fallback if no audit events exist yet
        if not items:
            items.append(
                CaseHistoryItem(
                    milestone_id=f"ms-{secrets.token_hex(6)}",
                    status=CaseStatus.DOCKET_CREATED.value,
                    label="Docket Created",
                    timestamp=record.created_at,
                    department=record.department,
                    description="Initial Civic Docket recorded in system",
                    actor_role="CITIZEN",
                    note="Initial Civic Docket Created",
                )
            )
            if record.status != CaseStatus.DOCKET_CREATED:
                status_val = record.status.value if isinstance(record.status, CaseStatus) else str(record.status)
                status_title = status_val.replace("_", " ").title()
                items.append(
                    CaseHistoryItem(
                        milestone_id=f"ms-{secrets.token_hex(6)}",
                        status=status_val,
                        label=status_title,
                        timestamp=record.updated_at,
                        department=record.department,
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
        expected_current_status: Optional[CaseStatus] = None,
    ) -> Optional[CivicCaseRecord]:
        record = self.get_case(case_id)
        if not record:
            return None

        condition = "attribute_exists(case_id)"
        expr_values: Dict[str, Any] = {}
        expr_names: Dict[str, str] = {}

        if expected_current_status is not None:
            condition += " AND #st = :expected_st"
            expr_names["#st"] = "status"
            expr_values[":expected_st"] = (
                expected_current_status.value
                if isinstance(expected_current_status, CaseStatus)
                else str(expected_current_status)
            )

        record.status = new_status
        record.updated_at = datetime.now(timezone.utc)
        if note:
            record.resolution_notes.append(note)

        item = case_record_to_dynamodb(record)
        put_kwargs: Dict[str, Any] = {
            "Item": item,
            "ConditionExpression": condition,
        }
        if expr_names:
            put_kwargs["ExpressionAttributeNames"] = expr_names
        if expr_values:
            put_kwargs["ExpressionAttributeValues"] = expr_values

        try:
            self.table.put_item(**put_kwargs)
            return record
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
                from fastapi import HTTPException, status as http_status
                raise HTTPException(
                    status_code=http_status.HTTP_409_CONFLICT,
                    detail="Concurrent modification conflict: case status has been modified by another operation.",
                )
            logger.error("DynamoDB update_case_status failed for '%s': %s", case_id, exc)
            raise

    def add_resolution_note(
        self,
        case_id: str,
        note: str,
        actor_label: Optional[str] = None,
    ) -> Optional[CivicCaseRecord]:
        now_iso = datetime.now(timezone.utc).isoformat()
        try:
            # Atomic list_append in DynamoDB with case existence check
            self.table.update_item(
                Key={"case_id": case_id},
                UpdateExpression="SET resolution_notes = list_append(if_not_exists(resolution_notes, :empty_list), :new_note), updated_at = :updated_at",
                ConditionExpression="attribute_exists(case_id)",
                ExpressionAttributeValues={
                    ":new_note": [note],
                    ":empty_list": [],
                    ":updated_at": now_iso,
                },
            )
            return self.get_case(case_id)
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
                return None
            logger.error("DynamoDB add_resolution_note failed for '%s': %s", case_id, exc)
            raise

    def add_evidence_uri(self, case_id: str, uri: str) -> Optional[CivicCaseRecord]:
        now_iso = datetime.now(timezone.utc).isoformat()
        try:
            # Atomic list_append in DynamoDB with case existence check
            self.table.update_item(
                Key={"case_id": case_id},
                UpdateExpression="SET evidence_uris = list_append(if_not_exists(evidence_uris, :empty_list), :new_uri), updated_at = :updated_at",
                ConditionExpression="attribute_exists(case_id)",
                ExpressionAttributeValues={
                    ":new_uri": [uri],
                    ":empty_list": [],
                    ":updated_at": now_iso,
                },
            )
            return self.get_case(case_id)
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
                return None
            logger.error("DynamoDB add_evidence_uri failed for '%s': %s", case_id, exc)
            raise

    def confirm_and_resolve_case(
        self,
        case_id: str,
        feedback: Optional[str] = None,
        actor_label: Optional[str] = None,
    ) -> Optional[CivicCaseRecord]:
        record = self.get_case(case_id)
        if not record:
            return None
        now = datetime.now(timezone.utc)
        record.resolution_confirmed = True
        record.resolution_confirmed_at = now
        if feedback:
            record.citizen_feedback = feedback
        record.status = CaseStatus.RESOLVED
        record.updated_at = now

        item = case_record_to_dynamodb(record)
        try:
            self.table.put_item(
                Item=item,
                ConditionExpression="attribute_exists(case_id)",
            )
            return record
        except ClientError as exc:
            logger.error("DynamoDB confirm_and_resolve_case failed for '%s': %s", case_id, exc)
            raise

    def reject_resolution(
        self,
        case_id: str,
        reason: str,
        actor_label: Optional[str] = None,
    ) -> Optional[CivicCaseRecord]:
        record = self.get_case(case_id)
        if not record:
            return None
        now = datetime.now(timezone.utc)
        record.resolution_confirmed = False
        record.resolution_rejected_at = now
        record.rejection_count += 1
        record.citizen_feedback = reason
        record.status = CaseStatus.UNDER_REVIEW
        record.resolution_notes.append(f"Citizen Rejected Resolution: {reason}")
        record.updated_at = now

        item = case_record_to_dynamodb(record)
        try:
            self.table.put_item(
                Item=item,
                ConditionExpression="attribute_exists(case_id)",
            )
            return record
        except ClientError as exc:
            logger.error("DynamoDB reject_resolution failed for '%s': %s", case_id, exc)
            raise

    def set_active_resolution_attempt(
        self,
        case_id: str,
        attempt_id: str,
    ) -> Optional[CivicCaseRecord]:
        now_iso = datetime.now(timezone.utc).isoformat()
        try:
            self.table.update_item(
                Key={"case_id": case_id},
                UpdateExpression="SET active_resolution_attempt = :att, updated_at = :updated_at",
                ConditionExpression="attribute_exists(case_id)",
                ExpressionAttributeValues={
                    ":att": attempt_id,
                    ":updated_at": now_iso,
                },
            )
            return self.get_case(case_id)
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
                return None
            logger.error("DynamoDB set_active_resolution_attempt failed for '%s': %s", case_id, exc)
            raise

    def list_all_cases(self) -> List[CivicCaseRecord]:
        """Scan and retrieve all civic cases across all DynamoDB pagination pages."""
        records: List[CivicCaseRecord] = []
        try:
            scan_kwargs: Dict[str, Any] = {}
            while True:
                response = self.table.scan(**scan_kwargs)
                for item in response.get("Items", []):
                    record = dynamodb_to_case_record(item)
                    if record:
                        records.append(record)
                if "LastEvaluatedKey" in response:
                    scan_kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]
                else:
                    break
            return records
        except ClientError as exc:
            logger.error("DynamoDB list_all_cases failed: %s", exc)
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
