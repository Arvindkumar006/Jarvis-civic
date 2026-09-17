"""FastAPI Integration and PEP Enforcement Tests for JARVIS Civic.

Phase 3 API Integration:
Verifies HTTP endpoints, PEP interceptors, sanitized HTTP 403 responses,
public tracking projections, and audit event stream.
"""

import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.models.enums import CaseStatus, ControlledDepartment
from app.security.audit import audit_dispatcher
from app.services.case_store import case_store

client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_stores():
    """Ensure clean case store and audit dispatcher for test isolation."""
    case_store.clear()
    audit_dispatcher.clear()
    yield
    case_store.clear()
    audit_dispatcher.clear()


def test_citizen_creates_case_via_api():
    """POST /api/cases with Citizen headers returns 201 Created and creates case."""
    headers = {
        "X-Principal-Id": "citizen-arun",
        "X-Principal-Role": "CITIZEN",
    }
    payload = {
        "description": "Severe road pothole causing bike accidents",
        "location": "Anna Nagar 2nd Avenue",
        "department": "PWD_ROADS",
        "pincode": "600040",
        "is_public": True,
    }
    response = client.post("/api/cases", json=payload, headers=headers)
    assert response.status_code == 201
    data = response.json()
    assert data["owner_id"] == "citizen-arun"
    assert data["department"] == "PWD_ROADS"
    assert data["status"] == "DOCKET_CREATED"
    assert "case_id" in data


def test_citizen_reads_own_case_allowed():
    """GET /api/cases/{case_id} by owner returns 200 OK with full case."""
    # Seed case
    headers = {"X-Principal-Id": "citizen-priya", "X-Principal-Role": "CITIZEN"}
    create_res = client.post(
        "/api/cases",
        json={
            "description": "Drainage overflow near water tank",
            "location": "Gandhi Street",
            "department": "DRAINAGE_STORMWATER",
            "is_public": True,
        },
        headers=headers,
    )
    case_id = create_res.json()["case_id"]

    # Read own case
    res = client.get(f"/api/cases/{case_id}", headers=headers)
    assert res.status_code == 200
    assert res.json()["case_id"] == case_id
    assert res.json()["owner_id"] == "citizen-priya"


def test_citizen_reads_another_citizens_case_forbidden():
    """GET /api/cases/{case_id} by non-owner returns 403 Forbidden with sanitized detail."""
    # Priya creates case
    priya_headers = {"X-Principal-Id": "citizen-priya", "X-Principal-Role": "CITIZEN"}
    create_res = client.post(
        "/api/cases",
        json={
            "description": "Drainage overflow near water tank",
            "location": "Gandhi Street",
            "department": "DRAINAGE_STORMWATER",
        },
        headers=priya_headers,
    )
    case_id = create_res.json()["case_id"]

    # Bob tries to read Priya's case
    bob_headers = {"X-Principal-Id": "citizen-bob", "X-Principal-Role": "CITIZEN"}
    res = client.get(f"/api/cases/{case_id}", headers=bob_headers)

    assert res.status_code == 403
    assert res.json() == {"detail": "Authorization denied"}


def test_citizen_cannot_update_case_status():
    """PATCH /api/cases/{case_id}/status by Citizen returns 403 Forbidden."""
    headers = {"X-Principal-Id": "citizen-priya", "X-Principal-Role": "CITIZEN"}
    create_res = client.post(
        "/api/cases",
        json={
            "description": "Garbage dumping on sidewalk",
            "location": "Park Road",
            "department": "WASTE_MANAGEMENT",
        },
        headers=headers,
    )
    case_id = create_res.json()["case_id"]

    # Attempt to resolve own case
    update_res = client.patch(
        f"/api/cases/{case_id}/status",
        json={"status": "RESOLVED", "note": "Resolved by citizen"},
        headers=headers,
    )
    assert update_res.status_code == 403
    assert update_res.json() == {"detail": "Authorization denied"}


def test_authority_officer_updates_case_within_department_scope():
    """PATCH /api/cases/{case_id}/status by Officer with matching department returns 200."""
    # Create drainage case
    cit_headers = {"X-Principal-Id": "citizen-1", "X-Principal-Role": "CITIZEN"}
    create_res = client.post(
        "/api/cases",
        json={
            "description": "Storm drain clogged with debris",
            "location": "Lake Road",
            "department": "DRAINAGE_STORMWATER",
        },
        headers=cit_headers,
    )
    case_id = create_res.json()["case_id"]

    # Officer with DRAINAGE_STORMWATER department updates status
    officer_headers = {
        "X-Principal-Id": "officer-drainage-1",
        "X-Principal-Role": "AUTHORITY_OFFICER",
        "X-Principal-Department": "DRAINAGE_STORMWATER",
    }
    update_res = client.patch(
        f"/api/cases/{case_id}/status",
        json={"status": "UNDER_REVIEW", "note": "Inspection scheduled for morning"},
        headers=officer_headers,
    )
    assert update_res.status_code == 200
    assert update_res.json()["status"] == "UNDER_REVIEW"
    assert "Inspection scheduled for morning" in update_res.json()["resolution_notes"]


