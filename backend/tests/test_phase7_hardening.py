"""Phase 7 Polish, Verification & Production Hardening Regression Tests.

Validates:
1. Structured API error responses and exception shielding (no stack trace exposure)
2. Input validation hardening (whitespace-only, boundary lengths, Indian pincode format)
3. Multilingual Unicode tolerance (Tamil, Hindi, Telugu, Kannada, Bengali, Marathi, Hinglish)
4. Principal resolution hardening (whitespace headers, unknown roles, departmental spoofing prevention)
5. Cedar fail-closed security and departmental boundary enforcement
6. Concurrency conflict detection on lifecycle state transitions (HTTP 409 Conflict)
7. Evidence security (cross-platform path traversal sanitization, empty/oversized file rejection)
8. Public tracking projection security isolation
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.enums import CaseStatus, ControlledDepartment
from app.services.case_store import case_store

client = TestClient(app)

DRAINAGE_DEPT = ControlledDepartment.DRAINAGE_STORMWATER.value
ROADS_DEPT = ControlledDepartment.PWD_ROADS.value


@pytest.fixture(autouse=True)
def clean_stores():
    """Ensure clean case store before and after each test."""
    case_store.clear()
    yield
    case_store.clear()


# ===========================================================================
# 1. Structured API Errors & Exception Shielding
# ===========================================================================

def test_structured_error_format_on_404():
    """Verify missing case returns safe JSON error with detail."""
    resp = client.get(
        "/api/cases/NON-EXISTENT-CASE",
        headers={"X-Simulated-Role": "ADMINISTRATOR", "X-Simulated-Principal-Id": "admin-1"},
    )
    assert resp.status_code == 404
    body = resp.json()
    assert "detail" in body
    assert body["detail"] == "Case not found"
    assert "Traceback" not in resp.text


def test_structured_error_format_on_validation_failure():
    """Verify validation failure returns structured JSON without leaking stack trace."""
    resp = client.post(
        "/api/cases",
        json={"description": "a", "location": "b"},  # Fails min_length
        headers={"X-Simulated-Role": "CITIZEN", "X-Simulated-Principal-Id": "cit-1"},
    )
    assert resp.status_code == 422
    body = resp.json()
    assert "detail" in body
    # Must not contain raw python traceback
    assert "Traceback" not in resp.text


# ===========================================================================
# 2. Input Validation Hardening (Whitespace, Pincode, Length Limits)
# ===========================================================================

def test_rejects_whitespace_only_description():
    """Whitespace-only descriptions must be rejected with 422."""
    resp = client.post(
        "/api/cases",
        json={
            "description": "          ",
            "location": "Anna Salai",
            "department": DRAINAGE_DEPT,
            "pincode": "600002",
        },
        headers={"X-Simulated-Role": "CITIZEN", "X-Simulated-Principal-Id": "cit-1"},
    )
    assert resp.status_code == 422
    assert "Description must contain at least 5 non-whitespace characters" in resp.text


def test_rejects_whitespace_only_location():
    """Whitespace-only location must be rejected with 422."""
    resp = client.post(
        "/api/cases",
        json={
            "description": "Severe pothole causing traffic obstruction",
            "location": "  ",
            "department": ROADS_DEPT,
            "pincode": "600002",
        },
        headers={"X-Simulated-Role": "CITIZEN", "X-Simulated-Principal-Id": "cit-1"},
    )
    assert resp.status_code == 422
    assert "Location must contain at least 2 non-whitespace characters" in resp.text


def test_rejects_invalid_pincode_formats():
    """Indian pincode must be exactly 6 digits starting with 1-9."""
    invalid_pincodes = ["012345", "12345", "1234567", "ABCDEF", "560 38", "56003#"]
    for pin in invalid_pincodes:
        resp = client.post(
            "/api/cases",
            json={
                "description": "Streetlight failure for past three weeks",
                "location": "Indiranagar 12th Main",
                "department": DRAINAGE_DEPT,
                "pincode": pin,
            },
            headers={"X-Simulated-Role": "CITIZEN", "X-Simulated-Principal-Id": "cit-1"},
        )
        assert resp.status_code == 422, f"Expected 422 for invalid pincode: {pin}"


def test_accepts_valid_indian_pincode():
    """Valid 6-digit Indian postal code starting with 1-9 must succeed."""
    resp = client.post(
        "/api/cases",
        json={
            "description": "Major road surface crater near metro pillar 45",
            "location": "Old Airport Road",
            "department": ROADS_DEPT,
            "pincode": "560008",
        },
        headers={"X-Simulated-Role": "CITIZEN", "X-Simulated-Principal-Id": "cit-1"},
    )
    assert resp.status_code == 201
    assert resp.json()["pincode"] == "560008"


def test_rejects_whitespace_only_resolution_note():
    """Whitespace-only resolution note must be rejected with 422."""
    # First create a valid case
    create_resp = client.post(
        "/api/cases",
        json={
            "description": "Drainage overflow across pedestrian walkway",
            "location": "T Nagar",
            "department": DRAINAGE_DEPT,
        },
        headers={"X-Simulated-Role": "CITIZEN", "X-Simulated-Principal-Id": "cit-1"},
    )
    cid = create_resp.json()["case_id"]

    # Try to add whitespace note
    note_resp = client.post(
        f"/api/cases/{cid}/resolution-note",
        json={"note": "     "},
        headers={
            "X-Simulated-Role": "AUTHORITY_OFFICER",
            "X-Simulated-Principal-Id": "officer-1",
            "X-Simulated-Department": DRAINAGE_DEPT,
        },
    )
    assert note_resp.status_code == 422
    assert "Resolution note must contain at least 3 non-whitespace characters" in note_resp.text


# ===========================================================================
# 3. Multilingual Unicode Resilience
# ===========================================================================

@pytest.mark.parametrize(
    "lang,description,location",
    [
        ("ta", "மழைநீர் வடிகால் அடைப்பு காரணமாக தெருவில் தண்ணீர் தேங்கியுள்ளது", "தியாகராய நகர்"),
        ("hi", "सड़क पर बड़ा गड्ढा होने के कारण यातायात बाधित हो रहा है", "कनॉट प्लेस"),
        ("te", "ప్రధాన రహదారిపై వీధి దీపాలు వెలగడం లేదు", "బంజారా హిల్స్"),
        ("kn", "ಕಸ ಸಂಗ್ರಹಣೆ ಸರಿಯಾಗಿ ನಡೆಯುತ್ತಿಲ್ಲ ಮತ್ತು ದುರ್ವಾಸನೆ ಬರುತ್ತಿದೆ", "ಜಯನಗರ"),
        ("bn", "বৃষ্টির জল জমে রাস্তা জলমগ্ন হয়ে পড়েছে", "সল্টলেক"),
        ("mr", "रस्त्यावरील खड्ड्यांमुळे वाहतुकीची कोंडी होत आहे", "शिवाजी नगर"),
        ("hinglish", "Main road pe bahut heavy waterlogging hai near metro station", "Indiranagar 100ft road"),
    ],
)
def test_multilingual_unicode_case_creation(lang, description, location):
    """Ensure non-Latin Indian scripts are processed without distortion or validation failure."""
    resp = client.post(
        "/api/cases",
        json={
            "description": description,
            "location": location,
            "department": DRAINAGE_DEPT,
            "pincode": "600017",
        },
        headers={"X-Simulated-Role": "CITIZEN", "X-Simulated-Principal-Id": f"cit-{lang}"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["description"] == description
    assert data["location"] == location


# ===========================================================================
# 4. Principal Resolution Hardening & Department Spoofing Prevention
# ===========================================================================

def test_citizen_cannot_spoof_authority_department():
    """A Citizen supplying an X-Simulated-Department header must have department stripped to None."""
    create_resp = client.post(
        "/api/cases",
        json={
            "description": "Garbage dump accumulation blocking school entrance",
            "location": "Velachery Main Road",
            "department": DRAINAGE_DEPT,
        },
        headers={"X-Simulated-Role": "CITIZEN", "X-Simulated-Principal-Id": "cit-spoof-1"},
    )
    cid = create_resp.json()["case_id"]

    # Attempt to update status as CITIZEN spoofing authority department
    resp = client.patch(
        f"/api/cases/{cid}/status",
        json={"status": CaseStatus.ROUTING_PREPARED.value},
        headers={
            "X-Simulated-Role": "CITIZEN",
            "X-Simulated-Principal-Id": "cit-spoof-1",
            "X-Simulated-Department": DRAINAGE_DEPT,
        },
    )
    assert resp.status_code == 403
    assert resp.json()["detail"] == "Authorization denied"


def test_empty_identity_headers_default_safely_to_public():
    """Empty or whitespace-only identity headers safely evaluate as PublicUser."""
    create_resp = client.post(
        "/api/cases",
        json={
            "description": "Public park bench broken",
            "location": "Cubbon Park",
            "department": ControlledDepartment.PUBLIC_INFRASTRUCTURE_DAMAGE.value if hasattr(ControlledDepartment, "PUBLIC_INFRASTRUCTURE_DAMAGE") else DRAINAGE_DEPT,
            "is_public": True,
        },
        headers={"X-Simulated-Role": "CITIZEN", "X-Simulated-Principal-Id": "cit-author-1"},
    )
    cid = create_resp.json()["case_id"]

    # Access public tracking with empty whitespace headers -> Must succeed for public projection
    resp = client.get(
        f"/api/tracking/{cid}",
        headers={"X-Simulated-Role": "   ", "X-Simulated-Principal-Id": "   "},
    )
    assert resp.status_code == 200
    assert resp.json()["case_id"] == cid

    # Attempt mutation with empty whitespace headers -> Must be denied (403)
    mut_resp = client.patch(
        f"/api/cases/{cid}/status",
        json={"status": CaseStatus.ROUTING_PREPARED.value},
        headers={"X-Simulated-Role": "   ", "X-Simulated-Principal-Id": "   "},
    )
    assert mut_resp.status_code == 403


def test_unknown_role_fails_closed_to_public():
    """Unknown or invalid role strings degrade safely to PublicUser and fail closed."""
    resp = client.post(
        "/api/cases",
        json={
            "description": "Attempted case creation with invalid role",
            "location": "MG Road",
            "department": DRAINAGE_DEPT,
        },
        headers={"X-Simulated-Role": "SUPER_USER_ROOT", "X-Simulated-Principal-Id": "hacker-1"},
    )
    # Public users cannot create cases (only Citizens and Admins can)
    assert resp.status_code == 403
    assert resp.json()["detail"] == "Authorization denied"


# ===========================================================================
# 5. Concurrency Conflict Detection on Lifecycle
# ===========================================================================

def test_concurrent_status_mutation_conflict_detection():
    """If two actors attempt simultaneous updates, second update must be rejected with 409 Conflict."""
    create_resp = client.post(
        "/api/cases",
        json={
            "description": "Water logging near underpass",
            "location": "Gariahat Flyover",
            "department": DRAINAGE_DEPT,
        },
        headers={"X-Simulated-Role": "CITIZEN", "X-Simulated-Principal-Id": "cit-1"},
    )
    cid = create_resp.json()["case_id"]

    # Officer 1 advances from DOCKET_CREATED -> ROUTING_PREPARED
    resp1 = client.patch(
        f"/api/cases/{cid}/status",
        json={"status": CaseStatus.ROUTING_PREPARED.value},
        headers={
            "X-Simulated-Role": "AUTHORITY_OFFICER",
            "X-Simulated-Principal-Id": "officer-drainage-1",
            "X-Simulated-Department": DRAINAGE_DEPT,
        },
    )
    assert resp1.status_code == 200
    assert resp1.json()["status"] == CaseStatus.ROUTING_PREPARED.value

    # Stale/concurrent request also trying to advance DOCKET_CREATED -> ROUTING_PREPARED
    resp2 = client.patch(
        f"/api/cases/{cid}/status",
        json={"status": CaseStatus.ROUTING_PREPARED.value},
        headers={
            "X-Simulated-Role": "AUTHORITY_OFFICER",
            "X-Simulated-Principal-Id": "officer-drainage-2",
            "X-Simulated-Department": DRAINAGE_DEPT,
        },
    )
    # Status is already ROUTING_PREPARED, so advancing to ROUTING_PREPARED is rejected with 409
    assert resp2.status_code == 409
    assert "Invalid status transition" in resp2.json()["detail"]


# ===========================================================================
# 6. Evidence Security & Path Traversal Protection
# ===========================================================================

def test_evidence_path_traversal_filename_sanitization():
    """Filenames containing directory traversal sequences must be sanitized to safe basenames."""
    create_resp = client.post(
        "/api/cases",
        json={
            "description": "Overflowing manhole cover",
            "location": "Koramangala 4th Block",
            "department": DRAINAGE_DEPT,
        },
        headers={"X-Simulated-Role": "CITIZEN", "X-Simulated-Principal-Id": "cit-ev-1"},
    )
    cid = create_resp.json()["case_id"]

    # Upload with dangerous traversal filename
    traversal_filenames = [
        "../../etc/passwd.jpg",
        "..\\..\\windows\\system32\\cmd.jpg",
        ".../.../traversal.png",
    ]

    for malicious_name in traversal_filenames:
        files = {"file": (malicious_name, b"fake-jpg-binary-content-12345", "image/jpeg")}
        up_resp = client.post(
            f"/api/cases/{cid}/evidence",
            files=files,
            headers={"X-Simulated-Role": "CITIZEN", "X-Simulated-Principal-Id": "cit-ev-1"},
        )
        assert up_resp.status_code == 201
        meta = up_resp.json()
        assert "/" not in meta["filename"]
        assert "\\" not in meta["filename"]
        assert ".." not in meta["filename"]
        assert meta["filename"].endswith((".jpg", ".png"))


def test_evidence_rejects_empty_file():
    """Empty 0-byte evidence file must be rejected with 400 Bad Request."""
    create_resp = client.post(
        "/api/cases",
        json={
            "description": "Pothole evidence upload test",
            "location": "Indiranagar",
            "department": ROADS_DEPT,
        },
        headers={"X-Simulated-Role": "CITIZEN", "X-Simulated-Principal-Id": "cit-ev-1"},
    )
    cid = create_resp.json()["case_id"]

    files = {"file": ("empty.jpg", b"", "image/jpeg")}
    up_resp = client.post(
        f"/api/cases/{cid}/evidence",
        files=files,
        headers={"X-Simulated-Role": "CITIZEN", "X-Simulated-Principal-Id": "cit-ev-1"},
    )
    assert up_resp.status_code == 400
    assert "cannot be empty" in up_resp.json()["detail"]


# ===========================================================================
# 7. Public Tracking Projection Isolation
# ===========================================================================

def test_public_tracking_excludes_sensitive_internal_attributes():
    """Public tracking projection must never leak owner identity, notes, or evidence URIs."""
    create_resp = client.post(
        "/api/cases",
        json={
            "description": "Broken drainage slab near bus stop",
            "location": "Adyar Signal",
            "department": DRAINAGE_DEPT,
            "pincode": "600020",
            "is_public": True,
        },
        headers={"X-Simulated-Role": "CITIZEN", "X-Simulated-Principal-Id": "cit-private-owner-99"},
    )
    cid = create_resp.json()["case_id"]

    # Public anonymous tracking request
    track_resp = client.get(
        f"/api/tracking/{cid}",
        headers={"X-Simulated-Role": "PUBLIC", "X-Simulated-Principal-Id": "anonymous-guest"},
    )
    assert track_resp.status_code == 200
    track_data = track_resp.json()

    # Allowed public fields
    assert "case_id" in track_data
    assert "status" in track_data
    assert "recommended_department" in track_data
    assert "created_at" in track_data
    assert "updated_at" in track_data

    # FORBIDDEN private fields
    assert "owner_id" not in track_data
    assert "description" not in track_data
    assert "evidence_uris" not in track_data
    assert "resolution_notes" not in track_data
    assert "cit-private-owner-99" not in track_resp.text
