"""Authority Roles Hardening and Authoritative Docket Status Tests.

Verifies:
R1. Citizen account belongs to CITIZEN workspace.
R2. PWD Officer authenticates to AUTHORITY_OFFICER with PWD_ROADS department.
R3. Roads Officer authenticates to AUTHORITY_OFFICER with PWD_ROADS department.
R4. Drainage Officer authenticates to AUTHORITY_OFFICER with DRAINAGE_STORMWATER department.
R5. Stormwater Officer authenticates to AUTHORITY_OFFICER with DRAINAGE_STORMWATER department.
R6. Municipal Supervisor authenticates to MUNICIPAL_SUPERVISOR.
R7. Public unauthenticated has no authority privileges.
R8. Administrator authenticates to ADMINISTRATOR, not an authority department, cannot impersonate citizen closure.
R9. Public tracking projection works without credentials.
R10. Administrator functionality works where required.
R11. Cross-department authorization denial: Drainage cannot advance PWD case and vice-versa.
R12. Citizen-only resolution confirmation enforced: authority and supervisor cannot close.

Lifecycle Status Invariants:
S1. Case creation initializes to DOCKET_CREATED.
S2. Progression leads to UNDER_REVIEW.
S3. Citizen ACCEPT atomically transitions to RESOLVED across CaseStore and tracking.
S6. Citizen REJECT preserves UNDER_REVIEW.
S7. Authority rework and subsequent citizen ACCEPT transitions to RESOLVED.
S8. CaseStore persistence preserves RESOLVED after reload.
S9. Direct authority/admin PATCH to RESOLVED returns HTTP 409 Conflict.
S10. Non-owner citizen confirmation returns HTTP 403 Forbidden.
"""

import io
import pytest
from fastapi.testclient import TestClient

from app.config.settings import settings
from app.main import app
from app.models.enums import CaseStatus, ControlledDepartment
from app.models.security import ApplicationRole
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


def login_as(email: str, password: str = settings.DEV_DEFAULT_PASSWORD) -> TestClient:
    """Helper to authenticate and return a client with session cookie."""
    c = TestClient(app)
    res = c.post("/api/auth/login", json={"email": email, "password": password})
    assert res.status_code == 200, f"Login failed for {email}: {res.text}"
    return c


# ==============================================================================
# 1. AUTHORITY WORKSPACE ROLE TESTS (R1 - R12)
# ==============================================================================

def test_r1_citizen_workspace_identity():
    """R1: Citizen authenticates to CITIZEN workspace."""
    c = login_as("citizen@jarviscivic.local")
    me = c.get("/api/auth/me").json()
    assert me["role"] == ApplicationRole.CITIZEN.value
    assert me["email"] == "citizen@jarviscivic.local"


def test_r2_pwd_authority_workspace():
    """R2: PWD Officer authenticates to AUTHORITY_OFFICER with PWD_ROADS department."""
    c = login_as("pwd.officer@jarviscivic.local")
    me = c.get("/api/auth/me").json()
    assert me["role"] == ApplicationRole.AUTHORITY_OFFICER.value
    assert me["department"] == ControlledDepartment.PWD_ROADS.value


def test_r3_roads_authority_workspace():
    """R3: Roads Officer authenticates to AUTHORITY_OFFICER with PWD_ROADS department."""
    c = login_as("roads.officer@jarviscivic.local")
    me = c.get("/api/auth/me").json()
    assert me["role"] == ApplicationRole.AUTHORITY_OFFICER.value
    assert me["department"] == ControlledDepartment.PWD_ROADS.value


def test_r4_drainage_authority_workspace():
    """R4: Drainage Officer authenticates to AUTHORITY_OFFICER with DRAINAGE_STORMWATER department."""
    c = login_as("drainage.officer@jarviscivic.local")
    me = c.get("/api/auth/me").json()
    assert me["role"] == ApplicationRole.AUTHORITY_OFFICER.value
    assert me["department"] == ControlledDepartment.DRAINAGE_STORMWATER.value


def test_r5_stormwater_authority_workspace():
    """R5: Stormwater Officer authenticates to AUTHORITY_OFFICER with DRAINAGE_STORMWATER department."""
    c = login_as("stormwater.officer@jarviscivic.local")
    me = c.get("/api/auth/me").json()
    assert me["role"] == ApplicationRole.AUTHORITY_OFFICER.value
    assert me["department"] == ControlledDepartment.DRAINAGE_STORMWATER.value


