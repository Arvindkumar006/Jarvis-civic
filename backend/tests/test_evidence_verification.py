"""Comprehensive Tests for JARVIS Civic Phase 8.7 Evidence Verification Architecture.

Verifies:
1. Citizen uploads valid case evidence
2. Citizen attempts another citizen's case (Cedar DENY -> HTTP 403)
3. Authority uploads valid resolution evidence (in assigned department)
4. Authority attempts another department's case (Cedar DENY -> HTTP 403)
5. Forged role header ignored in authenticated session
6. Forged department header ignored in authenticated session
7. Invalid session rejected with HTTP 401
8. Invalid MIME type rejected with HTTP 400
9. MIME/magic-byte mismatch rejected with HTTP 400
10. Wrong file extension rejected with HTTP 400
11. Oversized file rejected (>10MB -> HTTP 413)
12. Corrupt / empty file rejected with HTTP 400
13. Malicious filename / path traversal sanitized server-side
14. Client attempts to submit VERIFIED status (calculated server-side)
15. Client attempts to submit another uploader identity (derived from principal)
16. Client attempts to submit another department (derived from principal)
17. AI unavailable returns safe UNCERTAIN outcome with ai_available=False
18. AI malformed response returns safe UNCERTAIN outcome
19. AI returns UNCERTAIN on ambiguous evidence
20. AI returns REJECTED on contradictory evidence (case not resolved)
21. Rejected evidence is not exposed as trusted evidence
22. Public cannot read private evidence (HTTP 401 / 403)
23. Audit identity comes from authenticated principal
24. Notification only occurs after validated persistence
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
    EvidenceType,
    VerificationOutcome,
)
from app.security.audit import audit_dispatcher
from app.security.session import session_store
from app.services.case_store import case_store
from app.services.evidence.provider import (
    DeterministicFallbackProvider,
    MockEvidenceAssessmentProvider,
)
from app.services.evidence.repository import evidence_repo
from app.services.evidence_verification_service import evidence_verification_service
from app.services.notifications import notification_service
from app.services.persistence.account_repository import account_repository

client = TestClient(app)

# Real valid binary headers
VALID_JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00valid_jpeg_payload"
VALID_PNG = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
VALID_PDF = b"%PDF-1.5\n%\xe2\xe3\xcf\xd3\n"
VALID_TXT = b"This is a valid text evidence file."


@pytest.fixture(autouse=True)
def reset_system_state():
    """Ensure clean stores and mock provider for test isolation."""
    session_store.clear()
    account_repository.reset_seed_data()
    case_store.clear()
    evidence_repo.clear()
    audit_dispatcher.clear()
    # Reset to deterministic mock provider for testing
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


# ---------------------------------------------------------------------------
# TEST 1: Citizen uploads valid case evidence
# ---------------------------------------------------------------------------
def test_01_citizen_uploads_valid_case_evidence():
    citizen_client = login_as("citizen@jarviscivic.local")

    # Create a case
    create_res = citizen_client.post(
        "/api/cases",
        json={
            "description": "Deep pothole causing vehicle damage",
            "location": "Anna Salai, Chennai",
            "department": "PWD_ROADS",
            "is_public": True,
        },
    )
    assert create_res.status_code == 201
    case_id = create_res.json()["case_id"]

    # Upload valid JPEG case evidence
    files = {"file": ("pothole.jpg", io.BytesIO(VALID_JPEG), "image/jpeg")}
    upload_res = citizen_client.post(f"/api/cases/{case_id}/evidence", files=files)
    assert upload_res.status_code == 201
    data = upload_res.json()

    assert data["case_id"] == case_id
    assert data["evidence_type"] == EvidenceType.CASE_EVIDENCE.value
    assert data["filename"] == "pothole.jpg"
    assert data["content_type"] == "image/jpeg"
    assert len(data["sha256"]) == 64
    assert data["validation_status"] == DeterministicValidationStatus.VALID.value
    assert data["verification_status"] == VerificationOutcome.VERIFIED.value

    # Verify evidence persists in evidence list
    list_res = citizen_client.get(f"/api/cases/{case_id}/evidence")
    assert list_res.status_code == 200
    evidence_list = list_res.json()
    assert len(evidence_list) == 1
    assert evidence_list[0]["evidence_id"] == data["evidence_id"]


# ---------------------------------------------------------------------------
# TEST 2: Citizen attempts another citizen's case
# ---------------------------------------------------------------------------
def test_02_citizen_attempts_another_citizens_case():
    alice = login_as("citizen@jarviscivic.local")  # citizen-01

    # Alice creates a case
    create_res = alice.post(
        "/api/cases",
        json={
            "description": "Streetlight broken on 4th cross",
            "location": "Mylapore",
            "department": "ELECTRICITY_UTILITY",
            "is_public": True,
        },
    )
    case_id = create_res.json()["case_id"]

    # Bob attempts to upload evidence to Alice's case
    bob = TestClient(app)
    files = {"file": ("bob_proof.jpg", io.BytesIO(VALID_JPEG), "image/jpeg")}
    headers = {"X-Principal-Id": "citizen-bob", "X-Principal-Role": "CITIZEN"}
    upload_res = bob.post(f"/api/cases/{case_id}/evidence", files=files, headers=headers)

    # Cedar DENY -> HTTP 403 Forbidden
    assert upload_res.status_code == 403
    assert "Authorization denied" in upload_res.json()["detail"]


# ---------------------------------------------------------------------------
# TEST 3: Authority uploads valid resolution evidence
# ---------------------------------------------------------------------------
def test_03_authority_uploads_valid_resolution_evidence():
    citizen = login_as("citizen@jarviscivic.local")
    roads_officer = login_as("roads.officer@jarviscivic.local")  # PWD_ROADS

    # Citizen creates road defect case
    create_res = citizen.post(
        "/api/cases",
        json={
            "description": "Road crater near flyover",
            "location": "Guindy",
            "department": "PWD_ROADS",
            "is_public": True,
        },
    )
    case_id = create_res.json()["case_id"]

    # Authority officer uploads resolution evidence
    files = {"file": ("repair_done.jpg", io.BytesIO(VALID_JPEG), "image/jpeg")}
    data = {
        "evidence_type": EvidenceType.RESOLUTION_EVIDENCE.value,
        "resolution_attempt": "repair-patch-phase1",
    }
    upload_res = roads_officer.post(f"/api/cases/{case_id}/evidence", files=files, data=data)
    assert upload_res.status_code == 201
    resp_data = upload_res.json()

    assert resp_data["evidence_type"] == EvidenceType.RESOLUTION_EVIDENCE.value
    assert resp_data["resolution_attempt"] == "repair-patch-phase1"
    assert resp_data["verification_status"] == VerificationOutcome.VERIFIED.value

    # Invariant: Resolution evidence exists, but case is NOT automatically marked RESOLVED
    case_res = roads_officer.get(f"/api/cases/{case_id}")
    case_data = case_res.json()
    assert case_data["status"] != CaseStatus.RESOLVED.value


# ---------------------------------------------------------------------------
# TEST 4: Authority attempts another department's case
# ---------------------------------------------------------------------------
def test_04_authority_attempts_another_departments_case():
    citizen = login_as("citizen@jarviscivic.local")
    drainage_officer = login_as("officer@jarviscivic.local")  # DRAINAGE_STORMWATER

    # Case belongs to PWD_ROADS
    create_res = citizen.post(
        "/api/cases",
        json={
            "description": "Road surface collapsed",
            "location": "T Nagar",
            "department": "PWD_ROADS",
            "is_public": True,
        },
    )
    case_id = create_res.json()["case_id"]

    # Drainage officer attempts to upload resolution evidence to Roads case
    files = {"file": ("drainage_repair.jpg", io.BytesIO(VALID_JPEG), "image/jpeg")}
    data = {"evidence_type": EvidenceType.RESOLUTION_EVIDENCE.value}
    upload_res = drainage_officer.post(f"/api/cases/{case_id}/evidence", files=files, data=data)

    # Cedar DENY -> HTTP 403 Forbidden
    assert upload_res.status_code == 403
    assert "Authorization denied" in upload_res.json()["detail"]


# ---------------------------------------------------------------------------
# TEST 5: Forged role header
# ---------------------------------------------------------------------------
def test_05_forged_role_header_ignored():
    citizen = login_as("citizen@jarviscivic.local")

    create_res = citizen.post(
        "/api/cases",
        json={
            "description": "Clogged drain overflowing",
            "location": "Adyar",
            "department": "DRAINAGE_STORMWATER",
            "is_public": True,
        },
    )
    case_id = create_res.json()["case_id"]

    # Citizen tries to forge Administrator or Officer role header to submit resolution evidence
    files = {"file": ("forged.jpg", io.BytesIO(VALID_JPEG), "image/jpeg")}
    data = {"evidence_type": EvidenceType.RESOLUTION_EVIDENCE.value}
    headers = {
        "X-Principal-Role": "ADMINISTRATOR",
        "X-Principal-Department": "DRAINAGE_STORMWATER",
    }
    upload_res = citizen.post(f"/api/cases/{case_id}/evidence", files=files, data=data, headers=headers)

    # Must be DENIED: Session role is CITIZEN, and citizen cannot add_resolution_evidence
    assert upload_res.status_code == 403


# ---------------------------------------------------------------------------
# TEST 6: Forged department header
# ---------------------------------------------------------------------------
def test_06_forged_department_header_ignored():
    drainage_officer = login_as("officer@jarviscivic.local")  # DRAINAGE_STORMWATER

    citizen = login_as("citizen@jarviscivic.local")
    create_res = citizen.post(
        "/api/cases",
        json={
            "description": "Broken streetlight post",
            "location": "Besant Nagar",
            "department": "ELECTRICITY_UTILITY",
            "is_public": True,
        },
    )
    case_id = create_res.json()["case_id"]

    # Drainage officer sends X-Principal-Department: ELECTRICITY_UTILITY
    files = {"file": ("fix.jpg", io.BytesIO(VALID_JPEG), "image/jpeg")}
    data = {"evidence_type": EvidenceType.RESOLUTION_EVIDENCE.value}
    headers = {"X-Principal-Department": "ELECTRICITY_UTILITY"}
    upload_res = drainage_officer.post(f"/api/cases/{case_id}/evidence", files=files, data=data, headers=headers)

    # Must be DENIED: Server derives department from authenticated session
    assert upload_res.status_code == 403


# ---------------------------------------------------------------------------
# TEST 7: Invalid session
# ---------------------------------------------------------------------------
def test_07_invalid_session_rejected_with_401():
    citizen = login_as("citizen@jarviscivic.local")
    create_res = citizen.post(
        "/api/cases",
        json={"description": "Test issue", "location": "Chennai", "department": "PWD_ROADS"},
    )
    case_id = create_res.json()["case_id"]

    unauth_client = TestClient(app)
    unauth_client.cookies.set(settings.AUTH_COOKIE_NAME, "invalid-expired-token-12345")

    files = {"file": ("test.jpg", io.BytesIO(VALID_JPEG), "image/jpeg")}
    upload_res = unauth_client.post(f"/api/cases/{case_id}/evidence", files=files)
    assert upload_res.status_code == 401


# ---------------------------------------------------------------------------
# TEST 8: Invalid MIME type
# ---------------------------------------------------------------------------
def test_08_invalid_mime_type_rejected():
    citizen = login_as("citizen@jarviscivic.local")
    create_res = citizen.post(
        "/api/cases",
        json={"description": "Test issue", "location": "Chennai", "department": "PWD_ROADS"},
    )
    case_id = create_res.json()["case_id"]

    # Upload with disallowed MIME type
    files = {"file": ("script.sh", io.BytesIO(b"#!/bin/bash\necho hello"), "application/x-sh")}
    upload_res = citizen.post(f"/api/cases/{case_id}/evidence", files=files)
    assert upload_res.status_code == 400
    assert "Content-Type" in upload_res.json()["detail"] or "extension" in upload_res.json()["detail"].lower()


# ---------------------------------------------------------------------------
# TEST 9: MIME / Magic-byte mismatch
# ---------------------------------------------------------------------------
def test_09_mime_magic_byte_mismatch_rejected():
    citizen = login_as("citizen@jarviscivic.local")
    create_res = citizen.post(
        "/api/cases",
        json={"description": "Test issue", "location": "Chennai", "department": "PWD_ROADS"},
    )
    case_id = create_res.json()["case_id"]

    # Disguise plain text or PE executable header as .jpg
    fake_jpg = b"MZ\x90\x00\x03\x00\x00\x00This is a Windows executable binary disguised as a picture"
    files = {"file": ("innocent.jpg", io.BytesIO(fake_jpg), "image/jpeg")}
    upload_res = citizen.post(f"/api/cases/{case_id}/evidence", files=files)
    assert upload_res.status_code == 400
    assert "magic signature" in upload_res.json()["detail"].lower()


# ---------------------------------------------------------------------------
# TEST 10: Wrong file extension
# ---------------------------------------------------------------------------
def test_10_wrong_file_extension_rejected():
    citizen = login_as("citizen@jarviscivic.local")
    create_res = citizen.post(
        "/api/cases",
        json={"description": "Test issue", "location": "Chennai", "department": "PWD_ROADS"},
    )
    case_id = create_res.json()["case_id"]

    # Executable extension with binary content
    files = {"file": ("malware.exe", io.BytesIO(b"MZ\x90\x00executable"), "application/octet-stream")}
    upload_res = citizen.post(f"/api/cases/{case_id}/evidence", files=files)
    assert upload_res.status_code == 400
    assert "not supported" in upload_res.json()["detail"].lower() or "not permitted" in upload_res.json()["detail"].lower()


# ---------------------------------------------------------------------------
# TEST 11: Oversized file
# ---------------------------------------------------------------------------
def test_11_oversized_file_rejected():
    citizen = login_as("citizen@jarviscivic.local")
    create_res = citizen.post(
        "/api/cases",
        json={"description": "Test issue", "location": "Chennai", "department": "PWD_ROADS"},
    )
    case_id = create_res.json()["case_id"]

    # 11MB file exceeds 10MB limit
    oversized = VALID_JPEG + b"0" * (11 * 1024 * 1024)
    files = {"file": ("large.jpg", io.BytesIO(oversized), "image/jpeg")}
    upload_res = citizen.post(f"/api/cases/{case_id}/evidence", files=files)
    assert upload_res.status_code == 413
    assert "exceeds maximum limit" in upload_res.json()["detail"]


# ---------------------------------------------------------------------------
# TEST 12: Corrupt / empty file
# ---------------------------------------------------------------------------
def test_12_corrupt_or_empty_file_rejected():
    citizen = login_as("citizen@jarviscivic.local")
    create_res = citizen.post(
        "/api/cases",
        json={"description": "Test issue", "location": "Chennai", "department": "PWD_ROADS"},
    )
    case_id = create_res.json()["case_id"]

    # Empty 0-byte file
    files = {"file": ("empty.jpg", io.BytesIO(b""), "image/jpeg")}
    upload_res = citizen.post(f"/api/cases/{case_id}/evidence", files=files)
    assert upload_res.status_code == 400
    assert "empty" in upload_res.json()["detail"].lower()


# ---------------------------------------------------------------------------
# TEST 13: Malicious filename / path traversal sanitized
# ---------------------------------------------------------------------------
def test_13_malicious_filename_path_traversal_sanitized():
    citizen = login_as("citizen@jarviscivic.local")
    create_res = citizen.post(
        "/api/cases",
        json={"description": "Test issue", "location": "Chennai", "department": "PWD_ROADS"},
    )
    case_id = create_res.json()["case_id"]

    # Attempt path traversal in filename
    traversal_name = "../../../../../etc/passwd.jpg"
    files = {"file": (traversal_name, io.BytesIO(VALID_JPEG), "image/jpeg")}
    upload_res = citizen.post(f"/api/cases/{case_id}/evidence", files=files)
    assert upload_res.status_code == 201
    saved_name = upload_res.json()["filename"]

    # Path traversal must be stripped to safe basename
    assert "/" not in saved_name
    assert ".." not in saved_name
    assert saved_name == "passwd.jpg"


# ---------------------------------------------------------------------------
# TEST 14: Client attempts to submit VERIFIED status directly
# ---------------------------------------------------------------------------
def test_14_client_cannot_spoof_verification_status():
    citizen = login_as("citizen@jarviscivic.local")
    create_res = citizen.post(
        "/api/cases",
        json={"description": "Test issue", "location": "Chennai", "department": "PWD_ROADS"},
    )
    case_id = create_res.json()["case_id"]

    # Mock provider configured to return UNCERTAIN
    evidence_verification_service.set_provider(
        MockEvidenceAssessmentProvider(outcome=VerificationOutcome.UNCERTAIN, ai_available=True)
    )

    # Client tries to send {"verification_status": "VERIFIED"}
    files = {"file": ("pothole.jpg", io.BytesIO(VALID_JPEG), "image/jpeg")}
    data = {"verification_status": "VERIFIED", "ai_confidence": 1.0}
    upload_res = citizen.post(f"/api/cases/{case_id}/evidence", files=files, data=data)
    assert upload_res.status_code == 201

    # Server must ignore client's claimed status and return the authoritative server evaluation (UNCERTAIN)
    assert upload_res.json()["verification_status"] == VerificationOutcome.UNCERTAIN.value


# ---------------------------------------------------------------------------
# TEST 15: Client attempts to submit another uploader identity
# ---------------------------------------------------------------------------
def test_15_client_cannot_spoof_uploader_identity():
    citizen = login_as("citizen@jarviscivic.local")  # citizen-01
    create_res = citizen.post(
        "/api/cases",
        json={"description": "Test issue", "location": "Chennai", "department": "PWD_ROADS"},
    )
    case_id = create_res.json()["case_id"]

    # Client tries to send uploader principal ID
    files = {"file": ("pothole.jpg", io.BytesIO(VALID_JPEG), "image/jpeg")}
    data = {"uploaded_by_principal": "mayor-01", "uploader_role": "ADMINISTRATOR"}
    upload_res = citizen.post(f"/api/cases/{case_id}/evidence", files=files, data=data)
    assert upload_res.status_code == 201

    # Verify server repository stored the authentic citizen-01 principal ID
    evidence_id = upload_res.json()["evidence_id"]
    rec = evidence_repo.get_evidence(case_id, evidence_id)
    assert rec is not None
    assert rec.uploaded_by_principal == "citizen-01"
    assert rec.uploader_role == "CITIZEN"


# ---------------------------------------------------------------------------
# TEST 16: Client attempts to submit another department
# ---------------------------------------------------------------------------
def test_16_client_cannot_spoof_department():
    roads_officer = login_as("roads.officer@jarviscivic.local")  # PWD_ROADS

    citizen = login_as("citizen@jarviscivic.local")
    create_res = citizen.post(
        "/api/cases",
        json={"description": "Road pothole", "location": "Chennai", "department": "PWD_ROADS"},
    )
    case_id = create_res.json()["case_id"]

    # Officer attempts to submit resolution evidence claiming department is DRAINAGE_STORMWATER
    files = {"file": ("repair.jpg", io.BytesIO(VALID_JPEG), "image/jpeg")}
    data = {
        "evidence_type": EvidenceType.RESOLUTION_EVIDENCE.value,
        "authority_department": "DRAINAGE_STORMWATER",
    }
    upload_res = roads_officer.post(f"/api/cases/{case_id}/evidence", files=files, data=data)
    assert upload_res.status_code == 201

    evidence_id = upload_res.json()["evidence_id"]
    rec = evidence_repo.get_evidence(case_id, evidence_id)
    assert rec is not None
    # Server derives authority department from officer's actual authenticated department (PWD_ROADS)
    assert rec.authority_department == "PWD_ROADS"


# ---------------------------------------------------------------------------
# TEST 17: AI unavailable returns safe UNCERTAIN outcome
# ---------------------------------------------------------------------------
def test_17_ai_unavailable_returns_safe_uncertain():
    citizen = login_as("citizen@jarviscivic.local")
    create_res = citizen.post(
        "/api/cases",
        json={"description": "Test issue", "location": "Chennai", "department": "PWD_ROADS"},
    )
    case_id = create_res.json()["case_id"]

    # Configure fallback provider (AI unavailable)
    evidence_verification_service.set_provider(DeterministicFallbackProvider())

    files = {"file": ("test.jpg", io.BytesIO(VALID_JPEG), "image/jpeg")}
    upload_res = citizen.post(f"/api/cases/{case_id}/evidence", files=files)
    assert upload_res.status_code == 201
    data = upload_res.json()

    assert data["validation_status"] == DeterministicValidationStatus.VALID.value
    assert data["verification_status"] == VerificationOutcome.UNCERTAIN.value

    # Verify verification record recorded ai_available = False
    ver = evidence_repo.get_verification_for_evidence(data["evidence_id"])
    assert ver is not None
    assert ver.ai_available is False
    assert ver.assessment_provider == "deterministic-fallback"


# ---------------------------------------------------------------------------
# TEST 18: AI malformed response handled safely as UNCERTAIN
# ---------------------------------------------------------------------------
def test_18_ai_malformed_response_handled_safely():
    citizen = login_as("citizen@jarviscivic.local")
    create_res = citizen.post(
        "/api/cases",
        json={"description": "Test issue", "location": "Chennai", "department": "PWD_ROADS"},
    )
    case_id = create_res.json()["case_id"]

    # Mock provider simulates malformed AI outcome
    evidence_verification_service.set_provider(
        MockEvidenceAssessmentProvider(
            outcome=VerificationOutcome.UNCERTAIN,
            reason="Advisory AI evaluation encountered an internal error; defaulted to UNCERTAIN.",
            confidence=None,
            ai_available=False,
        )
    )

    files = {"file": ("test.jpg", io.BytesIO(VALID_JPEG), "image/jpeg")}
    upload_res = citizen.post(f"/api/cases/{case_id}/evidence", files=files)
    assert upload_res.status_code == 201
    assert upload_res.json()["verification_status"] == VerificationOutcome.UNCERTAIN.value


# ---------------------------------------------------------------------------
# TEST 19: AI returns UNCERTAIN on ambiguous evidence
# ---------------------------------------------------------------------------
def test_19_ai_returns_uncertain_on_ambiguous_evidence():
    citizen = login_as("citizen@jarviscivic.local")
    create_res = citizen.post(
        "/api/cases",
        json={"description": "Test issue", "location": "Chennai", "department": "PWD_ROADS"},
    )
    case_id = create_res.json()["case_id"]

    evidence_verification_service.set_provider(
        MockEvidenceAssessmentProvider(
            outcome=VerificationOutcome.UNCERTAIN,
            reason="Ambiguous visual content; cannot determine defect status with confidence.",
            confidence=0.45,
            ai_available=True,
        )
    )

    files = {"file": ("blurry.jpg", io.BytesIO(VALID_JPEG), "image/jpeg")}
    upload_res = citizen.post(f"/api/cases/{case_id}/evidence", files=files)
    assert upload_res.status_code == 201
    assert upload_res.json()["verification_status"] == VerificationOutcome.UNCERTAIN.value


# ---------------------------------------------------------------------------
# TEST 20: AI returns REJECTED on contradictory evidence
# ---------------------------------------------------------------------------
def test_20_ai_returns_rejected_on_contradictory_evidence():
    roads_officer = login_as("roads.officer@jarviscivic.local")
    citizen = login_as("citizen@jarviscivic.local")
    create_res = citizen.post(
        "/api/cases",
        json={"description": "Large road crater", "location": "Chennai", "department": "PWD_ROADS"},
    )
    case_id = create_res.json()["case_id"]

    # AI detects that evidence is contradictory (e.g. photo of an indoor office)
    evidence_verification_service.set_provider(
        MockEvidenceAssessmentProvider(
            outcome=VerificationOutcome.REJECTED,
            reason="Artifact content is unrelated or contradicts case context.",
            confidence=0.92,
            ai_available=True,
        )
    )

    files = {"file": ("unrelated.jpg", io.BytesIO(VALID_JPEG), "image/jpeg")}
    data = {"evidence_type": EvidenceType.RESOLUTION_EVIDENCE.value}
    upload_res = roads_officer.post(f"/api/cases/{case_id}/evidence", files=files, data=data)
    assert upload_res.status_code == 201
    assert upload_res.json()["verification_status"] == VerificationOutcome.REJECTED.value

    # Invariant: Case is NOT closed or resolved
    case = case_store.get_case(case_id)
    assert case.status != CaseStatus.RESOLVED


# ---------------------------------------------------------------------------
# TEST 21: Rejected evidence not exposed as trusted evidence
# ---------------------------------------------------------------------------
def test_21_rejected_evidence_not_persisted_as_trusted():
    citizen = login_as("citizen@jarviscivic.local")
    create_res = citizen.post(
        "/api/cases",
        json={"description": "Test issue", "location": "Chennai", "department": "PWD_ROADS"},
    )
    case_id = create_res.json()["case_id"]

    # Upload malformed file that fails deterministic validation
    files = {"file": ("corrupt.png", io.BytesIO(b"not_png_bytes"), "image/png")}
    upload_res = citizen.post(f"/api/cases/{case_id}/evidence", files=files)
    assert upload_res.status_code == 400

    # Verify no evidence was attached to the case
    case = case_store.get_case(case_id)
    assert len(case.evidence_uris) == 0
    assert len(evidence_repo.list_evidence_for_case(case_id)) == 0


# ---------------------------------------------------------------------------
# TEST 22: Public cannot read private evidence
# ---------------------------------------------------------------------------
def test_22_public_cannot_read_private_evidence():
    citizen = login_as("citizen@jarviscivic.local")
    create_res = citizen.post(
        "/api/cases",
        json={"description": "Test issue", "location": "Chennai", "department": "PWD_ROADS"},
    )
    case_id = create_res.json()["case_id"]

    files = {"file": ("secret.jpg", io.BytesIO(VALID_JPEG), "image/jpeg")}
    citizen.post(f"/api/cases/{case_id}/evidence", files=files)

    # Unauthenticated / Public client attempts to read case evidence
    unauth = TestClient(app)
    read_res = unauth.get(f"/api/cases/{case_id}/evidence")
    # Public has no read_evidence permission -> HTTP 401 or 403
    assert read_res.status_code in [401, 403]


# ---------------------------------------------------------------------------
# TEST 23: Audit identity comes from authenticated principal
# ---------------------------------------------------------------------------
def test_23_audit_identity_comes_from_authenticated_principal():
    roads_officer = login_as("roads.officer@jarviscivic.local")  # authority-officer-roads-01

    citizen = login_as("citizen@jarviscivic.local")
    create_res = citizen.post(
        "/api/cases",
        json={"description": "Road pothole", "location": "Chennai", "department": "PWD_ROADS"},
    )
    case_id = create_res.json()["case_id"]

    files = {"file": ("repair.jpg", io.BytesIO(VALID_JPEG), "image/jpeg")}
    data = {"evidence_type": EvidenceType.RESOLUTION_EVIDENCE.value}
    upload_res = roads_officer.post(f"/api/cases/{case_id}/evidence", files=files, data=data)
    assert upload_res.status_code == 201

    # Check audit dispatcher recorded event with authority-officer-roads-01 principal ID
    events = [e for e in audit_dispatcher.get_events_for_case(case_id) if e.event_type == "RESOLUTION_EVIDENCE_ATTACHED"]
    assert len(events) >= 1
    ev = events[0]
    assert ev.principal_id == "authority-officer-roads-01"
    assert ev.principal_role == "AUTHORITY_OFFICER"
    assert ev.principal_department == "PWD_ROADS"


# ---------------------------------------------------------------------------
# TEST 24: Notification only occurs after validated persistence
# ---------------------------------------------------------------------------
def test_24_notification_only_occurs_after_validated_persistence():
    citizen = login_as("citizen@jarviscivic.local")
    create_res = citizen.post(
        "/api/cases",
        json={"description": "Road pothole", "location": "Chennai", "department": "PWD_ROADS"},
    )
    case_id = create_res.json()["case_id"]

    initial_notifs = len(notification_service.get_case_notifications(case_id))

    # 1. Invalid upload attempt (fails deterministic check)
    files = {"file": ("corrupt.jpg", io.BytesIO(b"fake_bytes"), "image/jpeg")}
    fail_res = citizen.post(f"/api/cases/{case_id}/evidence", files=files)
    assert fail_res.status_code == 400

    # Invariant: Notification count did NOT increase
    assert len(notification_service.get_case_notifications(case_id)) == initial_notifs

    # 2. Valid upload
    valid_files = {"file": ("valid.jpg", io.BytesIO(VALID_JPEG), "image/jpeg")}
    success_res = citizen.post(f"/api/cases/{case_id}/evidence", files=valid_files)
    assert success_res.status_code == 201

    # Invariant: Notification triggered after validated persistence
    assert len(notification_service.get_case_notifications(case_id)) > initial_notifs


# ---------------------------------------------------------------------------
# TEST 25: Backend restart preserves evidence metadata (Correction 1 & 14.A)
# ---------------------------------------------------------------------------
def test_25_backend_restart_preserves_evidence_metadata(tmp_path):
    storage_file = str(tmp_path / "restart_evidence.json")
    # Point repository to temp disk store
    from app.services.evidence.repository import EvidenceVerificationRepository

    repo1 = EvidenceVerificationRepository(storage_path=storage_file)

    citizen = login_as("citizen@jarviscivic.local")
    create_res = citizen.post(
        "/api/cases",
        json={"description": "Restart test case", "location": "Chennai", "department": "PWD_ROADS"},
    )
    case_id = create_res.json()["case_id"]

    # Temporarily substitute repo in evidence_verification_service
    import app.services.evidence_verification_service as evs_module
    orig_repo = evs_module.evidence_repo
    evs_module.evidence_repo = repo1

    try:
        files = {"file": ("durable.jpg", io.BytesIO(VALID_JPEG), "image/jpeg")}
        upload_res = citizen.post(f"/api/cases/{case_id}/evidence", files=files)
        assert upload_res.status_code == 201
        ev_data = upload_res.json()
        evidence_id = ev_data["evidence_id"]
        expected_sha = ev_data["sha256"]

        # Simulate backend restart: create new EvidenceVerificationRepository instance from the same disk file
        repo2 = EvidenceVerificationRepository(storage_path=storage_file)

        # Invariant 1: Evidence metadata survived restart
        reloaded_rec = repo2.get_evidence(case_id, evidence_id)
        assert reloaded_rec is not None
        assert reloaded_rec.sha256 == expected_sha
        assert reloaded_rec.validation_status == DeterministicValidationStatus.VALID
        assert reloaded_rec.verification_status == VerificationOutcome.VERIFIED

        # Invariant 2: List query returns the preserved evidence
        case_items = repo2.list_evidence_for_case(case_id)
        assert any(item.evidence_id == evidence_id for item in case_items)

        # Invariant 3: Verification record survived restart
        ver_rec = repo2.get_verification_for_evidence(evidence_id)
        assert ver_rec is not None
        assert ver_rec.verification_status == VerificationOutcome.VERIFIED
    finally:
        evs_module.evidence_repo = orig_repo


# ---------------------------------------------------------------------------
# TEST 26: Text-only Ollama model cannot perform image analysis (Correction 4 & 14.E)
# ---------------------------------------------------------------------------
def test_26_text_only_ollama_model_cannot_perform_image_analysis():
    from app.services.evidence.provider import OllamaEvidenceAssessmentProvider

    # Configure a text-only model
    provider = OllamaEvidenceAssessmentProvider(model="llama3.2:3b")

    result = provider.assess(
        case_id="case-123",
        case_description="Pothole repair check",
        department="PWD_ROADS",
        evidence_type=EvidenceType.RESOLUTION_EVIDENCE,
        filename="repair_photo.jpg",
        content_type="image/jpeg",
        file_bytes=VALID_JPEG,
    )

    # Invariant: Text-only model is never falsely reported as having inspected an image
    assert result.outcome == VerificationOutcome.UNCERTAIN
    assert result.ai_available is False
    assert "unsupported_modality" in result.detected_characteristics
    assert "text-only" in result.reason


# ---------------------------------------------------------------------------
# TEST 27: Client cannot spoof SHA-256 digest (Correction 11 & 14.F)
# ---------------------------------------------------------------------------
def test_27_client_cannot_spoof_sha256():
    citizen = login_as("citizen@jarviscivic.local")
    create_res = citizen.post(
        "/api/cases",
        json={"description": "Spoof test case", "location": "Chennai", "department": "PWD_ROADS"},
    )
    case_id = create_res.json()["case_id"]

    import hashlib
    actual_sha = hashlib.sha256(VALID_JPEG).hexdigest()
    forged_sha = "0000000000000000000000000000000000000000000000000000000000000000"

    files = {"file": ("check.jpg", io.BytesIO(VALID_JPEG), "image/jpeg")}
    data = {"sha256": forged_sha}
    res = citizen.post(f"/api/cases/{case_id}/evidence", files=files, data=data)
    assert res.status_code == 201
    body = res.json()

    # Invariant: Server-calculated SHA-256 is authoritative; client-provided SHA-256 is discarded
    assert body["sha256"] == actual_sha
    assert body["sha256"] != forged_sha


# ---------------------------------------------------------------------------
# TEST 28: Resolution evidence does not modify lifecycle status (Correction 7 & 14.J)
# ---------------------------------------------------------------------------
def test_28_resolution_evidence_does_not_modify_case_status():
    roads_officer = login_as("roads.officer@jarviscivic.local")
    citizen = login_as("citizen@jarviscivic.local")
    create_res = citizen.post(
        "/api/cases",
        json={"description": "Pothole case", "location": "Chennai", "department": "PWD_ROADS"},
    )
    case_id = create_res.json()["case_id"]

    # Initial status
    initial_case = case_store.get_case(case_id)
    assert initial_case.status == CaseStatus.DOCKET_CREATED

    # Authority uploads resolution evidence
    files = {"file": ("repair_done.jpg", io.BytesIO(VALID_JPEG), "image/jpeg")}
    data = {"evidence_type": EvidenceType.RESOLUTION_EVIDENCE.value, "resolution_attempt": "1"}
    upload_res = roads_officer.post(f"/api/cases/{case_id}/evidence", files=files, data=data)
    assert upload_res.status_code == 201

    # Invariant: Case status remains unchanged; NOT RESOLVED, NOT CLOSED
    updated_case = case_store.get_case(case_id)
    assert updated_case.status == CaseStatus.DOCKET_CREATED
    assert updated_case.status.value != "RESOLVED"
    assert updated_case.status.value != "CASE_RESOLVED"


# ---------------------------------------------------------------------------
# TEST 29: Valid artifact + AI REJECTED remains assessment state, not closure (Correction 3 & 14.C)
# ---------------------------------------------------------------------------
def test_29_valid_artifact_ai_rejected_remains_assessment_not_closure():
    roads_officer = login_as("roads.officer@jarviscivic.local")
    citizen = login_as("citizen@jarviscivic.local")
    create_res = citizen.post(
        "/api/cases",
        json={"description": "Road pothole issue", "location": "Chennai", "department": "PWD_ROADS"},
    )
    case_id = create_res.json()["case_id"]

    # Configure mock AI to assess artifact as REJECTED (e.g. photo shows wrong scene or contradictory content)
    evidence_verification_service.set_provider(
        MockEvidenceAssessmentProvider(
            outcome=VerificationOutcome.REJECTED,
            reason="Image shows an unrelated indoor scene rather than road repair.",
            confidence=0.95,
            ai_available=True,
        )
    )

    # Valid JPEG uploaded
    files = {"file": ("unrelated.jpg", io.BytesIO(VALID_JPEG), "image/jpeg")}
    data = {"evidence_type": EvidenceType.RESOLUTION_EVIDENCE.value}
    upload_res = roads_officer.post(f"/api/cases/{case_id}/evidence", files=files, data=data)

    # Invariant 1: Valid artifact passes deterministic validation and is persisted
    assert upload_res.status_code == 201
    body = upload_res.json()
    assert body["validation_status"] == "VALID"
    assert body["verification_status"] == "REJECTED"
    assert "indoor scene" in body["verification_reason"]

    # Invariant 2: Case remains open, status is NOT modified
    current_case = case_store.get_case(case_id)
    assert current_case.status == CaseStatus.DOCKET_CREATED
    assert current_case.status.value != "RESOLVED"
