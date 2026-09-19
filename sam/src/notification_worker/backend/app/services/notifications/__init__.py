"""Notification subsystem exports for JARVIS Civic.

Phase 8.4: Pluggable notification service, email templates, and SMTP delivery.
"""

from app.services.notifications.notification_service import (
    NotificationService,
    notification_service,
)
from app.services.notifications.recipient_resolver import (
    NotificationRecipientResolver,
    ResolvedRecipient,
    recipient_resolver,
)
from app.services.notifications.smtp_adapter import (
    DeliveryResult,
    SMTPAdapter,
    StandardSMTPAdapter,
    smtp_adapter,
)
from app.services.notifications.template_service import (
    EmailTemplateService,
    email_template_service,
)

__all__ = [
    "NotificationService",
    "notification_service",
    "NotificationRecipientResolver",
    "ResolvedRecipient",
    "recipient_resolver",
    "SMTPAdapter",
    "StandardSMTPAdapter",
    "smtp_adapter",
    "EmailTemplateService",
    "email_template_service",
    "DeliveryResult",
]
