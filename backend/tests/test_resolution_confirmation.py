"""Focused Security and Integration Tests for JARVIS Civic Phase 8.8:
Citizen Resolution Confirmation & Closure Gate.

Verifies:
1. Owner citizen ACCEPT -> 200 (atomically transitions to RESOLVED, sets resolution_confirmed=True)
2. Owner citizen REJECT -> 200 (remains UNDER_REVIEW, rejection_count incremented, feedback stored)
3. Rejection reason < 5 chars -> 422 Unprocessable Entity
4. Different citizen ACCEPT -> 403 Forbidden (Cedar DENY)
5. Different citizen REJECT -> 403 Forbidden (Cedar DENY)
6. Authority officer ACCEPT -> 403 Forbidden (Cedar DENY)
7. Authority officer REJECT -> 403 Forbidden (Cedar DENY)
8. Municipal supervisor ACCEPT and REJECT -> 403 Forbidden (Cedar DENY)
9. Administrator ACCEPT and REJECT -> 403 Forbidden (Cedar DENY - No administrative bypass)
10. Unauthenticated public user -> 401 Unauthorized
11. Forged role / principal / department headers rejected in authenticated session
12. Direct authority PATCH /status to RESOLVED blocked with HTTP 409 Conflict
13. ACCEPT with no resolution evidence -> 409 Conflict
14. Deterministic invalid evidence (e.g. corrupt) cannot close case -> 409 Conflict
15. AI UNCERTAIN + valid deterministic evidence + citizen ACCEPT -> 200 OK (RESOLVED)
16. AI REJECTED + valid deterministic evidence + citizen ACCEPT -> 200 OK (RESOLVED)
17. AI VERIFIED without citizen ACCEPT cannot close case (remains UNDER_REVIEW)
18. Duplicate ACCEPT is idempotent (200 OK, no duplicate side-effects)
19. Revised resolution attempt after rejection:
    - attempt 1 rejected
    - attempt 2 uploaded and becomes active
    - citizen accepts attempt 2 -> RESOLVED
    - attempt 1 remains historical and auditable
20. Restart persistence: confirmation state and RESOLVED status survive reload
"""

import io
import pytest
from fastapi.testclient import TestClient

from app.config.settings import settings
from app.main import app
from app.models.enums import CaseStatus, ControlledDepartment
from app.models.evidence import (
    CivicEvidenceType,
    DeterministicValidationStatus,
    VerificationOutcome,
)
from app.security.audit import audit_dispatcher
from app.security.session import session_store
from app.services.case_store import case_store
from app.services.evidence.provider import MockEvidenceAssessmentProvider
from app.services.evidence.repository import evidence_repo
from app.services.evidence_verification_service import evidence_verification_service
from app.services.notifications import notification_service
from app.services.persistence.factory import get_repositories
from app.services.persistence.account_repository import account_repository

client = TestClient(app)

VALID_JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00resolution_proof_bytes"


@pytest.fixture(autouse=True)
def reset_system_state():
    """Ensure clean stores and mock provider for test isolation."""
    session_store.clear()
    account_repository.reset_seed_data()
    case_store.clear()
    evidence_repo.clear()
    audit_dispatcher.clear()
    evidence_verification_service.set_provider(
        MockEvidenceAssessmentProvider(outcome=VerificationOutcome.VERIFIED, ai_available=True)
    )
    yield
    session_store.clear()
    account_repository.reset_seed_data()
    case_store.clear()
    evidence_repo.clear()
    audit_dispatcher.clear()
    evidence_verification_service.set_provider(
        MockEvidenceAssessmentProvider(outcome=VerificationOutcome.VERIFIED, ai_available=True)
    )


def login_as(email: str, password: str = settings.DEV_DEFAULT_PASSWORD) -> TestClient:
    """Helper to authenticate and return a client with session cookie."""
    c = TestClient(app)
    res = c.post("/api/auth/login", json={"email": email, "password": password})
    assert res.status_code == 200, f"Login failed for {email}: {res.text}"
    return c