def test_authority_officer_denied_on_different_department():
    """PATCH /api/cases/{case_id}/status by Officer in different department returns 403."""
    # Create drainage case
    cit_headers = {"X-Principal-Id": "citizen-1", "X-Principal-Role": "CITIZEN"}
    create_res = client.post(
        "/api/cases",
        json={
            "description": "Storm drain clogged with debris",
            "location": "Lake Road",
            "department": "DRAINAGE_STORMWATER",
        },
        headers=cit_headers,
    )
    case_id = create_res.json()["case_id"]

    # Officer with WASTE_MANAGEMENT tries to update DRAINAGE case
    waste_officer_headers = {
        "X-Principal-Id": "officer-waste-1",
        "X-Principal-Role": "AUTHORITY_OFFICER",
        "X-Principal-Department": "WASTE_MANAGEMENT",
    }
    update_res = client.patch(
        f"/api/cases/{case_id}/status",
        json={"status": "UNDER_REVIEW"},
        headers=waste_officer_headers,
    )
    assert update_res.status_code == 403
    assert update_res.json() == {"detail": "Authorization denied"}


def test_public_tracking_works_without_authentication_headers():
    """GET /api/tracking/{case_id} requires NO identity headers and returns safe projection."""
    # Create case
    cit_headers = {"X-Principal-Id": "citizen-ramesh", "X-Principal-Role": "CITIZEN"}
    create_res = client.post(
        "/api/cases",
        json={
            "description": "Streetlight bulb damaged",
            "location": "North Usman Road",
            "department": "ELECTRICITY_UTILITY",
            "is_public": True,
        },
        headers=cit_headers,
    )
    case_id = create_res.json()["case_id"]

    # Anonymous call with ZERO identity headers
    tracking_res = client.get(f"/api/tracking/{case_id}")
    assert tracking_res.status_code == 200
    track_data = tracking_res.json()

    # Safe projection check: MUST NOT contain owner_id or private citizen details
    assert track_data["case_id"] == case_id
    assert track_data["status"] == "DOCKET_CREATED"
    assert track_data["recommended_department"] == "ELECTRICITY_UTILITY"
    assert "owner_id" not in track_data
    assert "description" not in track_data
    assert "location" not in track_data


def test_public_user_cannot_access_full_case():
    """GET /api/cases/{case_id} without credentials is denied (Public cannot read full case)."""
    cit_headers = {"X-Principal-Id": "citizen-1", "X-Principal-Role": "CITIZEN"}
    create_res = client.post(
        "/api/cases",
        json={
            "description": "Broken sidewalk",
            "location": "1st Street",
            "department": "PWD_ROADS",
        },
        headers=cit_headers,
    )
    case_id = create_res.json()["case_id"]

    # Call /api/cases without headers -> defaults to PUBLIC -> Denied
    res = client.get(f"/api/cases/{case_id}")
    assert res.status_code == 403
    assert res.json() == {"detail": "Authorization denied"}


def test_audit_log_access_and_isolation():
    """GET /api/audit/logs allows Supervisor/Admin and strictly denies Citizens/Public."""
    # 1. Citizen is denied
    cit_headers = {"X-Principal-Id": "citizen-1", "X-Principal-Role": "CITIZEN"}
    res_cit = client.get("/api/audit/logs", headers=cit_headers)
    assert res_cit.status_code == 403
    assert res_cit.json() == {"detail": "Authorization denied"}

    # 2. Public is denied
    res_pub = client.get("/api/audit/logs")
    assert res_pub.status_code == 403

    # 3. Supervisor can inspect
    sup_headers = {
        "X-Principal-Id": "supervisor-1",
        "X-Principal-Role": "MUNICIPAL_SUPERVISOR",
        "X-Principal-Department": "DRAINAGE_STORMWATER",
    }
    res_sup = client.get("/api/audit/logs", headers=sup_headers)
    assert res_sup.status_code == 200
    assert isinstance(res_sup.json(), list)

    # 4. Administrator can inspect
    admin_headers = {
        "X-Principal-Id": "admin-1",
        "X-Principal-Role": "ADMINISTRATOR",
    }
    res_admin = client.get("/api/audit/logs", headers=admin_headers)
    assert res_admin.status_code == 200
    assert isinstance(res_admin.json(), list)


def test_audit_dispatcher_records_decisions():
    """Verify that audit dispatcher captures audit records for PEP evaluations."""
    initial_count = audit_dispatcher.count()

    headers = {"X-Principal-Id": "citizen-audit-test", "X-Principal-Role": "CITIZEN"}
    client.post(
        "/api/cases",
        json={
            "description": "Test case for audit streaming",
            "location": "Audit Lane",
            "department": "PWD_ROADS",
        },
        headers=headers,
    )

    new_count = audit_dispatcher.count()
    assert new_count > initial_count

    events = audit_dispatcher.get_events()
    recent = events[0]
    assert recent.principal_id == "citizen-audit-test"
    assert recent.action == "create_case"
    assert recent.decision == "ALLOW"
