"""SMTP Adapter Abstraction and Implementation for JARVIS Civic.

Phase 8.4: Pluggable email dispatch adapter.
Connects to local Mailpit (or any standard SMTP server) without leaking credentials,
supporting text body, HTML body, and sanitized attachment metadata.
"""

from abc import ABC, abstractmethod
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr, make_msgid
import logging
import smtplib
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from app.config.settings import settings

logger = logging.getLogger("jarvis.notifications.smtp")


class DeliveryResult(BaseModel):
    """Result of an SMTP message delivery attempt."""

    success: bool
    message_id: Optional[str] = None
    error: Optional[str] = None


class SMTPAdapter(ABC):
    """Abstract contract for SMTP email transmission."""

    @abstractmethod
    def send_email(
        self,
        to_address: str,
        subject: str,
        text_body: str,
        html_body: str,
        attachments: Optional[List[Dict[str, Any]]] = None,
    ) -> DeliveryResult:
        """Send an individual email message."""
        pass


class StandardSMTPAdapter(SMTPAdapter):
    """Production-structured standard library smtplib adapter.

    Connects to local Mailpit (localhost:1025) or configured development/staging SMTP.
    Safely captures network/socket exceptions without leaking secrets.
    """

    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        sender_email: Optional[str] = None,
        sender_name: Optional[str] = None,
        use_tls: Optional[bool] = None,
        timeout: Optional[float] = None,
    ):
        self._host = host or settings.SMTP_HOST
        self._port = port or settings.SMTP_PORT
        self._username = username or settings.SMTP_USERNAME
        self._password = password or settings.SMTP_PASSWORD
        self._sender_email = sender_email or settings.SMTP_SENDER_EMAIL
        self._sender_name = sender_name or settings.SMTP_SENDER_NAME
        self._use_tls = use_tls if use_tls is not None else settings.SMTP_USE_TLS
        self._timeout = timeout if timeout is not None else settings.SMTP_TIMEOUT_SECONDS

    def send_email(
        self,
        to_address: str,
        subject: str,
        text_body: str,
        html_body: str,
        attachments: Optional[List[Dict[str, Any]]] = None,
    ) -> DeliveryResult:
        """Send an individual, privacy-isolated email message to a single recipient."""
        if not to_address or "@" not in to_address:
            return DeliveryResult(success=False, error=f"Invalid recipient email address: '{to_address}'")

        try:
            # 1. Build MIME structure
            msg_id = make_msgid(domain="jarviscivic.local")

            if attachments and len(attachments) > 0:
                root_msg = MIMEMultipart("mixed")
                alt_part = MIMEMultipart("alternative")
                alt_part.attach(MIMEText(text_body, "plain", "utf-8"))
                alt_part.attach(MIMEText(html_body, "html", "utf-8"))
                root_msg.attach(alt_part)

                # Attach validated artifacts
                for att in attachments:
                    filename = att.get("filename", "attachment.bin")
                    content_bytes = att.get("content_bytes")
                    content_type = att.get("content_type", "application/octet-stream")

                    if content_bytes and isinstance(content_bytes, bytes):
                        maintype, _, subtype = content_type.partition("/")
                        part = MIMEBase(maintype or "application", subtype or "octet-stream")
                        part.set_payload(content_bytes)
                        encoders.encode_base64(part)
                        part.add_header("Content-Disposition", f'attachment; filename="{filename}"')
                        root_msg.attach(part)
            else:
                root_msg = MIMEMultipart("alternative")
                root_msg.attach(MIMEText(text_body, "plain", "utf-8"))
                root_msg.attach(MIMEText(html_body, "html", "utf-8"))

            root_msg["Message-ID"] = msg_id
            root_msg["Subject"] = subject
            root_msg["From"] = formataddr((self._sender_name, self._sender_email))
            # Individual To header: guarantees complete recipient privacy (no multi-party exposure)
            root_msg["To"] = to_address

            # 2. Establish SMTP connection
            with smtplib.SMTP(self._host, self._port, timeout=self._timeout) as server:
                if self._use_tls:
                    server.starttls()
                if self._username and self._password:
                    server.login(self._username, self._password)

                server.sendmail(self._sender_email, [to_address], root_msg.as_string())

            logger.info("Email successfully dispatched via SMTP to %s (Msg-ID: %s)", to_address, msg_id)
            return DeliveryResult(success=True, message_id=msg_id)

        except (smtplib.SMTPException, OSError, ConnectionError) as net_err:
            # Format sanitized error message without exposing credentials or internal topology
            err_msg = f"SMTP transmission failed to {self._host}:{self._port}: {type(net_err).__name__}"
            logger.warning("SMTP delivery error: %s", err_msg)
            return DeliveryResult(success=False, error=err_msg)
        except Exception as unexpected_err:
            err_msg = f"Unexpected delivery failure: {type(unexpected_err).__name__}"
            logger.error("Unexpected error sending email: %s", err_msg)
            return DeliveryResult(success=False, error=err_msg)


# Global singleton instance
smtp_adapter = StandardSMTPAdapter()