def test_r6_municipal_supervisor_authority_workspace():
    """R6: Municipal Supervisor authenticates to MUNICIPAL_SUPERVISOR."""
    c = login_as("supervisor@jarviscivic.local")
    me = c.get("/api/auth/me").json()
    assert me["role"] == ApplicationRole.MUNICIPAL_SUPERVISOR.value


def test_r7_public_cannot_perform_authority_mutations():
    """R7: Public unauthenticated user cannot perform status transitions."""
    cit_c = login_as("citizen@jarviscivic.local")
    case_res = cit_c.post("/api/cases", json={
        "description": "Public test case",
        "location": "Adyar",
        "department": "PWD_ROADS",
    })
    case_id = case_res.json()["case_id"]

    # Attempt status transition without authentication -> 403 Forbidden under Cedar default deny
    res = client.patch(
        f"/api/cases/{case_id}/status",
        json={"status": "ROUTING_PREPARED"},
    )
    assert res.status_code == 403


def test_r8_system_administrator_identity_and_closure_restriction():
    """R8: System Administrator is ADMINISTRATOR, has admin access, but cannot close case."""
    admin_c = login_as("admin@jarviscivic.local")
    me = admin_c.get("/api/auth/me").json()
    assert me["role"] == ApplicationRole.ADMINISTRATOR.value

    # Create a case by citizen
    cit_c = login_as("citizen@jarviscivic.local")
    case_res = cit_c.post("/api/cases", json={
        "description": "Drain blockage",
        "location": "Anna Nagar",
        "department": "DRAINAGE_STORMWATER",
    })
    case_id = case_res.json()["case_id"]

    # Admin attempts to accept citizen resolution -> MUST BE 403
    accept_res = admin_c.post(f"/api/cases/{case_id}/resolution/accept", json={"feedback": "Admin force"})
    assert accept_res.status_code == 403


def test_r9_public_tracking_works_unauthenticated():
    """R9: Public tracking query returns public-safe projection without credentials."""
    cit_c = login_as("citizen@jarviscivic.local")
    case_res = cit_c.post("/api/cases", json={
        "description": "Crater in street",
        "location": "Velachery",
        "department": "PWD_ROADS",
        "is_public": True,
    })
    case_id = case_res.json()["case_id"]

    # Query public tracking unauthenticated
    track_res = client.get(f"/api/tracking/{case_id}")
    assert track_res.status_code == 200
    data = track_res.json()
    assert data["case_id"] == case_id
    assert data["status"] == "DOCKET_CREATED"
    assert data["recommended_department"] == "PWD_ROADS"


def test_r10_administrator_audit_access_works():
    """R10: Administrator functionality works where authorized (e.g. audit access)."""
    cit_c = login_as("citizen@jarviscivic.local")
    case_res = cit_c.post("/api/cases", json={
        "description": "Streetlight broken",
        "location": "Mylapore",
        "department": "PWD_ROADS",
    })
    case_id = case_res.json()["case_id"]

    admin_c = login_as("admin@jarviscivic.local")
    audit_res = admin_c.get(f"/api/audit/cases/{case_id}")
    assert audit_res.status_code == 200


def test_r11_cross_department_authorization_isolation():
    """R11: Cross-department isolation enforced: Drainage officer cannot advance PWD case."""
    cit_c = login_as("citizen@jarviscivic.local")
    case_res = cit_c.post("/api/cases", json={
        "description": "Road surface defect",
        "location": "Mount Road",
        "department": "PWD_ROADS",
    })
    case_id = case_res.json()["case_id"]

    drainage_c = login_as("drainage.officer@jarviscivic.local")
    # Drainage officer tries to advance PWD case
    mut_res = drainage_c.patch(
        f"/api/cases/{case_id}/status",
        json={"status": "ROUTING_PREPARED"},
    )
    assert mut_res.status_code == 403


def test_r12_citizen_only_resolution_confirmation():
    """R12: Authority officer and supervisor cannot accept resolution confirmation."""
    cit_c = login_as("citizen@jarviscivic.local")
    case_res = cit_c.post("/api/cases", json={
        "description": "Road defect",
        "location": "Adyar",
        "department": "PWD_ROADS",
    })
    case_id = case_res.json()["case_id"]

    pwd_c = login_as("pwd.officer@jarviscivic.local")
    sup_c = login_as("supervisor@jarviscivic.local")

    assert pwd_c.post(f"/api/cases/{case_id}/resolution/accept", json={}).status_code == 403
    assert sup_c.post(f"/api/cases/{case_id}/resolution/accept", json={}).status_code == 403