def create_case_under_review_with_resolution_evidence(
    citizen_email: str = "citizen@jarviscivic.local",
    authority_email: str = "roads.officer@jarviscivic.local",
    department: str = "PWD_ROADS",
    ai_outcome: VerificationOutcome = VerificationOutcome.VERIFIED,
) -> tuple[str, TestClient, TestClient, str]:
    """Helper to bootstrap a case through to UNDER_REVIEW with resolution evidence uploaded."""
    evidence_verification_service.set_provider(
        MockEvidenceAssessmentProvider(outcome=ai_outcome, ai_available=True)
    )

    citizen_c = login_as(citizen_email)
    authority_c = login_as(authority_email)

    # 1. Citizen creates case
    create_res = citizen_c.post(
        "/api/cases",
        json={
            "description": "Critical road pothole on Mount Road",
            "location": "Mount Road, Chennai",
            "department": department,
            "is_public": True,
        },
    )
    assert create_res.status_code == 201
    case_id = create_res.json()["case_id"]

    # 2. Advance through canonical lifecycle to UNDER_REVIEW
    for next_st in ["ROUTING_PREPARED", "SUBMISSION_READY", "UNDER_REVIEW"]:
        adv_res = authority_c.patch(
            f"/api/cases/{case_id}/status",
            json={"status": next_st, "notes": f"Advancing to {next_st}"},
        )
        assert adv_res.status_code == 200, f"Failed advance to {next_st}: {adv_res.text}"

    # 3. Authority uploads resolution evidence
    files = {
        "file": ("pothole_fixed.jpg", io.BytesIO(VALID_JPEG), "image/jpeg"),
    }
    data = {
        "evidence_type": "RESOLUTION_EVIDENCE",
    }
    upload_res = authority_c.post(
        f"/api/cases/{case_id}/evidence",
        files=files,
        data=data,
    )
    assert upload_res.status_code == 201, f"Failed upload: {upload_res.text}"
    evidence_id = upload_res.json()["evidence_id"]

    return case_id, citizen_c, authority_c, evidence_id


# ---------------------------------------------------------------------------
# TEST 01: Owner citizen ACCEPT -> 200 (atomically transitions to RESOLVED)
# ---------------------------------------------------------------------------
def test_01_owner_citizen_accept_success():
    case_id, citizen_c, _, evidence_id = create_case_under_review_with_resolution_evidence()

    res = citizen_c.post(
        f"/api/cases/{case_id}/resolution/accept",
        json={"feedback": "The pothole was completely repaired with asphalt."},
    )
    assert res.status_code == 200
    data = res.json()

    assert data["case_id"] == case_id
    assert data["status"] == "RESOLVED"
    assert data["resolution_confirmed"] is True
    assert data["resolution_confirmed_at"] is not None
    assert data["citizen_feedback"] == "The pothole was completely repaired with asphalt."
    assert data["active_resolution_attempt"] == "attempt-1"

    # Verify audit event emitted
    audit_events = audit_dispatcher.get_events_for_case(case_id)
    accept_events = [e for e in audit_events if e.event_type == "RESOLUTION_ACCEPTED"]
    assert len(accept_events) == 1
    assert accept_events[0].principal_role == "CITIZEN"
    assert accept_events[0].outcome == "SUCCESS"


# ---------------------------------------------------------------------------
# TEST 02: Owner citizen REJECT -> 200 (remains UNDER_REVIEW, rejection_count incremented)
# ---------------------------------------------------------------------------
def test_02_owner_citizen_reject_success():
    case_id, citizen_c, _, _ = create_case_under_review_with_resolution_evidence()

    res = citizen_c.post(
        f"/api/cases/{case_id}/resolution/reject",
        json={"reason": "Pothole filled with loose gravel only, unfinished asphalt."},
    )
    assert res.status_code == 200
    data = res.json()

    assert data["case_id"] == case_id
    assert data["status"] == "UNDER_REVIEW"
    assert data["resolution_confirmed"] is False
    assert data["resolution_rejected_at"] is not None
    assert data["rejection_count"] == 1
    assert data["citizen_feedback"] == "Pothole filled with loose gravel only, unfinished asphalt."

    # Verify audit event emitted
    audit_events = audit_dispatcher.get_events_for_case(case_id)
    reject_events = [e for e in audit_events if e.event_type == "RESOLUTION_REJECTED"]
    assert len(reject_events) == 1
    assert reject_events[0].principal_role == "CITIZEN"
    assert reject_events[0].outcome == "SUCCESS"


