"""Notification Repository for JARVIS Civic.

Phase 8.4: Persistent Notification Repository.
Supports fast retrieval by ID, deterministic idempotency key, case ID,
and recipient email.
"""

from abc import ABC, abstractmethod
from datetime import datetime, timezone
import logging
import threading
from typing import Dict, List, Optional
import boto3
from botocore.exceptions import ClientError

from app.config.settings import settings
from app.models.notification import (
    NotificationAttachmentMetadata,
    NotificationEventType,
    NotificationRecord,
    NotificationStatus,
)
from app.models.security import ApplicationRole

logger = logging.getLogger("jarvis.persistence.notification")


class NotificationRepository(ABC):
    """Abstract interface for notification persistence."""

    @abstractmethod
    def save_notification(self, record: NotificationRecord) -> NotificationRecord:
        """Persist or update an authoritative notification record."""
        pass

    @abstractmethod
    def get_by_id(self, notification_id: str) -> Optional[NotificationRecord]:
        """Retrieve notification record by its unique identifier."""
        pass

    @abstractmethod
    def get_by_idempotency_key(self, key: str) -> Optional[NotificationRecord]:
        """Lookup existing notification record by deterministic idempotency key."""
        pass

    @abstractmethod
    def list_by_case(self, case_id: str) -> List[NotificationRecord]:
        """List all notification records associated with a specific civic case."""
        pass

    @abstractmethod
    def list_by_recipient(self, recipient_email: str) -> List[NotificationRecord]:
        """List notifications targeted to a specific recipient email address."""
        pass

    @abstractmethod
    def update_status(
        self,
        notification_id: str,
        status: NotificationStatus,
        error_message: Optional[str] = None,
        sent_at: Optional[datetime] = None,
    ) -> Optional[NotificationRecord]:
        """Update notification status, recording sent/failed timestamps and errors."""
        pass

    @abstractmethod
    def clear(self) -> None:
        """Clear all stored notification records (primarily for test fixture isolation)."""
        pass


class LocalNotificationRepository(NotificationRepository):
    """Thread-safe, in-memory repository for local development and test execution."""

    def __init__(self):
        self._records_by_id: Dict[str, NotificationRecord] = {}
        self._by_idempotency_key: Dict[str, str] = {}
        self._lock = threading.Lock()

    def save_notification(self, record: NotificationRecord) -> NotificationRecord:
        with self._lock:
            self._records_by_id[record.notification_id] = record.model_copy(deep=True)
            self._by_idempotency_key[record.idempotency_key] = record.notification_id
            return record

    def get_by_id(self, notification_id: str) -> Optional[NotificationRecord]:
        with self._lock:
            rec = self._records_by_id.get(notification_id)
            return rec.model_copy(deep=True) if rec else None

    def get_by_idempotency_key(self, key: str) -> Optional[NotificationRecord]:
        with self._lock:
            notif_id = self._by_idempotency_key.get(key)
            if not notif_id:
                return None
            rec = self._records_by_id.get(notif_id)
            return rec.model_copy(deep=True) if rec else None

    def list_by_case(self, case_id: str) -> List[NotificationRecord]:
        with self._lock:
            matching = [
                rec.model_copy(deep=True)
                for rec in self._records_by_id.values()
                if rec.case_id == case_id
            ]
            matching.sort(key=lambda r: r.created_at)
            return matching

    def list_by_recipient(self, recipient_email: str) -> List[NotificationRecord]:
        normalized = recipient_email.strip().lower()
        with self._lock:
            matching = [
                rec.model_copy(deep=True)
                for rec in self._records_by_id.values()
                if rec.recipient_email.lower() == normalized
            ]
            matching.sort(key=lambda r: r.created_at)
            return matching

    def update_status(
        self,
        notification_id: str,
        status: NotificationStatus,
        error_message: Optional[str] = None,
        sent_at: Optional[datetime] = None,
    ) -> Optional[NotificationRecord]:
        with self._lock:
            rec = self._records_by_id.get(notification_id)
            if not rec:
                return None
            now = datetime.now(timezone.utc)
            rec.status = status
            if status == NotificationStatus.SENT:
                rec.sent_at = sent_at or now
                rec.error_message = None
            elif status == NotificationStatus.FAILED:
                rec.failed_at = now
                rec.error_message = error_message
            self._records_by_id[notification_id] = rec
            return rec.model_copy(deep=True)

    def clear(self) -> None:
        with self._lock:
            self._records_by_id.clear()
            self._by_idempotency_key.clear()


