"""FastAPI Integration Tests for Persistence and Evidence Upload.

Phase 4 Test Suite:
Verifies case persistence through API endpoints, dedicated 'add_evidence'
Cedar authorization enforcement, evidence upload order, and public tracking safety.
"""

import io
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.case_store import case_store
from app.security.audit import audit_dispatcher

client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_stores():
    """Ensure clean case store and audit dispatcher for test isolation."""
    case_store.clear()
    audit_dispatcher.clear()
    yield
    case_store.clear()
    audit_dispatcher.clear()


def test_case_persistence_and_retrieval():
    """Verify case created via POST /api/cases persists and is retrievable via GET."""
    headers = {"X-Principal-Id": "citizen-1", "X-Principal-Role": "CITIZEN"}
    payload = {
        "description": "Severe road waterlogging blocking school buses",
        "location": "Velachery Main Road",
        "department": "DRAINAGE_STORMWATER",
        "pincode": "600042",
        "is_public": True,
    }
    create_res = client.post("/api/cases", json=payload, headers=headers)
    assert create_res.status_code == 201
    case_id = create_res.json()["case_id"]

    # Retrieve case
    get_res = client.get(f"/api/cases/{case_id}", headers=headers)
    assert get_res.status_code == 200
    data = get_res.json()
    assert data["case_id"] == case_id
    assert data["pincode"] == "600042"
    assert data["status"] == "DOCKET_CREATED"


def test_citizen_can_upload_evidence_to_own_case():
    """Citizen can upload evidence to their own case (Cedar action: add_evidence)."""
    headers = {"X-Principal-Id": "citizen-owner", "X-Principal-Role": "CITIZEN"}
    create_res = client.post(
        "/api/cases",
        json={
            "description": "Pothole damaging cars",
            "location": "LB Road",
            "department": "PWD_ROADS",
            "is_public": True,
        },
        headers=headers,
    )
    case_id = create_res.json()["case_id"]

    # Upload evidence file (valid real JPEG magic bytes FF D8 FF)
    file_content = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00\x60\x00\x60\x00\x00pothole_proof_bytes"
    files = {"file": ("pothole.jpg", io.BytesIO(file_content), "image/jpeg")}

    upload_res = client.post(f"/api/cases/{case_id}/evidence", files=files, headers=headers)
    assert upload_res.status_code == 201
    meta = upload_res.json()
    assert meta["case_id"] == case_id
    assert meta["filename"] == "pothole.jpg"
    assert meta["content_type"] == "image/jpeg"
    assert meta["object_key"].startswith(f"cases/{case_id}/evidence/")

    # Verify URI was attached to the case
    case_res = client.get(f"/api/cases/{case_id}", headers=headers)
    case_data = case_res.json()
    assert len(case_data["evidence_uris"]) == 1
    assert case_data["evidence_uris"][0] == meta["s3_uri"]


def test_citizen_cannot_upload_evidence_to_another_citizens_case():
    """Citizen attempting to upload evidence to another citizen's case receives 403."""
    # Alice creates case
    alice_headers = {"X-Principal-Id": "citizen-alice", "X-Principal-Role": "CITIZEN"}
    create_res = client.post(
        "/api/cases",
        json={
            "description": "Streetlight broken",
            "location": "Besant Nagar",
            "department": "ELECTRICITY_UTILITY",
        },
        headers=alice_headers,
    )
    case_id = create_res.json()["case_id"]

    # Bob tries to upload evidence to Alice's case
    bob_headers = {"X-Principal-Id": "citizen-bob", "X-Principal-Role": "CITIZEN"}
    files = {"file": ("photo.jpg", io.BytesIO(b"sample bytes"), "image/jpeg")}

    upload_res = client.post(f"/api/cases/{case_id}/evidence", files=files, headers=bob_headers)
    assert upload_res.status_code == 403
    assert upload_res.json() == {"detail": "Authorization denied"}


def test_public_user_cannot_upload_evidence():
    """Unauthenticated public user cannot upload evidence to any case (HTTP 403)."""
    alice_headers = {"X-Principal-Id": "citizen-alice", "X-Principal-Role": "CITIZEN"}
    create_res = client.post(
        "/api/cases",
        json={
            "description": "Garbage dump",
            "location": "Adyar",
            "department": "WASTE_MANAGEMENT",
        },
        headers=alice_headers,
    )
    case_id = create_res.json()["case_id"]

    # Anonymous user calls evidence upload with zero identity headers
    files = {"file": ("photo.jpg", io.BytesIO(b"sample bytes"), "image/jpeg")}
    upload_res = client.post(f"/api/cases/{case_id}/evidence", files=files)
    assert upload_res.status_code == 403
    assert upload_res.json() == {"detail": "Authorization denied"}