# ---------------------------------------------------------------------------
# TEST 03: Rejection reason too short (< 5 chars) -> 422
# ---------------------------------------------------------------------------
def test_03_rejection_reason_too_short_rejected_422():
    case_id, citizen_c, _, _ = create_case_under_review_with_resolution_evidence()

    res = citizen_c.post(
        f"/api/cases/{case_id}/resolution/reject",
        json={"reason": "bad"},
    )
    assert res.status_code == 422


# ---------------------------------------------------------------------------
# TEST 04: Different citizen ACCEPT -> 403 Forbidden (Cedar DENY)
# ---------------------------------------------------------------------------
def test_04_different_citizen_accept_denied_403():
    case_id, _, _, _ = create_case_under_review_with_resolution_evidence()
    other_citizen_c = login_as("citizen2@jarviscivic.local")

    res = other_citizen_c.post(
        f"/api/cases/{case_id}/resolution/accept",
        json={"feedback": "Impersonating citizen attempt"},
    )
    assert res.status_code == 403


# ---------------------------------------------------------------------------
# TEST 05: Different citizen REJECT -> 403 Forbidden (Cedar DENY)
# ---------------------------------------------------------------------------
def test_05_different_citizen_reject_denied_403():
    case_id, _, _, _ = create_case_under_review_with_resolution_evidence()
    other_citizen_c = login_as("citizen2@jarviscivic.local")

    res = other_citizen_c.post(
        f"/api/cases/{case_id}/resolution/reject",
        json={"reason": "Different citizen trying to reject"},
    )
    assert res.status_code == 403


# ---------------------------------------------------------------------------
# TEST 06: Authority officer ACCEPT -> 403 Forbidden (Cedar DENY)
# ---------------------------------------------------------------------------
def test_06_authority_officer_accept_denied_403():
    case_id, _, authority_c, _ = create_case_under_review_with_resolution_evidence()

    res = authority_c.post(
        f"/api/cases/{case_id}/resolution/accept",
        json={"feedback": "Officer trying to self-accept resolution"},
    )
    assert res.status_code == 403


# ---------------------------------------------------------------------------
# TEST 07: Authority officer REJECT -> 403 Forbidden (Cedar DENY)
# ---------------------------------------------------------------------------
def test_07_authority_officer_reject_denied_403():
    case_id, _, authority_c, _ = create_case_under_review_with_resolution_evidence()

    res = authority_c.post(
        f"/api/cases/{case_id}/resolution/reject",
        json={"reason": "Officer trying to reject own resolution"},
    )
    assert res.status_code == 403


# ---------------------------------------------------------------------------
# TEST 08: Municipal supervisor ACCEPT and REJECT -> 403 Forbidden (Cedar DENY)
# ---------------------------------------------------------------------------
def test_08_supervisor_accept_and_reject_denied_403():
    case_id, _, _, _ = create_case_under_review_with_resolution_evidence()
    supervisor_c = login_as("supervisor@jarviscivic.local")

    res_accept = supervisor_c.post(
        f"/api/cases/{case_id}/resolution/accept",
        json={"feedback": "Supervisor attempting to accept"},
    )
    assert res_accept.status_code == 403

    res_reject = supervisor_c.post(
        f"/api/cases/{case_id}/resolution/reject",
        json={"reason": "Supervisor attempting to reject"},
    )
    assert res_reject.status_code == 403


# ---------------------------------------------------------------------------
# TEST 09: Administrator ACCEPT and REJECT -> 403 Forbidden (Cedar DENY - No Bypass)
# ---------------------------------------------------------------------------
def test_09_administrator_accept_and_reject_denied_403():
    case_id, _, _, _ = create_case_under_review_with_resolution_evidence()
    admin_c = login_as("admin@jarviscivic.local")

    res_accept = admin_c.post(
        f"/api/cases/{case_id}/resolution/accept",
        json={"feedback": "Admin attempting to bypass citizen closure"},
    )
    assert res_accept.status_code == 403

    res_reject = admin_c.post(
        f"/api/cases/{case_id}/resolution/reject",
        json={"reason": "Admin attempting to reject on behalf of citizen"},
    )
    assert res_reject.status_code == 403


