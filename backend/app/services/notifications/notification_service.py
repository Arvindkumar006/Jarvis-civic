"""Centralized Notification Service for JARVIS Civic.

Phase 8.4: Production-structured notification subsystem.
Orchestrates:
Notification Event
  ↓
NotificationRecipientResolver
  ↓
EmailTemplateService
  ↓
Idempotency Check (NotificationRepository)
  ↓
SMTPAdapter (Mailpit)
  ↓
Audit Dispatcher & Persistence

SECURITY & INTEGRITY INVARIANTS:
1. Notification failure never rolls back or corrupts the case.
2. Synchronous, deterministic, and testable (no uncontrolled background threads).
3. Client-provided roles, departments, or emails are never trusted.
4. Each recipient receives an individual message (zero multi-recipient leakage).
5. All delivery attempts (SENT/FAILED) are persisted in NotificationRepository.
"""

from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional
import uuid

from app.config.settings import settings
from app.models.notification import (
    NotificationAttachmentMetadata,
    NotificationEventType,
    NotificationRecord,
    NotificationStatus,
)
from app.models.security import CivicCaseRecord, EvidenceMetadata
from app.security.audit import audit_dispatcher
from app.services.notifications.recipient_resolver import (
    NotificationRecipientResolver,
    ResolvedRecipient,
    recipient_resolver,
)
from app.services.notifications.smtp_adapter import (
    DeliveryResult,
    SMTPAdapter,
    smtp_adapter,
)
from app.services.notifications.template_service import (
    EmailTemplateService,
    email_template_service,
)
from app.services.persistence.notification_repository import (
    NotificationRepository,
    notification_repository,
)

logger = logging.getLogger("jarvis.notifications.service")