# ==============================================================================
# 2. STATUS SCENARIOS (S1 - S10)
# ==============================================================================

def test_s1_create_case_initializes_docket_created():
    """S1: Newly created case has status DOCKET_CREATED."""
    cit_c = login_as("citizen@jarviscivic.local")
    res = cit_c.post("/api/cases", json={
        "description": "Drain overflow",
        "location": "T Nagar",
        "department": "DRAINAGE_STORMWATER",
    })
    assert res.status_code == 201
    assert res.json()["status"] == CaseStatus.DOCKET_CREATED.value

    # Verify public tracking also shows DOCKET_CREATED
    case_id = res.json()["case_id"]
    track = client.get(f"/api/tracking/{case_id}").json()
    assert track["status"] == CaseStatus.DOCKET_CREATED.value


def test_s2_progress_case_to_under_review():
    """S2: Case transitions canonical lifecycle up to UNDER_REVIEW."""
    cit_c = login_as("citizen@jarviscivic.local")
    res = cit_c.post("/api/cases", json={
        "description": "Drain overflow",
        "location": "T Nagar",
        "department": "DRAINAGE_STORMWATER",
    })
    case_id = res.json()["case_id"]
    drainage_c = login_as("drainage.officer@jarviscivic.local")

    transitions = [
        "ROUTING_PREPARED",
        "SUBMISSION_READY",
        "UNDER_REVIEW",
    ]
    for nxt in transitions:
        t_res = drainage_c.patch(f"/api/cases/{case_id}/status", json={"status": nxt})
        assert t_res.status_code == 200
        assert t_res.json()["status"] == nxt

    # Verify CaseStore and tracking are in UNDER_REVIEW
    rec = case_store.get_case(case_id)
    assert rec.status == CaseStatus.UNDER_REVIEW
    track = client.get(f"/api/tracking/{case_id}").json()
    assert track["status"] == "UNDER_REVIEW"


def test_s3_citizen_accept_transitions_to_resolved():
    """S3: Citizen ACCEPT atomically transitions CaseStore and tracking to RESOLVED."""
    cit_c = login_as("citizen@jarviscivic.local")
    res = cit_c.post("/api/cases", json={
        "description": "Road pothole",
        "location": "Guindy",
        "department": "PWD_ROADS",
    })
    case_id = res.json()["case_id"]
    roads_c = login_as("roads.officer@jarviscivic.local")

    for nxt in ["ROUTING_PREPARED", "SUBMISSION_READY", "UNDER_REVIEW"]:
        t_res = roads_c.patch(f"/api/cases/{case_id}/status", json={"status": nxt})
        assert t_res.status_code == 200

    # Authority uploads resolution evidence
    files = {"file": ("proof.jpg", io.BytesIO(VALID_JPEG), "image/jpeg")}
    data = {
        "evidence_type": CivicEvidenceType.RESOLUTION_EVIDENCE.value,
        "description": "Pothole filled and leveled",
    }
    ev_res = roads_c.post(f"/api/cases/{case_id}/evidence", files=files, data=data)
    assert ev_res.status_code == 201

    # Citizen confirms resolution
    accept_res = cit_c.post(f"/api/cases/{case_id}/resolution/accept", json={"feedback": "Looks great!"})
    assert accept_res.status_code == 200
    assert accept_res.json()["status"] == CaseStatus.RESOLVED.value

    # CaseStore authoritative check
    persisted = case_store.get_case(case_id)
    assert persisted.status == CaseStatus.RESOLVED
    assert persisted.resolution_confirmed is True

    # Tracking projection check
    track = client.get(f"/api/tracking/{case_id}").json()
    assert track["status"] == "RESOLVED"


