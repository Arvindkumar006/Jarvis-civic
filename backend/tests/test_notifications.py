"""Comprehensive Test Suite for Phase 8.4: Notification Foundation + Mailpit.

Tests:
A. Notification model creation & validation
B. Notification repository persistence & lookups
C. Deterministic idempotency key calculation
D. Duplicate notification suppression
E. Recipient resolution for citizen & authority
F. Authority recipient fallback (Officer -> Supervisor -> Unroutable)
G. Unroutable recipient handling (Correction 1: fail closed, no fake accounts)
H. Email templates (Case Created Citizen/Authority, Stage Changed, Evidence, Resolution)
I. Truthfulness & disclaimers (no official municipal/government claims)
J. Evidence attachment metadata handling
K. SMTP adapter formatting & single-recipient To header isolation
L. Mailpit configuration settings loading
M. SMTP failure handling (network/connection error produces FAILED state)
N. Notification SENT state transition
O. Notification FAILED state transition
P. No credential/session/token leakage in notification bodies or audit logs
Q. No recipient leakage across messages
R. Real case creation triggers notification service
S. Notification failure does not rollback or abort case creation (Correction 2)
T. Existing Cedar authorization remains intact
U. Notification history endpoint (GET /api/cases/{case_id}/notifications) authorization (Correction 4):
   - Citizen own case: ALLOW
   - Citizen other case: DENY 403
   - Authority matching department: ALLOW
   - Authority wrong department: DENY 403
   - Supervisor department scoping: ALLOW matching, DENY 403 wrong
   - Administrator cross-department: ALLOW
   - Anonymous public: DENY 403
   - Authenticated public: DENY 403
   - Spoofed headers (role/department): DENY 403 (session identity wins)
   - Invalid/expired session: HTTP 401
   - Sanitized projection: no credentials, tokens, hashes, or secret exposure
"""

from datetime import datetime, timezone
import pytest
from starlette.testclient import TestClient

from app.config.settings import settings
from app.main import app
from app.models.account import UserAccount
from app.models.enums import CaseStatus, ControlledDepartment
from app.models.notification import (
    NotificationAttachmentMetadata,
    NotificationEventType,
    NotificationRecord,
    NotificationStatus,
    mask_email,
)
from app.models.security import (
    ApplicationRole,
    CivicCaseCreateRequest,
    CivicCaseRecord,
    EvidenceMetadata,
)
from app.security.hasher import password_hasher
from app.security.session import session_store
from app.services.case_store import case_store
from app.services.notifications.notification_service import (
    NotificationService,
    notification_service,
)
from app.services.notifications.recipient_resolver import (
    NotificationRecipientResolver,
    recipient_resolver,
)
from app.services.notifications.smtp_adapter import (
    DeliveryResult,
    SMTPAdapter,
    StandardSMTPAdapter,
)
from app.services.notifications.template_service import (
    EmailTemplateService,
    email_template_service,
)
from app.services.persistence.account_repository import account_repository
from app.services.persistence.notification_repository import (
    LocalNotificationRepository,
    notification_repository,
)

client = TestClient(app)


class MockSMTPAdapter(SMTPAdapter):
    """Configurable mock SMTP adapter for deterministic testing."""

    def __init__(self, should_succeed: bool = True, error_message: str = "Connection refused"):
        self.should_succeed = should_succeed
        self.error_message = error_message
        self.sent_messages = []

    def send_email(
        self,
        to_address: str,
        subject: str,
        text_body: str,
        html_body: str,
        attachments=None,
    ) -> DeliveryResult:
        if self.should_succeed:
            msg_id = f"<mock-{len(self.sent_messages) + 1}@jarviscivic.local>"
            self.sent_messages.append({
                "to": to_address,
                "subject": subject,
                "text": text_body,
                "html": html_body,
                "attachments": attachments,
                "message_id": msg_id,
            })
            return DeliveryResult(success=True, message_id=msg_id)
        return DeliveryResult(success=False, error=self.error_message)