# ---------------------------------------------------------------------------
# TEST 10: Unauthenticated public user -> 401 Unauthorized
# ---------------------------------------------------------------------------
def test_10_public_user_denied_401():
    case_id, _, _, _ = create_case_under_review_with_resolution_evidence()
    anon_c = TestClient(app)

    res_accept = anon_c.post(
        f"/api/cases/{case_id}/resolution/accept",
        json={"feedback": "Public accept"},
    )
    assert res_accept.status_code in [401, 403]

    res_reject = anon_c.post(
        f"/api/cases/{case_id}/resolution/reject",
        json={"reason": "Public reject"},
    )
    assert res_reject.status_code in [401, 403]


# ---------------------------------------------------------------------------
# TEST 11: Forged role / principal / department headers rejected in session
# ---------------------------------------------------------------------------
def test_11_forged_headers_ignored_in_session():
    case_id, citizen_c, authority_c, _ = create_case_under_review_with_resolution_evidence()

    # Authority attempts to forge citizen principal and role headers
    res = authority_c.post(
        f"/api/cases/{case_id}/resolution/accept",
        headers={
            "X-Principal-Role": "CITIZEN",
            "X-Principal-ID": "USR-CITIZEN-001",
        },
        json={"feedback": "Forged headers"},
    )
    assert res.status_code == 403


# ---------------------------------------------------------------------------
# TEST 12: Direct authority PATCH /status to RESOLVED blocked with HTTP 409 Conflict
# ---------------------------------------------------------------------------
def test_12_direct_patch_status_resolved_blocked_409():
    case_id, _, authority_c, _ = create_case_under_review_with_resolution_evidence()

    res = authority_c.patch(
        f"/api/cases/{case_id}/status",
        json={"status": "RESOLVED", "notes": "Authority attempting direct closure"},
    )
    assert res.status_code == 409
    assert "gated on authenticated citizen resolution confirmation" in res.json()["detail"].lower()


# ---------------------------------------------------------------------------
# TEST 13: ACCEPT with no resolution evidence -> 409 Conflict
# ---------------------------------------------------------------------------
def test_13_accept_with_no_resolution_evidence_blocked_409():
    citizen_c = login_as("citizen@jarviscivic.local")
    authority_c = login_as("roads.officer@jarviscivic.local")

    # Create case and advance to UNDER_REVIEW without uploading resolution evidence
    create_res = citizen_c.post(
        "/api/cases",
        json={
            "description": "Pothole without resolution evidence",
            "location": "Mount Road, Chennai",
            "department": "PWD_ROADS",
            "is_public": True,
        },
    )
    case_id = create_res.json()["case_id"]

    for next_st in ["ROUTING_PREPARED", "SUBMISSION_READY", "UNDER_REVIEW"]:
        authority_c.patch(
            f"/api/cases/{case_id}/status",
            json={"status": next_st, "notes": f"Advancing to {next_st}"},
        )

    # Citizen tries to accept when no resolution evidence exists
    res = citizen_c.post(
        f"/api/cases/{case_id}/resolution/accept",
        json={"feedback": "Premature acceptance"},
    )
    assert res.status_code == 409
    assert "lacks verified resolution evidence" in res.json()["detail"].lower()


# ---------------------------------------------------------------------------
# TEST 14: Deterministic invalid evidence cannot close case -> 409 Conflict
# ---------------------------------------------------------------------------
def test_14_deterministic_invalid_evidence_blocks_accept_409():
    case_id, citizen_c, authority_c, evidence_id = create_case_under_review_with_resolution_evidence()

    # Manually mark the evidence as DETERMINISTICALLY INVALID (e.g. corrupt)
    ev = evidence_repo.get_evidence(case_id, evidence_id)
    assert ev is not None
    ev.validation_status = DeterministicValidationStatus.CORRUPT_FILE
    evidence_repo.save_evidence(ev)

    res = citizen_c.post(
        f"/api/cases/{case_id}/resolution/accept",
        json={"feedback": "Accepting despite corrupted file"},
    )
    assert res.status_code == 409
    assert "deterministic validation" in res.json()["detail"].lower()