def test_s6_citizen_reject_preserves_under_review():
    """S6: Citizen REJECT keeps case in UNDER_REVIEW."""
    cit_c = login_as("citizen@jarviscivic.local")
    res = cit_c.post("/api/cases", json={
        "description": "Road pothole",
        "location": "Guindy",
        "department": "PWD_ROADS",
    })
    case_id = res.json()["case_id"]
    roads_c = login_as("roads.officer@jarviscivic.local")

    for nxt in ["ROUTING_PREPARED", "SUBMISSION_READY", "UNDER_REVIEW"]:
        t_res = roads_c.patch(f"/api/cases/{case_id}/status", json={"status": nxt})
        assert t_res.status_code == 200

    # Upload evidence
    files = {"file": ("proof.jpg", io.BytesIO(VALID_JPEG), "image/jpeg")}
    data = {
        "evidence_type": CivicEvidenceType.RESOLUTION_EVIDENCE.value,
        "description": "Temporary gravel patch",
    }
    roads_c.post(f"/api/cases/{case_id}/evidence", files=files, data=data)

    # Citizen rejects
    reject_res = cit_c.post(
        f"/api/cases/{case_id}/resolution/reject",
        json={"reason": "Gravel is loose and pothole is still sunken"},
    )
    assert reject_res.status_code == 200
    assert reject_res.json()["status"] == CaseStatus.UNDER_REVIEW.value
    assert reject_res.json()["rejection_count"] == 1

    persisted = case_store.get_case(case_id)
    assert persisted.status == CaseStatus.UNDER_REVIEW
    assert persisted.rejection_count == 1


def test_s7_rework_and_second_accept():
    """S7: Authority reworks, submits new evidence, citizen accepts -> RESOLVED."""
    cit_c = login_as("citizen@jarviscivic.local")
    res = cit_c.post("/api/cases", json={
        "description": "Clogged culvert",
        "location": "Saidapet",
        "department": "DRAINAGE_STORMWATER",
    })
    case_id = res.json()["case_id"]
    stormwater_c = login_as("stormwater.officer@jarviscivic.local")

    for nxt in ["ROUTING_PREPARED", "SUBMISSION_READY", "UNDER_REVIEW"]:
        t_res = stormwater_c.patch(f"/api/cases/{case_id}/status", json={"status": nxt})
        assert t_res.status_code == 200

    # 1. First attempt rejected
    files1 = {"file": ("attempt1.jpg", io.BytesIO(VALID_JPEG), "image/jpeg")}
    stormwater_c.post(
        f"/api/cases/{case_id}/evidence",
        files=files1,
        data={"evidence_type": CivicEvidenceType.RESOLUTION_EVIDENCE.value, "description": "Attempt 1"},
    )
    cit_c.post(f"/api/cases/{case_id}/resolution/reject", json={"reason": "Culvert still blocked inside"})

    # 2. Rework: Second attempt uploaded
    files2 = {"file": ("attempt2.jpg", io.BytesIO(VALID_JPEG), "image/jpeg")}
    stormwater_c.post(
        f"/api/cases/{case_id}/evidence",
        files=files2,
        data={"evidence_type": CivicEvidenceType.RESOLUTION_EVIDENCE.value, "description": "Full desilting complete"},
    )

    # 3. Citizen accepts second attempt
    acc = cit_c.post(f"/api/cases/{case_id}/resolution/accept", json={"feedback": "Water flowing smoothly now."})
    assert acc.status_code == 200
    assert acc.json()["status"] == CaseStatus.RESOLVED.value

    persisted = case_store.get_case(case_id)
    assert persisted.status == CaseStatus.RESOLVED


def test_s8_persisted_resolved_status_remains_intact():
    """S8: Persisted RESOLVED case in CaseStore retains RESOLVED status."""
    cit_c = login_as("citizen@jarviscivic.local")
    res = cit_c.post("/api/cases", json={
        "description": "Drain overflow",
        "location": "Saidapet",
        "department": "DRAINAGE_STORMWATER",
    })
    case_id = res.json()["case_id"]
    drainage_c = login_as("drainage.officer@jarviscivic.local")

    for nxt in ["ROUTING_PREPARED", "SUBMISSION_READY", "UNDER_REVIEW"]:
        t_res = drainage_c.patch(f"/api/cases/{case_id}/status", json={"status": nxt})
        assert t_res.status_code == 200

    files = {"file": ("proof.jpg", io.BytesIO(VALID_JPEG), "image/jpeg")}
    drainage_c.post(
        f"/api/cases/{case_id}/evidence",
        files=files,
        data={"evidence_type": CivicEvidenceType.RESOLUTION_EVIDENCE.value, "description": "Cleared"},
    )
    cit_c.post(f"/api/cases/{case_id}/resolution/accept", json={"feedback": "Done"})

    # Retrieve from CaseStore directly
    record = case_store.get_case(case_id)
    assert record.status == CaseStatus.RESOLVED

    # Re-fetch via API
    api_get = cit_c.get(f"/api/cases/{case_id}").json()
    assert api_get["status"] == "RESOLVED"

    # Tracking projection
    track_get = client.get(f"/api/tracking/{case_id}").json()
    assert track_get["status"] == "RESOLVED"