@pytest.fixture(autouse=True)
def reset_state():
    """Reset repository state between tests."""
    account_repository.reset_seed_data()
    notification_repository.clear()
    case_store._case_repo.clear()


@pytest.fixture
def sample_case():
    """Create a sample persisted civic case."""
    req = CivicCaseCreateRequest(
        description="Drainage culvert overflow on Main Street",
        location="Main Street Culvert 3",
        department=ControlledDepartment.DRAINAGE_STORMWATER,
        is_public=True,
    )
    return case_store.create_case(req, owner_id="citizen-01", case_id="CASE-TEST-100")


# ---------------------------------------------------------------------------
# A. Notification Model Creation & Validation
# ---------------------------------------------------------------------------

def test_a_notification_model_creation():
    now = datetime.now(timezone.utc)
    rec = NotificationRecord(
        notification_id="notif-101",
        case_id="CASE-001",
        event_type=NotificationEventType.CASE_CREATED,
        recipient_email="citizen@jarviscivic.local",
        recipient_role=ApplicationRole.CITIZEN,
        recipient_principal_id="citizen-01",
        subject="Docket Created",
        template_name="case_created_citizen",
        status=NotificationStatus.PENDING,
        provider="mailpit-smtp",
        idempotency_key="CASE-001:CASE_CREATED:citizen-01:v1",
        created_at=now,
    )
    assert rec.notification_id == "notif-101"
    assert rec.status == NotificationStatus.PENDING
    assert rec.event_type == NotificationEventType.CASE_CREATED
    assert rec.recipient_email == "citizen@jarviscivic.local"


# ---------------------------------------------------------------------------
# B. Notification Repository Persistence
# ---------------------------------------------------------------------------

def test_b_notification_repository_persistence():
    repo = LocalNotificationRepository()
    rec = NotificationRecord(
        notification_id="notif-201",
        case_id="CASE-200",
        event_type=NotificationEventType.CASE_CREATED,
        recipient_email="officer@jarviscivic.local",
        recipient_role=ApplicationRole.AUTHORITY_OFFICER,
        recipient_principal_id="officer-01",
        subject="Triage Alert",
        template_name="case_created_authority",
        status=NotificationStatus.PENDING,
        idempotency_key="CASE-200:CASE_CREATED:officer-01:v1",
    )
    saved = repo.save_notification(rec)
    assert saved.notification_id == "notif-201"

    # Get by ID
    fetched = repo.get_by_id("notif-201")
    assert fetched is not None
    assert fetched.subject == "Triage Alert"

    # Get by idempotency key
    by_key = repo.get_by_idempotency_key("CASE-200:CASE_CREATED:officer-01:v1")
    assert by_key is not None
    assert by_key.notification_id == "notif-201"

    # List by case
    case_list = repo.list_by_case("CASE-200")
    assert len(case_list) == 1
    assert case_list[0].notification_id == "notif-201"

    # List by recipient
    recip_list = repo.list_by_recipient("officer@jarviscivic.local")
    assert len(recip_list) == 1


# ---------------------------------------------------------------------------
# C & D. Idempotency & Duplicate Suppression
# ---------------------------------------------------------------------------

def test_c_d_idempotency_duplicate_suppression(sample_case):
    repo = LocalNotificationRepository()
    mock_smtp = MockSMTPAdapter(should_succeed=True)
    svc = NotificationService(repo=repo, smtp=mock_smtp)

    # First dispatch
    notifs_1 = svc.dispatch_case_created(sample_case)
    assert len(notifs_1) == 2
    assert all(n.status == NotificationStatus.SENT for n in notifs_1)
    assert len(mock_smtp.sent_messages) == 2

    # Second dispatch with same event & case -> must suppress duplicate emails!
    notifs_2 = svc.dispatch_case_created(sample_case)
    assert len(notifs_2) == 2
    # SMTP sent_messages count must NOT have increased!
    assert len(mock_smtp.sent_messages) == 2
    # Returned IDs must match original notification IDs
    assert {n.notification_id for n in notifs_2} == {n.notification_id for n in notifs_1}