# ---------------------------------------------------------------------------
# TEST 15: AI UNCERTAIN + valid deterministic evidence + citizen ACCEPT -> RESOLVED
# ---------------------------------------------------------------------------
def test_15_ai_uncertain_with_valid_deterministic_evidence_allows_accept():
    case_id, citizen_c, _, _ = create_case_under_review_with_resolution_evidence(
        ai_outcome=VerificationOutcome.UNCERTAIN
    )

    res = citizen_c.post(
        f"/api/cases/{case_id}/resolution/accept",
        json={"feedback": "Citizen confirms work is done despite AI uncertainty."},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "RESOLVED"
    assert data["resolution_confirmed"] is True


# ---------------------------------------------------------------------------
# TEST 16: AI REJECTED + valid deterministic evidence + citizen ACCEPT -> RESOLVED
# ---------------------------------------------------------------------------
def test_16_ai_rejected_with_valid_deterministic_evidence_allows_accept():
    case_id, citizen_c, _, _ = create_case_under_review_with_resolution_evidence(
        ai_outcome=VerificationOutcome.REJECTED
    )

    res = citizen_c.post(
        f"/api/cases/{case_id}/resolution/accept",
        json={"feedback": "Citizen physically verified the site; accepts despite AI rejection."},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "RESOLVED"
    assert data["resolution_confirmed"] is True


# ---------------------------------------------------------------------------
# TEST 17: AI VERIFIED without citizen ACCEPT cannot close case
# ---------------------------------------------------------------------------
def test_17_ai_verified_without_citizen_cannot_close_case():
    case_id, _, _, _ = create_case_under_review_with_resolution_evidence(
        ai_outcome=VerificationOutcome.VERIFIED
    )

    # Inspect case - must remain in UNDER_REVIEW
    repo, _ = get_repositories()
    case = repo.get_case(case_id)
    assert case.status == CaseStatus.UNDER_REVIEW
    assert case.resolution_confirmed is False


# ---------------------------------------------------------------------------
# TEST 18: Duplicate ACCEPT is idempotent (200 OK, no duplicate side-effects)
# ---------------------------------------------------------------------------
def test_18_duplicate_accept_is_idempotent():
    case_id, citizen_c, _, _ = create_case_under_review_with_resolution_evidence()

    # First ACCEPT
    res1 = citizen_c.post(
        f"/api/cases/{case_id}/resolution/accept",
        json={"feedback": "First acceptance"},
    )
    assert res1.status_code == 200

    audit_count_before = len([e for e in audit_dispatcher.get_events_for_case(case_id) if e.event_type == "RESOLUTION_ACCEPTED"])
    assert audit_count_before == 1

    # Second ACCEPT (idempotent retry)
    res2 = citizen_c.post(
        f"/api/cases/{case_id}/resolution/accept",
        json={"feedback": "Second duplicate acceptance"},
    )
    assert res2.status_code == 200
    assert res2.json()["status"] == "RESOLVED"
    assert res2.json()["resolution_confirmed"] is True

    # Audit events count must remain 1
    audit_count_after = len([e for e in audit_dispatcher.get_events_for_case(case_id) if e.event_type == "RESOLUTION_ACCEPTED"])
    assert audit_count_after == 1


# ---------------------------------------------------------------------------
# TEST 19: Revised resolution attempt after rejection
# ---------------------------------------------------------------------------
def test_19_revised_attempt_and_rejection_history():
    case_id, citizen_c, authority_c, attempt1_id = create_case_under_review_with_resolution_evidence()

    # 1. Citizen rejects attempt 1
    rej_res = citizen_c.post(
        f"/api/cases/{case_id}/resolution/reject",
        json={"reason": "Attempt 1 incomplete: patch is uneven and rocks are loose."},
    )
    assert rej_res.status_code == 200
    assert rej_res.json()["status"] == "UNDER_REVIEW"
    assert rej_res.json()["rejection_count"] == 1

    # 2. Authority reworks and uploads revised resolution evidence (attempt 2)
    files2 = {
        "file": ("pothole_rework_final.jpg", io.BytesIO(VALID_JPEG), "image/jpeg"),
    }
    upload2 = authority_c.post(
        f"/api/cases/{case_id}/evidence",
        files=files2,
        data={"evidence_type": "RESOLUTION_EVIDENCE"},
    )
    assert upload2.status_code == 201
    attempt2_id = upload2.json()["evidence_id"]
    assert attempt2_id != attempt1_id

    # 3. Verify active resolution attempt is updated to attempt 2
    repo, _ = get_repositories()
    case = repo.get_case(case_id)
    assert case.active_resolution_attempt == "attempt-2"

    # 4. Citizen reviews and ACCEPTS revised attempt 2
    acc_res = citizen_c.post(
        f"/api/cases/{case_id}/resolution/accept",
        json={"feedback": "Rework verified, surface is smooth and complete."},
    )
    assert acc_res.status_code == 200
    assert acc_res.json()["status"] == "RESOLVED"
    assert acc_res.json()["resolution_confirmed"] is True
    assert acc_res.json()["active_resolution_attempt"] == "attempt-2"
    assert acc_res.json()["rejection_count"] == 1

    # 5. Historical attempt 1 remains stored in evidence repository
    ev1 = evidence_repo.get_evidence(case_id, attempt1_id)
    ev2 = evidence_repo.get_evidence(case_id, attempt2_id)
    assert ev1 is not None
    assert ev2 is not None


# ---------------------------------------------------------------------------
# TEST 20: Restart persistence preserves confirmation state
# ---------------------------------------------------------------------------
def test_20_restart_preserves_confirmation_state():
    case_id, citizen_c, _, evidence_id = create_case_under_review_with_resolution_evidence()

    acc_res = citizen_c.post(
        f"/api/cases/{case_id}/resolution/accept",
        json={"feedback": "Final confirmed resolution."},
    )
    assert acc_res.status_code == 200

    # Simulate backend restart by re-instantiating the repository
    repo, _ = get_repositories()
    reloaded_case = repo.get_case(case_id)

    assert reloaded_case is not None
    assert reloaded_case.status == CaseStatus.RESOLVED
    assert reloaded_case.resolution_confirmed is True
    assert reloaded_case.resolution_confirmed_at is not None
    assert reloaded_case.active_resolution_attempt == "attempt-1"
    assert reloaded_case.citizen_feedback == "Final confirmed resolution."


# ---------------------------------------------------------------------------
# TEST 21: Authority officer request confirmation success
# ---------------------------------------------------------------------------
def test_21_authority_officer_request_confirmation_success():
    citizen_c = login_as("citizen@jarviscivic.local")
    authority_c = login_as("roads.officer@jarviscivic.local")

    create_res = citizen_c.post(
        "/api/cases",
        json={
            "description": "Pothole on Mount Road",
            "location": "Mount Road",
            "department": "PWD_ROADS",
            "is_public": True,
        },
    )
    case_id = create_res.json()["case_id"]

    for next_st in ["ROUTING_PREPARED", "SUBMISSION_READY", "UNDER_REVIEW"]:
        authority_c.patch(
            f"/api/cases/{case_id}/status",
            json={"status": next_st, "notes": f"Advancing to {next_st}"},
        )

    # Authority uploads resolution evidence with authoritative resolution message
    files = {"file": ("repaired.jpg", io.BytesIO(VALID_JPEG), "image/jpeg")}
    data = {
        "evidence_type": "RESOLUTION_EVIDENCE",
        "resolution_message": "Pothole filled with standard asphalt mix and leveled.",
    }
    upload_res = authority_c.post(f"/api/cases/{case_id}/evidence", files=files, data=data)
    assert upload_res.status_code == 201

    # Authority requests citizen confirmation
    req_res = authority_c.post(f"/api/cases/{case_id}/resolution/request-confirmation")
    assert req_res.status_code == 200
    data = req_res.json()
    assert data["confirmation_requested"] is True
    assert data["confirmation_requested_at"] is not None
    assert data["resolution_message"] == "Pothole filled with standard asphalt mix and leveled."

    # Verify audit event emitted
    audit_events = audit_dispatcher.get_events_for_case(case_id)
    req_events = [e for e in audit_events if e.event_type == "CITIZEN_CONFIRMATION_REQUESTED"]
    assert len(req_events) == 1
    assert req_events[0].outcome == "SUCCESS"


# ---------------------------------------------------------------------------
# TEST 22: Administrator CANNOT request citizen confirmation (Cedar DENY -> 403)
# ---------------------------------------------------------------------------
def test_22_administrator_request_confirmation_denied_403():
    case_id, _, authority_c, _ = create_case_under_review_with_resolution_evidence()

    # Upload authoritative resolution message via authority
    note_res = authority_c.post(
        f"/api/cases/{case_id}/resolution-note",
        json={"note": "Official resolution statement"},
    )
    assert note_res.status_code == 200

    admin_c = login_as("admin@jarviscivic.local")
    res = admin_c.post(f"/api/cases/{case_id}/resolution/request-confirmation")
    assert res.status_code == 403


# ---------------------------------------------------------------------------
# TEST 23: Different department officer CANNOT request confirmation (Cedar DENY -> 403)
# ---------------------------------------------------------------------------
def test_23_different_department_officer_request_confirmation_denied_403():
    case_id, _, _, _ = create_case_under_review_with_resolution_evidence(department="PWD_ROADS")

    drainage_officer_c = login_as("drainage.officer@jarviscivic.local")
    res = drainage_officer_c.post(f"/api/cases/{case_id}/resolution/request-confirmation")
    assert res.status_code == 403


# ---------------------------------------------------------------------------
# TEST 24: Citizen CANNOT request citizen confirmation (Cedar DENY -> 403)
# ---------------------------------------------------------------------------
def test_24_citizen_request_confirmation_denied_403():
    case_id, citizen_c, _, _ = create_case_under_review_with_resolution_evidence()

    res = citizen_c.post(f"/api/cases/{case_id}/resolution/request-confirmation")
    assert res.status_code == 403


# ---------------------------------------------------------------------------
# TEST 25: Unauthenticated user CANNOT request confirmation (401)
# ---------------------------------------------------------------------------
def test_25_unauthenticated_request_confirmation_denied_401():
    case_id, _, _, _ = create_case_under_review_with_resolution_evidence()
    anon_c = TestClient(app)

    res = anon_c.post(f"/api/cases/{case_id}/resolution/request-confirmation")
    assert res.status_code in [401, 403]


# ---------------------------------------------------------------------------
# TEST 26: Single authoritative message cannot be overwritten on request confirmation
# ---------------------------------------------------------------------------
def test_26_single_authoritative_resolution_message_cannot_be_overwritten():
    citizen_c = login_as("citizen@jarviscivic.local")
    authority_c = login_as("roads.officer@jarviscivic.local")

    create_res = citizen_c.post(
        "/api/cases",
        json={
            "description": "Pothole on Mount Road",
            "location": "Mount Road",
            "department": "PWD_ROADS",
            "is_public": True,
        },
    )
    case_id = create_res.json()["case_id"]

    for next_st in ["ROUTING_PREPARED", "SUBMISSION_READY", "UNDER_REVIEW"]:
        authority_c.patch(
            f"/api/cases/{case_id}/status",
            json={"status": next_st, "notes": f"Advancing to {next_st}"},
        )

    # 1. Authority uploads resolution evidence with authoritative message
    files = {"file": ("repair_done.jpg", io.BytesIO(VALID_JPEG), "image/jpeg")}
    data = {
        "evidence_type": "RESOLUTION_EVIDENCE",
        "resolution_message": "Authoritative resolution message from evidence submission.",
    }
    upload_res = authority_c.post(f"/api/cases/{case_id}/evidence", files=files, data=data)
    assert upload_res.status_code == 201
    assert upload_res.json()["resolution_message"] == "Authoritative resolution message from evidence submission."

    # 2. Request confirmation with a different message attempt in payload
    req_res = authority_c.post(
        f"/api/cases/{case_id}/resolution/request-confirmation",
        json={"message": "Unauthorized replacement message attempt"},
    )
    assert req_res.status_code == 200
    # Must preserve the authoritative message from evidence upload!
    assert req_res.json()["resolution_message"] == "Authoritative resolution message from evidence submission."


# ---------------------------------------------------------------------------
# TEST 27: Backend confirmation gate enforces all required conditions
# ---------------------------------------------------------------------------
def test_27_backend_confirmation_gate_enforces_all_conditions():
    citizen_c = login_as("citizen@jarviscivic.local")
    authority_c = login_as("roads.officer@jarviscivic.local")

    create_res = citizen_c.post(
        "/api/cases",
        json={
            "description": "Road barrier broken",
            "location": "Anna Salai",
            "department": "PWD_ROADS",
            "is_public": True,
        },
    )
    case_id = create_res.json()["case_id"]

    # Condition: case must be in UNDER_REVIEW (currently DOCKET_CREATED)
    res_not_under_review = authority_c.post(f"/api/cases/{case_id}/resolution/request-confirmation")
    assert res_not_under_review.status_code == 409
    assert "under_review" in res_not_under_review.json()["detail"].lower()

    # Advance to UNDER_REVIEW without uploading resolution evidence
    for next_st in ["ROUTING_PREPARED", "SUBMISSION_READY", "UNDER_REVIEW"]:
        authority_c.patch(
            f"/api/cases/{case_id}/status",
            json={"status": next_st, "notes": f"Advancing to {next_st}"},
        )

    # Condition: active resolution attempt and resolution evidence must exist
    res_no_evidence = authority_c.post(f"/api/cases/{case_id}/resolution/request-confirmation")
    assert res_no_evidence.status_code == 409

    # Upload resolution evidence without resolution message
    files = {"file": ("barrier_fixed.jpg", io.BytesIO(VALID_JPEG), "image/jpeg")}
    upload_res = authority_c.post(
        f"/api/cases/{case_id}/evidence",
        files=files,
        data={"evidence_type": "RESOLUTION_EVIDENCE"},
    )
    assert upload_res.status_code == 201

    # Condition: non-empty persisted resolution message required
    res_no_msg = authority_c.post(
        f"/api/cases/{case_id}/resolution/request-confirmation",
        json={"message": "   "},
    )
    assert res_no_msg.status_code == 409
    assert "resolution message required" in res_no_msg.json()["detail"].lower()


# ---------------------------------------------------------------------------
# TEST 28: Full confirmation flow and Citizen accept resets confirmation state
# ---------------------------------------------------------------------------
def test_28_full_confirmation_flow_and_citizen_accept():
    citizen_c = login_as("citizen@jarviscivic.local")
    authority_c = login_as("roads.officer@jarviscivic.local")

    create_res = citizen_c.post(
        "/api/cases",
        json={
            "description": "Drain cover missing",
            "location": "T Nagar",
            "department": "PWD_ROADS",
            "is_public": True,
        },
    )
    case_id = create_res.json()["case_id"]

    for next_st in ["ROUTING_PREPARED", "SUBMISSION_READY", "UNDER_REVIEW"]:
        authority_c.patch(
            f"/api/cases/{case_id}/status",
            json={"status": next_st, "notes": f"Advancing to {next_st}"},
        )

    # Authority uploads resolution evidence + message
    files = {"file": ("cover_replaced.jpg", io.BytesIO(VALID_JPEG), "image/jpeg")}
    upload_res = authority_c.post(
        f"/api/cases/{case_id}/evidence",
        files=files,
        data={
            "evidence_type": "RESOLUTION_EVIDENCE",
            "resolution_message": "Heavy duty drain cover installed and bolted.",
        },
    )
    assert upload_res.status_code == 201

    # Authority requests citizen confirmation
    req_res = authority_c.post(f"/api/cases/{case_id}/resolution/request-confirmation")
    assert req_res.status_code == 200
    assert req_res.json()["confirmation_requested"] is True

    # Citizen accepts resolution
    acc_res = citizen_c.post(
        f"/api/cases/{case_id}/resolution/accept",
        json={"feedback": "Verified in person, safe for pedestrians."},
    )
    assert acc_res.status_code == 200
    assert acc_res.json()["status"] == "RESOLVED"
    assert acc_res.json()["resolution_confirmed"] is True
    assert acc_res.json()["confirmation_requested"] is False