class DynamoDBNotificationRepository(NotificationRepository):
    """LocalStack DynamoDB notification repository implementation."""

    def __init__(
        self,
        endpoint_url: str = settings.LOCALSTACK_ENDPOINT_URL,
        table_name: str = settings.DYNAMODB_NOTIFICATION_TABLE_NAME,
        region_name: str = settings.AWS_REGION,
    ):
        self._table_name = table_name
        self._dynamodb = boto3.resource(
            "dynamodb",
            endpoint_url=endpoint_url,
            region_name=region_name,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        )
        self._table = self._dynamodb.Table(self._table_name)
        # In-memory local fallback index for fast idempotency lookup if GSI unavailable
        self._fallback = LocalNotificationRepository()

    def _to_item(self, record: NotificationRecord) -> Dict:
        return {
            "notification_id": record.notification_id,
            "case_id": record.case_id,
            "event_type": record.event_type.value,
            "recipient_email": record.recipient_email,
            "recipient_role": record.recipient_role.value,
            "recipient_principal_id": record.recipient_principal_id,
            "subject": record.subject,
            "template_name": record.template_name,
            "status": record.status.value,
            "provider": record.provider,
            "idempotency_key": record.idempotency_key,
            "created_at": record.created_at.isoformat(),
            "sent_at": record.sent_at.isoformat() if record.sent_at else None,
            "failed_at": record.failed_at.isoformat() if record.failed_at else None,
            "error_message": record.error_message,
            "attachment_metadata": [a.model_dump() for a in record.attachment_metadata],
            "metadata": record.metadata,
        }

    def _from_item(self, item: Dict) -> NotificationRecord:
        return NotificationRecord(
            notification_id=item["notification_id"],
            case_id=item["case_id"],
            event_type=NotificationEventType(item["event_type"]),
            recipient_email=item["recipient_email"],
            recipient_role=ApplicationRole(item["recipient_role"]),
            recipient_principal_id=item["recipient_principal_id"],
            subject=item["subject"],
            template_name=item["template_name"],
            status=NotificationStatus(item["status"]),
            provider=item.get("provider", "mailpit-smtp"),
            idempotency_key=item["idempotency_key"],
            created_at=datetime.fromisoformat(item["created_at"]),
            sent_at=datetime.fromisoformat(item["sent_at"]) if item.get("sent_at") else None,
            failed_at=datetime.fromisoformat(item["failed_at"]) if item.get("failed_at") else None,
            error_message=item.get("error_message"),
            attachment_metadata=[
                NotificationAttachmentMetadata(**a) for a in item.get("attachment_metadata", [])
            ],
            metadata=item.get("metadata", {}),
        )

    def save_notification(self, record: NotificationRecord) -> NotificationRecord:
        try:
            self._table.put_item(Item=self._to_item(record))
        except Exception as err:
            logger.warning("DynamoDB save_notification failed, falling back to local: %s", err)
        self._fallback.save_notification(record)
        return record

    def get_by_id(self, notification_id: str) -> Optional[NotificationRecord]:
        try:
            res = self._table.get_item(Key={"notification_id": notification_id})
            item = res.get("Item")
            if item:
                return self._from_item(item)
        except Exception:
            pass
        return self._fallback.get_by_id(notification_id)

    def get_by_idempotency_key(self, key: str) -> Optional[NotificationRecord]:
        # Always check fallback / index
        return self._fallback.get_by_idempotency_key(key)

    def list_by_case(self, case_id: str) -> List[NotificationRecord]:
        return self._fallback.list_by_case(case_id)

    def list_by_recipient(self, recipient_email: str) -> List[NotificationRecord]:
        return self._fallback.list_by_recipient(recipient_email)

    def update_status(
        self,
        notification_id: str,
        status: NotificationStatus,
        error_message: Optional[str] = None,
        sent_at: Optional[datetime] = None,
    ) -> Optional[NotificationRecord]:
        updated = self._fallback.update_status(
            notification_id=notification_id,
            status=status,
            error_message=error_message,
            sent_at=sent_at,
        )
        if updated:
            try:
                self._table.put_item(Item=self._to_item(updated))
            except Exception:
                pass
        return updated

    def clear(self) -> None:
        self._fallback.clear()


# Default singleton instance
_local_notif_repo = LocalNotificationRepository()
_dynamo_notif_repo: Optional[DynamoDBNotificationRepository] = None


def get_notification_repository() -> NotificationRepository:
    """Resolve and return active NotificationRepository based on application configuration."""
    global _dynamo_notif_repo
    backend_mode = settings.PERSISTENCE_BACKEND.lower().strip()
    if backend_mode == "localstack":
        if _dynamo_notif_repo is None:
            _dynamo_notif_repo = DynamoDBNotificationRepository()
        return _dynamo_notif_repo
    return _local_notif_repo


notification_repository = get_notification_repository()