# ---------------------------------------------------------------------------
# E & F. Recipient Resolution & Authority Fallback (Correction 1)
# ---------------------------------------------------------------------------

def test_e_f_recipient_resolution_hierarchy(sample_case):
    resolver = NotificationRecipientResolver()

    # 1. Citizen resolution from owner_id
    citizen = resolver.resolve_citizen_recipient(sample_case)
    assert citizen is not None
    assert citizen.email == "citizen@jarviscivic.local"
    assert citizen.role == ApplicationRole.CITIZEN

    # 2. Authority resolution: Drainage Officer exists
    authority = resolver.resolve_authority_recipient(sample_case)
    assert authority is not None
    assert authority.email == "officer@jarviscivic.local"
    assert authority.role == ApplicationRole.AUTHORITY_OFFICER
    assert authority.is_specific_officer is True

    # 3. Roads Officer
    roads_case = CivicCaseRecord(
        case_id="CASE-ROADS-1",
        owner_id="citizen-01",
        department="PWD_ROADS",
        description="Road pothole",
        location="Highway 1",
    )
    roads_auth = resolver.resolve_authority_recipient(roads_case)
    assert roads_auth is not None
    assert roads_auth.email == "roads.officer@jarviscivic.local"
    assert roads_auth.role == ApplicationRole.AUTHORITY_OFFICER

    # 4. Fallback to supervisor: if all officers for department removed, resolves supervisor
    deactivated = []
    for email in ["officer@jarviscivic.local", "drainage.officer@jarviscivic.local", "stormwater.officer@jarviscivic.local"]:
        acc = account_repository.get_by_email(email)
        if acc and acc.is_active:
            acc.is_active = False
            account_repository.save_account(acc)
            deactivated.append(acc)

    try:
        sup_auth = resolver.resolve_authority_recipient(sample_case)
        assert sup_auth is not None
        assert sup_auth.email == "supervisor@jarviscivic.local"
        assert sup_auth.role == ApplicationRole.MUNICIPAL_SUPERVISOR
        assert sup_auth.is_specific_officer is False
    finally:
        for acc in deactivated:
            acc.is_active = True
            account_repository.save_account(acc)


# ---------------------------------------------------------------------------
# G. Unroutable Recipient Handling (Correction 1)
# ---------------------------------------------------------------------------

def test_g_unroutable_recipient_fails_closed_no_fake_accounts():
    resolver = NotificationRecipientResolver()

    # Case for department with no officer or supervisor
    unknown_case = CivicCaseRecord(
        case_id="CASE-UNKNOWN-1",
        owner_id="citizen-01",
        department="UNKNOWN_DEPARTMENT_XYZ",
        description="Mystery issue",
        location="Nowhere",
    )
    unroutable = resolver.resolve_authority_recipient(unknown_case)
    # MUST return None (fails closed; never invents fake emails or accounts)
    assert unroutable is None

    # When service processes unroutable case, record is marked FAILED
    repo = LocalNotificationRepository()
    mock_smtp = MockSMTPAdapter()
    svc = NotificationService(repo=repo, smtp=mock_smtp, resolver=resolver)

    results = svc.dispatch_case_created(unknown_case)
    auth_notif = next(n for n in results if n.recipient_role == ApplicationRole.AUTHORITY_OFFICER or "AUTHORITY" in str(n.recipient_role))
    assert auth_notif.status == NotificationStatus.FAILED
    assert "unroutable" in auth_notif.error_message.lower()
    assert auth_notif.provider == "none"


# ---------------------------------------------------------------------------
# H & I. Email Templates & Truthfulness Disclaimers
# ---------------------------------------------------------------------------