def test_s9_direct_authority_patch_to_resolved_returns_409():
    """S9: Direct authority or admin attempt to PATCH status to RESOLVED returns 409 Conflict."""
    cit_c = login_as("citizen@jarviscivic.local")
    res = cit_c.post("/api/cases", json={
        "description": "Road pothole",
        "location": "Mount Road",
        "department": "PWD_ROADS",
    })
    case_id = res.json()["case_id"]
    roads_c = login_as("roads.officer@jarviscivic.local")

    for nxt in ["ROUTING_PREPARED", "SUBMISSION_READY", "UNDER_REVIEW"]:
        t_res = roads_c.patch(f"/api/cases/{case_id}/status", json={"status": nxt})
        assert t_res.status_code == 200

    # Direct PATCH to RESOLVED must be rejected with 409
    patch_res = roads_c.patch(f"/api/cases/{case_id}/status", json={"status": "RESOLVED"})
    assert patch_res.status_code == 409
    assert "citizen" in patch_res.text.lower() or "resolution confirmation" in patch_res.text.lower()


def test_s10_non_owner_citizen_confirmation_denied():
    """S10: Non-owner citizen attempting resolution confirmation receives HTTP 403 Forbidden."""
    cit1_c = login_as("citizen@jarviscivic.local")
    res = cit1_c.post("/api/cases", json={
        "description": "Road crater",
        "location": "Kotturpuram",
        "department": "PWD_ROADS",
    })
    case_id = res.json()["case_id"]
    roads_c = login_as("roads.officer@jarviscivic.local")

    for nxt in ["ROUTING_PREPARED", "SUBMISSION_READY", "UNDER_REVIEW"]:
        t_res = roads_c.patch(f"/api/cases/{case_id}/status", json={"status": nxt})
        assert t_res.status_code == 200

    files = {"file": ("proof.jpg", io.BytesIO(VALID_JPEG), "image/jpeg")}
    roads_c.post(
        f"/api/cases/{case_id}/evidence",
        files=files,
        data={"evidence_type": CivicEvidenceType.RESOLUTION_EVIDENCE.value, "description": "Done"},
    )

    # Register second citizen
    cit2_c = login_as("citizen.two@jarviscivic.local")
    acc_res = cit2_c.post(f"/api/cases/{case_id}/resolution/accept", json={"feedback": "Hijack attempt"})
    assert acc_res.status_code == 403


def test_department_routing_streetlight_outage_pwd_roads():
    """Verify Streetlight Outage routes to PWD_ROADS, matching Authority Workspace scope."""
    cit_c = login_as("citizen@jarviscivic.local")

    # 1. Citizen Conversation Reasoning
    conv_res = cit_c.post("/api/conversation", json={
        "session_id": "session-light-1",
        "message": "All streetlights are completely dark on 5th Main Road, Sector 4",
        "language": "en",
    })
    assert conv_res.status_code == 200
    state = conv_res.json()["state"]
    assert state["intent"] == "STREETLIGHT_OUTAGE"
    assert state["department"] == "PWD_ROADS"  # Recommended department is operational PWD_ROADS

    # 2. Case Creation
    case_res = cit_c.post("/api/cases", json={
        "description": state["description"],
        "location": state["location"],
        "department": state["department"],
    })
    assert case_res.status_code == 201
    case_data = case_res.json()
    case_id = case_data["case_id"]
    assert case_data["department"] == "PWD_ROADS"  # Persisted CaseStore department matches

    # 3. PWD Officer & Roads Officer can access and advance status
    pwd_c = login_as("pwd.officer@jarviscivic.local")
    pwd_t = pwd_c.patch(f"/api/cases/{case_id}/status", json={"status": "ROUTING_PREPARED"})
    assert pwd_t.status_code == 200

    roads_c = login_as("roads.officer@jarviscivic.local")
    roads_t = roads_c.patch(f"/api/cases/{case_id}/status", json={"status": "SUBMISSION_READY"})
    assert roads_t.status_code == 200

    # 4. Drainage Officer remains denied (department isolation)
    drain_c = login_as("drainage.officer@jarviscivic.local")
    drain_t = drain_c.patch(f"/api/cases/{case_id}/status", json={"status": "UNDER_REVIEW"})
    assert drain_t.status_code == 403

    # 5. Stormwater Officer remains denied
    storm_c = login_as("stormwater.officer@jarviscivic.local")
    storm_t = storm_c.patch(f"/api/cases/{case_id}/status", json={"status": "UNDER_REVIEW"})
    assert storm_t.status_code == 403

    # 6. Municipal Supervisor (DRAINAGE_STORMWATER scope) remains denied on PWD case
    super_c = login_as("supervisor@jarviscivic.local")
    super_t = super_c.patch(f"/api/cases/{case_id}/status", json={"status": "UNDER_REVIEW"})
    assert super_t.status_code == 403

    # 7. Unauthenticated Public remains denied
    pub_res = client.patch(f"/api/cases/{case_id}/status", json={"status": "UNDER_REVIEW"})
    assert pub_res.status_code == 403


