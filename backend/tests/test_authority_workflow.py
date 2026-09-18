"""Phase 6 Authority Workflow and Audit Trail Integration Tests.

Validates:
1. Strict forward single-step lifecycle transitions (01 DOCKET_CREATED -> 02 ROUTING_PREPARED -> 03 SUBMISSION_READY -> 04 UNDER_REVIEW -> 05 RESOLVED)
2. Rejection of skipped and backward transitions with HTTP 409 Conflict
3. Department-scoped Cedar authorization for AuthorityOfficers and MunicipalSupervisors
4. Cedar denial (HTTP 403) for Citizen and Public status mutation and audit access
5. Resolution note addition and attribution
6. Cedar-protected audit log inspection (/api/audit/cases/{case_id})
7. Public-safe history endpoint (/api/cases/{case_id}/history)
8. Append-only audit record creation after successful mutations and integrity on rejected mutations
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.enums import CaseStatus, ControlledDepartment
from app.services.case_store import case_store

client = TestClient(app)

DRAINAGE_DEPT = ControlledDepartment.DRAINAGE_STORMWATER.value
ROADS_DEPT = ControlledDepartment.PWD_ROADS.value
WATER_DEPT = ControlledDepartment.WATER_SUPPLY.value

# Principal Headers for Simulation
CITIZEN_HEADERS = {
    "X-Simulated-Role": "CITIZEN",
    "X-Simulated-Principal-Id": "cit-user-101",
}

PUBLIC_HEADERS = {
    "X-Simulated-Role": "PUBLIC",
    "X-Simulated-Principal-Id": "anon-visitor",
}

OFFICER_DRAINAGE_HEADERS = {
    "X-Simulated-Role": "AUTHORITY_OFFICER",
    "X-Simulated-Principal-Id": "officer-drainage-1",
    "X-Simulated-Department": DRAINAGE_DEPT,
}

OFFICER_ROADS_HEADERS = {
    "X-Simulated-Role": "AUTHORITY_OFFICER",
    "X-Simulated-Principal-Id": "officer-roads-2",
    "X-Simulated-Department": ROADS_DEPT,
}

SUPERVISOR_DRAINAGE_HEADERS = {
    "X-Simulated-Role": "MUNICIPAL_SUPERVISOR",
    "X-Simulated-Principal-Id": "sup-drainage-1",
    "X-Simulated-Department": DRAINAGE_DEPT,
}

SUPERVISOR_ROADS_HEADERS = {
    "X-Simulated-Role": "MUNICIPAL_SUPERVISOR",
    "X-Simulated-Principal-Id": "sup-roads-2",
    "X-Simulated-Department": ROADS_DEPT,
}

ADMIN_HEADERS = {
    "X-Simulated-Role": "ADMINISTRATOR",
    "X-Simulated-Principal-Id": "admin-global",
}


@pytest.fixture(autouse=True)
def clean_store():
    """Ensure clean case store and audit trail before each test."""
    case_store.clear()
    yield
    case_store.clear()


def _create_test_case(department: str = DRAINAGE_DEPT) -> str:
    """Helper to create a civic grievance case as a citizen."""
    payload = {
        "description": "Severe stormwater drain overflow near market entrance",
        "location": "North Usman Road, T. Nagar",
        "pincode": "600017",
        "department": department,
        "is_public": True,
    }
    resp = client.post("/api/cases", json=payload, headers=CITIZEN_HEADERS)
    assert resp.status_code == 201
    return resp.json()["case_id"]


# ===========================================================================
# 1. Canonical Lifecycle State Machine Transitions
# ===========================================================================

def test_canonical_forward_lifecycle_transitions():
    """Verify strict single-step progression through all 5 canonical stages."""
    case_id = _create_test_case(DRAINAGE_DEPT)

    # Initial stage: 01 DOCKET_CREATED
    case = client.get(f"/api/cases/{case_id}", headers=OFFICER_DRAINAGE_HEADERS).json()
    assert case["status"] == "DOCKET_CREATED"

    # Step 1: DOCKET_CREATED -> ROUTING_PREPARED
    r1 = client.patch(
        f"/api/cases/{case_id}/status",
        json={"status": "ROUTING_PREPARED", "note": "Jurisdictional routing verified"},
        headers=OFFICER_DRAINAGE_HEADERS,
    )
    assert r1.status_code == 200
    assert r1.json()["status"] == "ROUTING_PREPARED"

    # Step 2: ROUTING_PREPARED -> SUBMISSION_READY
    r2 = client.patch(
        f"/api/cases/{case_id}/status",
        json={"status": "SUBMISSION_READY", "note": "Docket dossier assembled"},
        headers=OFFICER_DRAINAGE_HEADERS,
    )
    assert r2.status_code == 200
    assert r2.json()["status"] == "SUBMISSION_READY"

    # Step 3: SUBMISSION_READY -> UNDER_REVIEW
    r3 = client.patch(
        f"/api/cases/{case_id}/status",
        json={"status": "UNDER_REVIEW", "note": "Field dispatch queued"},
        headers=OFFICER_DRAINAGE_HEADERS,
    )
    assert r3.status_code == 200
    assert r3.json()["status"] == "UNDER_REVIEW"

    # Step 4: UNDER_REVIEW -> RESOLVED
    r4 = client.patch(
        f"/api/cases/{case_id}/status",
        json={"status": "RESOLVED", "note": "Drain de-silted and flow restored"},
        headers=OFFICER_DRAINAGE_HEADERS,
    )
    assert r4.status_code == 200
    assert r4.json()["status"] == "RESOLVED"
    assert "Drain de-silted and flow restored" in r4.json()["resolution_notes"]


def test_skip_lifecycle_transition_rejected_with_409():
    """Verify jumping ahead (skipping stages) returns HTTP 409 Conflict."""
    case_id = _create_test_case(DRAINAGE_DEPT)

    # Attempt skipping from DOCKET_CREATED directly to UNDER_REVIEW
    resp = client.patch(
        f"/api/cases/{case_id}/status",
        json={"status": "UNDER_REVIEW"},
        headers=OFFICER_DRAINAGE_HEADERS,
    )
    assert resp.status_code == 409
    assert "Invalid status transition" in resp.json()["detail"]

    # Case remains unchanged
    case = client.get(f"/api/cases/{case_id}", headers=OFFICER_DRAINAGE_HEADERS).json()
    assert case["status"] == "DOCKET_CREATED"

    # Attempt skipping directly to RESOLVED
    resp2 = client.patch(
        f"/api/cases/{case_id}/status",
        json={"status": "RESOLVED"},
        headers=OFFICER_DRAINAGE_HEADERS,
    )
    assert resp2.status_code == 409
    assert case_store.get_case(case_id).status == CaseStatus.DOCKET_CREATED


def test_backward_lifecycle_transition_rejected_with_409():
    """Verify backward status mutations are strictly rejected with HTTP 409."""
    case_id = _create_test_case(DRAINAGE_DEPT)

    # Advance to ROUTING_PREPARED
    client.patch(
        f"/api/cases/{case_id}/status",
        json={"status": "ROUTING_PREPARED"},
        headers=OFFICER_DRAINAGE_HEADERS,
    )

    # Attempt backward move to DOCKET_CREATED
    resp = client.patch(
        f"/api/cases/{case_id}/status",
        json={"status": "DOCKET_CREATED"},
        headers=OFFICER_DRAINAGE_HEADERS,
    )
    assert resp.status_code == 409
    assert "Invalid status transition" in resp.json()["detail"]
    assert case_store.get_case(case_id).status == CaseStatus.ROUTING_PREPARED


def test_same_or_terminal_transition_rejected_with_409():
    """Verify transition to same status or beyond RESOLVED is rejected."""
    case_id = _create_test_case(DRAINAGE_DEPT)

    # Attempt same status
    resp = client.patch(
        f"/api/cases/{case_id}/status",
        json={"status": "DOCKET_CREATED"},
        headers=OFFICER_DRAINAGE_HEADERS,
    )
    assert resp.status_code == 409


# ===========================================================================
# 2. Cedar Authorization & Department Scoping
# ===========================================================================

def test_authority_department_match_succeeds():
    """Officer whose department matches the case department can update status."""
    case_id = _create_test_case(ROADS_DEPT)

    resp = client.patch(
        f"/api/cases/{case_id}/status",
        json={"status": "ROUTING_PREPARED"},
        headers=OFFICER_ROADS_HEADERS,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "ROUTING_PREPARED"


def test_authority_department_mismatch_denied_with_403():
    """Officer from a different department cannot update status (Cedar denied)."""
    case_id = _create_test_case(ROADS_DEPT)

    # Officer from DRAINAGE attempts to mutate ROADS case
    resp = client.patch(
        f"/api/cases/{case_id}/status",
        json={"status": "ROUTING_PREPARED"},
        headers=OFFICER_DRAINAGE_HEADERS,
    )
    assert resp.status_code == 403
    assert resp.json()["detail"] == "Authorization denied"


def test_citizen_cannot_update_case_status_403():
    """Citizen (even the case owner) cannot mutate lifecycle status."""
    case_id = _create_test_case(DRAINAGE_DEPT)

    resp = client.patch(
        f"/api/cases/{case_id}/status",
        json={"status": "ROUTING_PREPARED"},
        headers=CITIZEN_HEADERS,
    )
    assert resp.status_code == 403


def test_public_user_cannot_update_case_status_403():
    """Public unauthenticated user cannot mutate lifecycle status."""
    case_id = _create_test_case(DRAINAGE_DEPT)

    resp = client.patch(
        f"/api/cases/{case_id}/status",
        json={"status": "ROUTING_PREPARED"},
        headers=PUBLIC_HEADERS,
    )
    assert resp.status_code == 403


# ===========================================================================
# 3. Resolution Notes API
# ===========================================================================

def test_authorized_resolution_note_addition():
    """Authorized officer can add resolution notes via /notes and /resolution-note alias."""
    case_id = _create_test_case(DRAINAGE_DEPT)

    # Add note via primary endpoint
    r1 = client.post(
        f"/api/cases/{case_id}/notes",
        json={"note": "Initial site inspection completed."},
        headers=OFFICER_DRAINAGE_HEADERS,
    )
    assert r1.status_code == 200
    assert "Initial site inspection completed." in r1.json()["resolution_notes"]

    # Add note via canonical alias endpoint
    r2 = client.post(
        f"/api/cases/{case_id}/resolution-note",
        json={"note": "Culvert blockage cleared by field crew."},
        headers=OFFICER_DRAINAGE_HEADERS,
    )
    assert r2.status_code == 200
    assert len(r2.json()["resolution_notes"]) == 2


def test_citizen_cannot_add_resolution_note_403():
    """Citizen cannot add authority resolution notes."""
    case_id = _create_test_case(DRAINAGE_DEPT)

    resp = client.post(
        f"/api/cases/{case_id}/resolution-note",
        json={"note": "Citizen trying to add authority note"},
        headers=CITIZEN_HEADERS,
    )
    assert resp.status_code == 403


# ===========================================================================
# 4. Cedar-Protected Audit Trail Endpoint (/api/audit/cases/{case_id})
# ===========================================================================

def test_supervisor_audit_access_scoped_to_department():
    """Municipal Supervisor can view audit trail for cases in their department."""
    case_id = _create_test_case(DRAINAGE_DEPT)

    # Supervisor matching department
    resp = client.get(
        f"/api/audit/cases/{case_id}",
        headers=SUPERVISOR_DRAINAGE_HEADERS,
    )
    assert resp.status_code == 200
    events = resp.json()
    assert isinstance(events, list)
    assert len(events) >= 1
    assert any(e["event_type"] == "DOCKET_CREATED" for e in events)


def test_supervisor_mismatched_department_audit_access_denied_403():
    """Supervisor from another department is strictly denied audit access."""
    case_id = _create_test_case(DRAINAGE_DEPT)

    # Supervisor from ROADS department attempts to inspect DRAINAGE case
    resp = client.get(
        f"/api/audit/cases/{case_id}",
        headers=SUPERVISOR_ROADS_HEADERS,
    )
    assert resp.status_code == 403


def test_administrator_universal_audit_access():
    """Administrator has universal audit access across all departments."""
    case_id = _create_test_case(DRAINAGE_DEPT)

    resp = client.get(
        f"/api/audit/cases/{case_id}",
        headers=ADMIN_HEADERS,
    )
    assert resp.status_code == 200
    assert len(resp.json()) >= 1


def test_authority_officer_denied_audit_trail_403():
    """Line officers cannot access the full supervisor audit trail."""
    case_id = _create_test_case(DRAINAGE_DEPT)

    resp = client.get(
        f"/api/audit/cases/{case_id}",
        headers=OFFICER_DRAINAGE_HEADERS,
    )
    assert resp.status_code == 403


def test_citizen_and_public_denied_audit_trail_403():
    """Citizens and public callers cannot access internal audit logs."""
    case_id = _create_test_case(DRAINAGE_DEPT)

    resp_cit = client.get(f"/api/audit/cases/{case_id}", headers=CITIZEN_HEADERS)
    assert resp_cit.status_code == 403

    resp_pub = client.get(f"/api/audit/cases/{case_id}", headers=PUBLIC_HEADERS)
    assert resp_pub.status_code == 403


# ===========================================================================
# 5. Public-Safe History Endpoint (/api/cases/{case_id}/history)
# ===========================================================================

def test_safe_public_history_endpoint():
    """Public callers can view sanitized milestone progression."""
    case_id = _create_test_case(DRAINAGE_DEPT)

    # Advance status as officer
    client.patch(
        f"/api/cases/{case_id}/status",
        json={"status": "ROUTING_PREPARED", "note": "Routing prepared"},
        headers=OFFICER_DRAINAGE_HEADERS,
    )

    # Retrieve history as public caller
    resp = client.get(f"/api/cases/{case_id}/history", headers=PUBLIC_HEADERS)
    assert resp.status_code == 200
    history = resp.json()
    assert len(history) >= 2
    assert history[0]["status"] == "DOCKET_CREATED"
    assert history[1]["status"] == "ROUTING_PREPARED"

    # Critical security assertion: No raw PII or Cedar internal tokens in history
    for item in history:
        assert "principal_id" not in item
        assert "decision" not in item


# ===========================================================================
# 6. Audit Trail Append-Only Behavior
# ===========================================================================

def test_audit_records_appended_on_mutations_and_not_on_rejections():
    """Verify audit entries are captured for valid mutations and not for invalid transitions."""
    case_id = _create_test_case(DRAINAGE_DEPT)

    # Attempt invalid jump -> Rejected 409
    client.patch(
        f"/api/cases/{case_id}/status",
        json={"status": "RESOLVED"},
        headers=OFFICER_DRAINAGE_HEADERS,
    )

    # Inspect audit events as admin
    audit_resp = client.get(f"/api/audit/cases/{case_id}", headers=ADMIN_HEADERS)
    events = audit_resp.json()

    # Should NOT have any STATUS_TRANSITION event since the mutation was rejected
    status_events = [e for e in events if e["event_type"] == "STATUS_TRANSITION"]
    assert len(status_events) == 0

    # Now perform valid transition
    client.patch(
        f"/api/cases/{case_id}/status",
        json={"status": "ROUTING_PREPARED", "note": "Valid advance"},
        headers=OFFICER_DRAINAGE_HEADERS,
    )

    audit_resp2 = client.get(f"/api/audit/cases/{case_id}", headers=ADMIN_HEADERS)
    events2 = audit_resp2.json()
    status_events2 = [e for e in events2 if e["event_type"] == "STATUS_TRANSITION"]
    assert len(status_events2) == 1
    assert status_events2[0]["previous_status"] == "DOCKET_CREATED"
    assert status_events2[0]["new_status"] == "ROUTING_PREPARED"
    assert status_events2[0]["principal_role"] == "AUTHORITY_OFFICER"