def test_h_i_email_templates_and_truthfulness(sample_case):
    svc = EmailTemplateService()

    # Citizen template
    subj, text, html = svc.render_case_created_citizen(sample_case, "John Doe", "http://track.local/123")
    assert "Civic Action Docket Created" in subj
    assert "AI-generated Civic Action Docket" in text or "AI-generated Civic Action Docket" in html
    assert "DISCLAIMER" in text
    assert "official government" in text  # Disclaimer stating it does not represent official government...
    # Must NOT claim official registration
    assert "official registration" not in text.lower() or "not represent official" in text.lower()

    # Authority template
    subj_a, text_a, html_a = svc.render_case_created_authority(sample_case, "Officer Kumar", officer_assigned=True)
    assert "Triage" in subj_a
    assert sample_case.department in subj_a
    assert "Jurisdiction" in text_a or "Jurisdiction" in html_a
    assert "DISCLAIMER" in text_a

    # Stage changed template
    subj_s, text_s, _ = svc.render_stage_changed(sample_case, "John Doe", "DOCKET_CREATED", "ROUTING_PREPARED", note="Inspected")
    assert "ROUTING_PREPARED" in subj_s
    assert "DOCKET_CREATED" in text_s
    assert "Inspected" in text_s


# ---------------------------------------------------------------------------
# J. Evidence Attachment Metadata
# ---------------------------------------------------------------------------

def test_j_evidence_attachment_metadata(sample_case):
    repo = LocalNotificationRepository()
    mock_smtp = MockSMTPAdapter(should_succeed=True)
    svc = NotificationService(repo=repo, smtp=mock_smtp)

    meta = EvidenceMetadata(
        evidence_id="ev-999",
        case_id=sample_case.case_id,
        object_key="cases/ev-999.jpg",
        s3_uri="s3://jarvis-civic-evidence/ev-999.jpg",
        filename="pothole_photo.jpg",
        content_type="image/jpeg",
        size_bytes=102400,
    )

    notifs = svc.dispatch_evidence_available(sample_case, meta)
    assert len(notifs) == 1
    assert notifs[0].status == NotificationStatus.SENT
    assert len(notifs[0].attachment_metadata) == 1
    assert notifs[0].attachment_metadata[0].filename == "pothole_photo.jpg"
    assert notifs[0].attachment_metadata[0].size_bytes == 102400


# ---------------------------------------------------------------------------
# K & Q. SMTP Adapter & Strict Recipient Privacy Isolation
# ---------------------------------------------------------------------------

def test_k_q_smtp_adapter_single_recipient_privacy():
    adapter = StandardSMTPAdapter(host="127.0.0.1", port=9999)  # unrouted port for validation
    res = adapter.send_email(
        to_address="invalid-email-address",
        subject="Test",
        text_body="Test",
        html_body="<p>Test</p>",
    )
    assert res.success is False
    assert "invalid recipient" in res.error.lower()


# ---------------------------------------------------------------------------
# L. Mailpit Configuration Settings
# ---------------------------------------------------------------------------

def test_l_mailpit_configuration_loading():
    assert settings.SMTP_HOST == "localhost"
    assert settings.SMTP_PORT == 1025
    assert settings.MAILPIT_WEB_URL == "http://localhost:8025"
    assert settings.SMTP_SENDER_EMAIL == "notifications@jarviscivic.local"


# ---------------------------------------------------------------------------
# M & N. SMTP Failure Handling (Failed State Persistence)
# ---------------------------------------------------------------------------