def test_department_routing_pothole_pwd_roads():
    """Verify Pothole / Road defect routes to PWD_ROADS."""
    cit_c = login_as("citizen@jarviscivic.local")

    conv_res = cit_c.post("/api/conversation", json={
        "session_id": "session-pothole-1",
        "message": "Dangerous deep pothole on MG Road near the railway overbridge",
        "language": "en",
    })
    assert conv_res.status_code == 200
    state = conv_res.json()["state"]
    assert state["intent"] == "ROAD_POTHOLE"
    assert state["department"] == "PWD_ROADS"

    case_res = cit_c.post("/api/cases", json={
        "description": state["description"],
        "location": state["location"],
        "department": state["department"],
    })
    assert case_res.status_code == 201
    case_id = case_res.json()["case_id"]
    assert case_res.json()["department"] == "PWD_ROADS"

    roads_c = login_as("roads.officer@jarviscivic.local")
    assert roads_c.patch(f"/api/cases/{case_id}/status", json={"status": "ROUTING_PREPARED"}).status_code == 200

    drain_c = login_as("drainage.officer@jarviscivic.local")
    assert drain_c.patch(f"/api/cases/{case_id}/status", json={"status": "SUBMISSION_READY"}).status_code == 403


def test_department_routing_drainage_waterlogging():
    """Verify Waterlogging / Drainage routes to DRAINAGE_STORMWATER with supervisory scope."""
    cit_c = login_as("citizen@jarviscivic.local")

    conv_res = cit_c.post("/api/conversation", json={
        "session_id": "session-flood-1",
        "message": "Severe waterlogging at Anna Salai blocking the entire left lane",
        "language": "en",
    })
    assert conv_res.status_code == 200
    state = conv_res.json()["state"]
    assert state["intent"] == "WATERLOGGING"
    assert state["department"] == "DRAINAGE_STORMWATER"

    case_res = cit_c.post("/api/cases", json={
        "description": state["description"],
        "location": state["location"],
        "department": state["department"],
    })
    assert case_res.status_code == 201
    case_id = case_res.json()["case_id"]
    assert case_res.json()["department"] == "DRAINAGE_STORMWATER"

    # Drainage & Stormwater officers can advance
    drain_c = login_as("drainage.officer@jarviscivic.local")
    assert drain_c.patch(f"/api/cases/{case_id}/status", json={"status": "ROUTING_PREPARED"}).status_code == 200

    storm_c = login_as("stormwater.officer@jarviscivic.local")
    assert storm_c.patch(f"/api/cases/{case_id}/status", json={"status": "SUBMISSION_READY"}).status_code == 200

    # Municipal Supervisor retains supervisory authority on DRAINAGE_STORMWATER
    super_c = login_as("supervisor@jarviscivic.local")
    assert super_c.patch(f"/api/cases/{case_id}/status", json={"status": "UNDER_REVIEW"}).status_code == 200

    # PWD officer remains denied on drainage case
    pwd_c = login_as("pwd.officer@jarviscivic.local")
    assert pwd_c.patch(f"/api/cases/{case_id}/status", json={"status": "UNDER_REVIEW"}).status_code == 403


def test_case_creation_legacy_department_normalized():
    """Verify non-operational department in create payload is normalized to operational scope."""
    cit_c = login_as("citizen@jarviscivic.local")

    res = cit_c.post("/api/cases", json={
        "description": "Streetlight pole broken on service lane",
        "location": "Velachery Main Road",
        "department": "MUNICIPAL_CORPORATION",  # Legacy non-operational department
    })
    assert res.status_code == 201
    case_data = res.json()
    assert case_data["department"] == "PWD_ROADS"  # Safely normalized to PWD_ROADS

    # Operational PWD Officer can access and advance
    pwd_c = login_as("pwd.officer@jarviscivic.local")
    assert pwd_c.patch(f"/api/cases/{case_data['case_id']}/status", json={"status": "ROUTING_PREPARED"}).status_code == 200