def test_authority_officer_upload_evidence_scoped():
    """Authority officer can upload evidence only within their assigned department."""
    cit_headers = {"X-Principal-Id": "citizen-1", "X-Principal-Role": "CITIZEN"}
    create_res = client.post(
        "/api/cases",
        json={
            "description": "Broken storm drain cover",
            "location": "Velachery",
            "department": "DRAINAGE_STORMWATER",
        },
        headers=cit_headers,
    )
    case_id = create_res.json()["case_id"]

    # 1. Drainage officer uploads evidence -> 201 Created
    drainage_officer = {
        "X-Principal-Id": "officer-drainage",
        "X-Principal-Role": "AUTHORITY_OFFICER",
        "X-Principal-Department": "DRAINAGE_STORMWATER",
    }
    files = {"file": ("inspection_photo.jpg", io.BytesIO(b"\xff\xd8\xff\xe0\x00\x10JFIF drain repair inspection"), "image/jpeg")}
    res_allowed = client.post(f"/api/cases/{case_id}/evidence", files=files, headers=drainage_officer)
    assert res_allowed.status_code == 201

    # 2. Waste officer tries to upload evidence to Drainage case -> 403 Forbidden
    waste_officer = {
        "X-Principal-Id": "officer-waste",
        "X-Principal-Role": "AUTHORITY_OFFICER",
        "X-Principal-Department": "WASTE_MANAGEMENT",
    }
    files2 = {"file": ("photo.jpg", io.BytesIO(b"bytes"), "image/jpeg")}
    res_denied = client.post(f"/api/cases/{case_id}/evidence", files=files2, headers=waste_officer)
    assert res_denied.status_code == 403
    assert res_denied.json() == {"detail": "Authorization denied"}


def test_evidence_authorization_order_fails_before_file_upload():
    """Verify Cedar authorization is enforced BEFORE file validation or storage.

    An unauthorized user uploading an invalid/empty file must receive 403 (Cedar Deny),
    NOT 400 (Bad Request).
    """
    alice_headers = {"X-Principal-Id": "citizen-alice", "X-Principal-Role": "CITIZEN"}
    create_res = client.post(
        "/api/cases",
        json={
            "description": "Road damage",
            "location": "Adyar",
            "department": "PWD_ROADS",
        },
        headers=alice_headers,
    )
    case_id = create_res.json()["case_id"]

    # Bob (unauthorized) uploads empty file with forbidden extension
    bob_headers = {"X-Principal-Id": "citizen-bob", "X-Principal-Role": "CITIZEN"}
    files = {"file": ("malware.exe", io.BytesIO(b""), "application/x-msdownload")}

    upload_res = client.post(f"/api/cases/{case_id}/evidence", files=files, headers=bob_headers)
    # Must be 403 (Authorization Denied), proving Cedar executed BEFORE file validation!
    assert upload_res.status_code == 403
    assert upload_res.json() == {"detail": "Authorization denied"}


def test_public_tracking_never_leaks_evidence_uris():
    """Verify that public tracking projection strictly excludes evidence URIs."""
    headers = {"X-Principal-Id": "citizen-owner", "X-Principal-Role": "CITIZEN"}
    create_res = client.post(
        "/api/cases",
        json={
            "description": "Open manhole hazard",
            "location": "T Nagar",
            "department": "DRAINAGE_STORMWATER",
            "is_public": True,
        },
        headers=headers,
    )
    case_id = create_res.json()["case_id"]

    # Attach evidence (real JPEG magic bytes)
    files = {"file": ("manhole.jpg", io.BytesIO(b"\xff\xd8\xff\xe0\x00\x10JFIF manhole image content"), "image/jpeg")}
    client.post(f"/api/cases/{case_id}/evidence", files=files, headers=headers)

    # Public tracking call
    tracking_res = client.get(f"/api/tracking/{case_id}")
    assert tracking_res.status_code == 200
    track_data = tracking_res.json()

    # CRITICAL SECURITY INVARIANT: No evidence URIs in public tracking projection
    assert "evidence_uris" not in track_data
    assert "owner_id" not in track_data
    assert track_data["case_id"] == case_id
    assert track_data["status"] == "DOCKET_CREATED"