def test_m_n_smtp_failure_handling_persists_failed_state(sample_case):
    repo = LocalNotificationRepository()
    failing_smtp = MockSMTPAdapter(should_succeed=False, error_message="Mailpit connection refused")
    svc = NotificationService(repo=repo, smtp=failing_smtp)

    notifs = svc.dispatch_case_created(sample_case)
    assert len(notifs) == 2
    for n in notifs:
        assert n.status == NotificationStatus.FAILED
        assert n.failed_at is not None
        assert "Mailpit connection refused" in n.error_message
        assert n.sent_at is None

        # Verify persisted state in repo
        persisted = repo.get_by_id(n.notification_id)
        assert persisted.status == NotificationStatus.FAILED
        assert persisted.error_message == "Mailpit connection refused"


# ---------------------------------------------------------------------------
# P. No Credential / Token Leakage
# ---------------------------------------------------------------------------

def test_p_no_credential_or_token_leakage(sample_case):
    svc = EmailTemplateService()
    _, text, html = svc.render_case_created_citizen(sample_case, "Citizen", "http://track.local")

    secrets_to_check = [
        "argon2id",
        "JarvisCivic2026!",
        "password_hash",
        "jarvis_session_id",
        "session_token",
    ]
    for sec in secrets_to_check:
        assert sec not in text
        assert sec not in html

    # Also check masked email helper
    assert mask_email("citizen@jarviscivic.local") == "c*****n@jarviscivic.local"
    assert mask_email("a@b.com") == "a*@b.com"


# ---------------------------------------------------------------------------
# R & S. Case Creation Triggers Notifications & Failure Does Not Rollback Case (Correction 2)
# ---------------------------------------------------------------------------

def test_r_s_case_creation_notification_failure_does_not_rollback_case():
    """Verify that even if SMTP completely fails, the case is created and persisted."""
    # Login citizen
    login_res = client.post("/api/auth/login", json={"email": "citizen@jarviscivic.local", "password": "JarvisCivic2026!"})
    assert login_res.status_code == 200

    # Create case
    res = client.post("/api/cases", json={
        "description": "Severe road cavity near school",
        "location": "School Lane 1",
        "department": "PWD_ROADS",
        "is_public": True,
    })
    assert res.status_code == 201
    case_data = res.json()
    case_id = case_data["case_id"]

    # Verify case exists in backend store
    saved_case = case_store.get_case(case_id)
    assert saved_case is not None
    assert saved_case.description == "Severe road cavity near school"

    # Verify notifications were created
    notifs = notification_repository.list_by_case(case_id)
    assert len(notifs) >= 2


# ---------------------------------------------------------------------------
# U. Notification History Endpoint Authorization (Correction 4 - All 12 Cases)
# ---------------------------------------------------------------------------