class NotificationService:
    """Coordinates recipient routing, template rendering, idempotency, and SMTP dispatch."""

    def __init__(
        self,
        repo: Optional[NotificationRepository] = None,
        resolver: Optional[NotificationRecipientResolver] = None,
        templates: Optional[EmailTemplateService] = None,
        smtp: Optional[SMTPAdapter] = None,
    ):
        self._repo = repo or notification_repository
        self._resolver = resolver or recipient_resolver
        self._templates = templates or email_template_service
        self._smtp = smtp or smtp_adapter

    def _build_idempotency_key(
        self,
        case_id: str,
        event_type: NotificationEventType,
        recipient_principal_id: str,
        event_version: str = "v1",
    ) -> str:
        """Compute deterministic idempotency key."""
        return f"{case_id}:{event_type.value}:{recipient_principal_id}:{event_version}"

    def _send_individual_notification(
        self,
        case: CivicCaseRecord,
        event_type: NotificationEventType,
        recipient: Optional[ResolvedRecipient],
        unroutable_role_label: str,
        subject: str,
        text_body: str,
        html_body: str,
        template_name: str,
        event_version: str = "v1",
        attachment_metadata: Optional[List[NotificationAttachmentMetadata]] = None,
        attachments_bytes: Optional[List[Dict[str, Any]]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> NotificationRecord:
        """Process and send an individual notification, enforcing idempotency and error recording."""
        now = datetime.now(timezone.utc)
        meta = metadata or {}

        # 1. Handle unroutable recipient (Correction 1: Fail closed, never invent fake accounts)
        if recipient is None:
            notif_id = f"notif-{uuid.uuid4().hex[:12]}"
            idemp_key = self._build_idempotency_key(
                case.case_id, event_type, f"unroutable-{unroutable_role_label.lower()}", event_version
            )
            failed_record = NotificationRecord(
                notification_id=notif_id,
                case_id=case.case_id,
                event_type=event_type,
                recipient_email="unroutable@jarviscivic.local",
                recipient_role=case.owner_id and unroutable_role_label or "UNKNOWN",  # type: ignore
                recipient_principal_id=f"unroutable-{unroutable_role_label.lower()}",
                subject=subject,
                template_name=template_name,
                status=NotificationStatus.FAILED,
                provider="none",
                idempotency_key=idemp_key,
                created_at=now,
                failed_at=now,
                error_message=f"Recipient unroutable: no active {unroutable_role_label} in directory for department '{case.department}'",
                attachment_metadata=attachment_metadata or [],
                metadata=meta,
            )
            self._repo.save_notification(failed_record)
            logger.warning("Notification %s created in FAILED state (unroutable recipient)", notif_id)
            return failed_record

        # 2. Compute idempotency key
        idemp_key = self._build_idempotency_key(
            case.case_id, event_type, recipient.principal_id, event_version
        )

        # 3. Idempotency Check
        existing = self._repo.get_by_idempotency_key(idemp_key)
        if existing:
            if existing.status == NotificationStatus.SENT:
                logger.info(
                    "Idempotency suppression: notification %s already SENT for key %s",
                    existing.notification_id,
                    idemp_key,
                )
                return existing
            if existing.status == NotificationStatus.PENDING:
                logger.info(
                    "Idempotency suppression: notification %s already PENDING for key %s",
                    existing.notification_id,
                    idemp_key,
                )
                return existing
            # If FAILED, we allow this subsequent execution to retry with new attempt record

        # 4. Create persistent record in PENDING state
        notif_id = f"notif-{uuid.uuid4().hex[:12]}"
        record = NotificationRecord(
            notification_id=notif_id,
            case_id=case.case_id,
            event_type=event_type,
            recipient_email=recipient.email,
            recipient_role=recipient.role,
            recipient_principal_id=recipient.principal_id,
            subject=subject,
            template_name=template_name,
            status=NotificationStatus.PENDING,
            provider="mailpit-smtp",
            idempotency_key=idemp_key,
            created_at=now,
            attachment_metadata=attachment_metadata or [],
            metadata=meta,
        )
        self._repo.save_notification(record)

        # 5. Dispatch via SMTP Adapter
        try:
            delivery_result: DeliveryResult = self._smtp.send_email(
                to_address=recipient.email,
                subject=subject,
                text_body=text_body,
                html_body=html_body,
                attachments=attachments_bytes,
            )
        except Exception as smtp_ex:
            delivery_result = DeliveryResult(success=False, error=f"SMTPAdapter Exception: {type(smtp_ex).__name__}")

        # 6. Update persistent status (SENT or FAILED)
        if delivery_result.success:
            updated = self._repo.update_status(
                notification_id=notif_id,
                status=NotificationStatus.SENT,
                sent_at=datetime.now(timezone.utc),
            )
            # Record audit event
            try:
                audit_dispatcher.record_workflow_event(
                    case_id=case.case_id,
                    event_type="NOTIFICATION_DISPATCHED",
                    previous_status="PENDING",
                    new_status="SENT",
                    principal=None,
                    outcome="SUCCESS",
                    metadata={
                        "notification_id": notif_id,
                        "event_type": event_type.value,
                        "recipient_role": recipient.role.value,
                    },
                )
            except Exception:
                pass
            return updated or record
        else:
            updated = self._repo.update_status(
                notification_id=notif_id,
                status=NotificationStatus.FAILED,
                error_message=delivery_result.error or "Unknown SMTP delivery error",
            )
            logger.warning(
                "Notification %s to %s failed delivery: %s",
                notif_id,
                recipient.email,
                delivery_result.error,
            )
            # Record audit failure event
            try:
                audit_dispatcher.record_workflow_event(
                    case_id=case.case_id,
                    event_type="NOTIFICATION_FAILED",
                    previous_status="PENDING",
                    new_status="FAILED",
                    principal=None,
                    outcome="FAILURE",
                    metadata={
                        "notification_id": notif_id,
                        "event_type": event_type.value,
                        "recipient_role": recipient.role.value,
                        "error": delivery_result.error,
                    },
                )
            except Exception:
                pass
            return updated or record

    def dispatch_case_created(self, case: CivicCaseRecord) -> List[NotificationRecord]:
        """Dispatch notifications upon case creation: Citizen confirmation + Authority triage."""
        records: List[NotificationRecord] = []
        tracking_url = f"{settings.ALLOWED_ORIGINS[0]}/#track/{case.case_id}"

        # 1. Citizen Confirmation
        citizen_recipient = self._resolver.resolve_citizen_recipient(case)
        if citizen_recipient:
            subject, text_body, html_body = self._templates.render_case_created_citizen(
                case=case,
                recipient_name=citizen_recipient.display_name,
                tracking_url=tracking_url,
            )
            rec = self._send_individual_notification(
                case=case,
                event_type=NotificationEventType.CASE_CREATED,
                recipient=citizen_recipient,
                unroutable_role_label="CITIZEN",
                subject=subject,
                text_body=text_body,
                html_body=html_body,
                template_name="case_created_citizen",
                event_version="v1",
            )
            records.append(rec)
        else:
            rec = self._send_individual_notification(
                case=case,
                event_type=NotificationEventType.CASE_CREATED,
                recipient=None,
                unroutable_role_label="CITIZEN",
                subject=f"[JARVIS Civic] Case Created: {case.case_id}",
                text_body="",
                html_body="",
                template_name="case_created_citizen",
                event_version="v1",
            )
            records.append(rec)

        # 2. Responsible Authority Notification
        authority_recipient = self._resolver.resolve_authority_recipient(case)
        if authority_recipient:
            subject, text_body, html_body = self._templates.render_case_created_authority(
                case=case,
                recipient_name=authority_recipient.display_name,
                officer_assigned=authority_recipient.is_specific_officer,
            )
            rec = self._send_individual_notification(
                case=case,
                event_type=NotificationEventType.CASE_CREATED,
                recipient=authority_recipient,
                unroutable_role_label="AUTHORITY_OFFICER",
                subject=subject,
                text_body=text_body,
                html_body=html_body,
                template_name="case_created_authority",
                event_version="v1",
            )
            records.append(rec)
        else:
            rec = self._send_individual_notification(
                case=case,
                event_type=NotificationEventType.CASE_CREATED,
                recipient=None,
                unroutable_role_label="AUTHORITY_OFFICER",
                subject=f"[JARVIS Civic — Triage] New Docket: {case.case_id}",
                text_body="",
                html_body="",
                template_name="case_created_authority",
                event_version="v1",
            )
            records.append(rec)

        return records

    def dispatch_stage_changed(
        self,
        case: CivicCaseRecord,
        previous_stage: str,
        new_stage: str,
        note: Optional[str] = None,
    ) -> List[NotificationRecord]:
        """Dispatch lifecycle stage advance notification to the citizen owner."""
        records: List[NotificationRecord] = []
        tracking_url = f"{settings.ALLOWED_ORIGINS[0]}/#track/{case.case_id}"
        citizen_recipient = self._resolver.resolve_citizen_recipient(case)

        event_version = f"{previous_stage}->{new_stage}"

        if citizen_recipient:
            subject, text_body, html_body = self._templates.render_stage_changed(
                case=case,
                recipient_name=citizen_recipient.display_name,
                previous_stage=previous_stage,
                new_stage=new_stage,
                note=note,
                tracking_url=tracking_url,
            )
            rec = self._send_individual_notification(
                case=case,
                event_type=NotificationEventType.WORKFLOW_STAGE_CHANGED,
                recipient=citizen_recipient,
                unroutable_role_label="CITIZEN",
                subject=subject,
                text_body=text_body,
                html_body=html_body,
                template_name="stage_changed_citizen",
                event_version=event_version,
                metadata={"previous_stage": previous_stage, "new_stage": new_stage, "note": note},
            )
            records.append(rec)
        else:
            rec = self._send_individual_notification(
                case=case,
                event_type=NotificationEventType.WORKFLOW_STAGE_CHANGED,
                recipient=None,
                unroutable_role_label="CITIZEN",
                subject=f"[JARVIS Civic] Status Update: {new_stage}",
                text_body="",
                html_body="",
                template_name="stage_changed_citizen",
                event_version=event_version,
            )
            records.append(rec)

        return records

    def dispatch_evidence_available(
        self,
        case: CivicCaseRecord,
        evidence: EvidenceMetadata,
    ) -> List[NotificationRecord]:
        """Dispatch notification when evidence has been verified and persisted."""
        records: List[NotificationRecord] = []
        authority_recipient = self._resolver.resolve_authority_recipient(case)
        att_meta = [
            NotificationAttachmentMetadata(
                filename=evidence.filename,
                content_type=evidence.content_type,
                size_bytes=evidence.size_bytes,
                s3_uri=evidence.s3_uri,
            )
        ]

        if authority_recipient:
            subject, text_body, html_body = self._templates.render_evidence_available(
                case=case,
                recipient_name=authority_recipient.display_name,
                filename=evidence.filename,
                content_type=evidence.content_type,
            )
            rec = self._send_individual_notification(
                case=case,
                event_type=NotificationEventType.EVIDENCE_AVAILABLE,
                recipient=authority_recipient,
                unroutable_role_label="AUTHORITY_OFFICER",
                subject=subject,
                text_body=text_body,
                html_body=html_body,
                template_name="evidence_available_authority",
                event_version=evidence.evidence_id,
                attachment_metadata=att_meta,
            )
            records.append(rec)
        return records

    def dispatch_resolution_ready(
        self,
        case: CivicCaseRecord,
        note: Optional[str] = None,
    ) -> List[NotificationRecord]:
        """Dispatch notification that proposed resolution details are ready (infrastructure only)."""
        records: List[NotificationRecord] = []
        citizen_recipient = self._resolver.resolve_citizen_recipient(case)

        if citizen_recipient:
            subject, text_body, html_body = self._templates.render_resolution_ready(
                case=case,
                recipient_name=citizen_recipient.display_name,
                note=note,
            )
            rec = self._send_individual_notification(
                case=case,
                event_type=NotificationEventType.RESOLUTION_READY,
                recipient=citizen_recipient,
                unroutable_role_label="CITIZEN",
                subject=subject,
                text_body=text_body,
                html_body=html_body,
                template_name="resolution_ready_citizen",
                event_version="v1",
                metadata={"note": note},
            )
            records.append(rec)
        return records

    def get_case_notifications(self, case_id: str) -> List[NotificationRecord]:
        """Retrieve authoritative notification records for a case."""
        return self._repo.list_by_case(case_id)


# Global singleton instance
notification_service = NotificationService()