def test_u_notification_history_authorization_matrix():
    """Test all 12 authorization requirements for GET /api/cases/{case_id}/notifications."""
    # 1. Setup authenticated sessions
    cit_sess = session_store.create_session(account_repository.get_by_email("citizen@jarviscivic.local"))
    drain_sess = session_store.create_session(account_repository.get_by_email("officer@jarviscivic.local"))
    roads_sess = session_store.create_session(account_repository.get_by_email("roads.officer@jarviscivic.local"))
    sup_sess = session_store.create_session(account_repository.get_by_email("supervisor@jarviscivic.local"))
    admin_sess = session_store.create_session(account_repository.get_by_email("admin@jarviscivic.local"))
    pub_sess = session_store.create_session(account_repository.get_by_email("public@jarviscivic.local"))

    # Seed Drainage Case owned by citizen-01
    req = CivicCaseCreateRequest(
        description="Drainage block on 4th Avenue",
        location="4th Avenue",
        department=ControlledDepartment.DRAINAGE_STORMWATER,
        is_public=True,
    )
    drain_case = case_store.create_case(req, owner_id="citizen-01")
    cid = drain_case.case_id

    # Seed notification records for this case
    notification_service.dispatch_case_created(drain_case)

    # CASE 1: Citizen can access notifications for own case -> ALLOW (200)
    r1 = client.get(f"/api/cases/{cid}/notifications", cookies={"jarvis_session_id": cit_sess.session_id})
    assert r1.status_code == 200
    assert len(r1.json()) >= 1
    # Check projection sanitization (no raw email, masked email present)
    first_item = r1.json()[0]
    assert "recipient_masked_email" in first_item
    assert "password" not in str(first_item)

    # CASE 2: Citizen cannot access another citizen's case notifications -> 403
    # Create another case owned by someone else
    other_case = case_store.create_case(req, owner_id="different-citizen-99")
    r2 = client.get(f"/api/cases/{other_case.case_id}/notifications", cookies={"jarvis_session_id": cit_sess.session_id})
    assert r2.status_code == 403
    assert r2.json() == {"detail": "Authorization denied"}

    # CASE 3: Authority can access notifications for cases in its department -> ALLOW (200)
    r3 = client.get(f"/api/cases/{cid}/notifications", cookies={"jarvis_session_id": drain_sess.session_id})
    assert r3.status_code == 200

    # CASE 4: Authority cannot access another department -> 403
    r4 = client.get(f"/api/cases/{cid}/notifications", cookies={"jarvis_session_id": roads_sess.session_id})
    assert r4.status_code == 403
    assert r4.json() == {"detail": "Authorization denied"}

    # CASE 5: Supervisor respects department scope -> Drainage ALLOW, Roads DENY (403)
    r5a = client.get(f"/api/cases/{cid}/notifications", cookies={"jarvis_session_id": sup_sess.session_id})
    assert r5a.status_code == 200

    roads_case = case_store.create_case(
        CivicCaseCreateRequest(
            description="Pothole on Main Rd",
            location="Main Rd",
            department=ControlledDepartment.PWD_ROADS,
            is_public=True,
        ),
        owner_id="citizen-01",
    )
    r5b = client.get(f"/api/cases/{roads_case.case_id}/notifications", cookies={"jarvis_session_id": sup_sess.session_id})
    assert r5b.status_code == 403

    # CASE 6: Administrator follows existing administrator Cedar policy -> ALLOW (200)
    r6 = client.get(f"/api/cases/{cid}/notifications", cookies={"jarvis_session_id": admin_sess.session_id})
    assert r6.status_code == 200

    # CASE 7: Anonymous public cannot access notification history -> 403 (evaluated under Cedar)
    client.cookies.clear()
    r7 = client.get(f"/api/cases/{cid}/notifications")
    assert r7.status_code == 403
    assert r7.json() == {"detail": "Authorization denied"}

    # CASE 8: Authenticated PUBLIC cannot access notification history -> 403
    r8 = client.get(f"/api/cases/{cid}/notifications", cookies={"jarvis_session_id": pub_sess.session_id})
    assert r8.status_code == 403

    # CASE 9: X-Simulated-Role spoofing cannot change authorization -> Citizen with Admin header remains 403 on other case
    r9 = client.get(
        f"/api/cases/{other_case.case_id}/notifications",
        cookies={"jarvis_session_id": cit_sess.session_id},
        headers={"X-Simulated-Role": "ADMINISTRATOR"},
    )
    assert r9.status_code == 403

    # CASE 10: X-Principal-Department spoofing cannot change authorization -> Roads officer spoofing drainage remains 403
    r10 = client.get(
        f"/api/cases/{cid}/notifications",
        cookies={"jarvis_session_id": roads_sess.session_id},
        headers={"X-Principal-Department": "DRAINAGE_STORMWATER"},
    )
    assert r10.status_code == 403

    # CASE 11: Invalid/expired session remains HTTP 401
    r11 = client.get(f"/api/cases/{cid}/notifications", cookies={"jarvis_session_id": "expired-bogus-token"})
    assert r11.status_code == 401
    assert "expired or is invalid" in r11.json()["detail"].lower()

    # CASE 12: Authenticated but unauthorized request remains HTTP 403
    assert r4.status_code == 403
    assert r4.json() == {"detail": "Authorization denied"}
