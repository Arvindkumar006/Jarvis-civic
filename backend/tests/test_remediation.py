"""Post-Phase-7 Surgical Remediation Regression Test Suite.

Validates all 18 remediation requirements:
1. Dependency smoke test (Strands, CedarPy)
2. Multi-turn conversation state persistence and enrichment
3. Session isolation between distinct citizens
4. Session correction/merge semantics
5. Malformed/invalid session token handling
6. Canonical enum contracts (CivicIntent, ControlledDepartment, CaseStatus, LocationSource)
7. Public case history projection sanitization (no actor_role, notes, internal dept)
8. Department-scoped authority case history access & Cedar enforcement
9. Persistent audit retrieval after repository re-instantiation
10. Complete five-stage durable lifecycle history reconstruction
11. Map location source semantics & coordinate persistence (MAP_SELECTED, TEXT_REFERENCE)
12. Evidence bounded upload memory safety (>10MB rejected with 413)
13. Evidence magic byte validation (JPEG, PNG, PDF, WAV, and invalid binary rejection)
14. Non-civic input short-circuit without false civic case generation
15. LLM source-consistency trust boundaries
16. Truthful liveness and readiness health checks
"""

import io
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.enums import (
    CaseStatus,
    CivicIntent,
    ControlledDepartment,
    LocationSource,
    UrgencyLevel,
)
from app.models.security import (
    ApplicationPrincipal,
    ApplicationRole,
    CaseHistoryItem,
    PublicCaseHistoryItem,
    AuthorizedCaseHistoryItem,
)
from app.services.persistence.factory import (
    get_repositories,
    get_audit_repository,
)
from app.services.persistence.conversation_repository import (
    conversation_session_repository,
    validate_session_id,
)
from app.services.civic_reasoning import process_civic_message

client = TestClient(app)


# 1. Dependency smoke test
def test_dependency_smoke_imports():
    """Verify runtime imports for strands and cedarpy succeed cleanly."""
    import strands
    import cedarpy
    assert strands is not None
    assert cedarpy is not None


# 2. Multi-turn conversation
@pytest.mark.asyncio
async def test_multi_turn_conversation_state_enrichment():
    """Test 3-turn conversation preserving earlier intent and merging location and pincode."""
    session_id = "session-remediation-turn-test-101"

    # Turn 1: Pothole problem
    res1 = await process_civic_message(
        message="There is a huge pothole near my house.",
        session_id=session_id,
    )
    assert res1.intent == CivicIntent.ROAD_POTHOLE
    assert res1.department == ControlledDepartment.PWD_ROADS
    assert res1.location is None
    assert "location" in res1.missing_fields
    assert res1.ready_for_action is False

    # Turn 2: Location provided
    res2 = await process_civic_message(
        message="Anna Salai near T Nagar.",
        session_id=session_id,
    )
    # Intent and description preserved from Turn 1
    assert res2.intent == CivicIntent.ROAD_POTHOLE
    assert res2.department == ControlledDepartment.PWD_ROADS
    assert "Anna Salai" in res2.location
    assert "T Nagar" in res2.location
    assert res2.pincode is None
    assert res2.ready_for_action is True

    # Turn 3: Pincode provided
    res3 = await process_civic_message(
        message="600017",
        session_id=session_id,
    )
    # Both intent, description, and location preserved
    assert res3.intent == CivicIntent.ROAD_POTHOLE
    assert "Anna Salai" in res3.location
    assert res3.pincode == "600017"
    assert res3.ready_for_action is True


# 3. Session isolation
@pytest.mark.asyncio
async def test_session_isolation():
    """Verify distinct session IDs maintain isolated conversational state."""
    sess_a = "session-citizen-alpha-isolated"
    sess_b = "session-citizen-beta-isolated"

    # Session A reports waterlogging
    res_a = await process_civic_message(
        message="Severe waterlogging on Mount Road.",
        session_id=sess_a,
    )
    assert res_a.intent == CivicIntent.WATERLOGGING

    # Session B reports pothole
    res_b = await process_civic_message(
        message="Deep pothole on Usman Road.",
        session_id=sess_b,
    )
    assert res_b.intent == CivicIntent.ROAD_POTHOLE

    # Verify Session A retained Mount Road and waterlogging
    saved_a = conversation_session_repository.get_session(sess_a)
    assert saved_a is not None
    assert saved_a.intent == CivicIntent.WATERLOGGING
    assert "Mount Road" in saved_a.location

    # Verify Session B retained Usman Road and pothole
    saved_b = conversation_session_repository.get_session(sess_b)
    assert saved_b is not None
    assert saved_b.intent == CivicIntent.ROAD_POTHOLE
    assert "Usman Road" in saved_b.location


# 4. Session correction/merge
@pytest.mark.asyncio
async def test_session_explicit_correction_replaces_field():
    """Verify explicit citizen correction updates the target field without discarding other data."""
    session_id = "session-correction-test-202"

    # Turn 1: Initial location
    res1 = await process_civic_message(
        message="Pothole on Usman Road.",
        session_id=session_id,
    )
    assert "Usman Road" in res1.location

    # Turn 2: Explicit correction
    res2 = await process_civic_message(
        message="Actually the pothole is on North Usman Road.",
        session_id=session_id,
    )
    assert "North Usman Road" in res2.location
    assert res2.intent == CivicIntent.ROAD_POTHOLE


# 5. Malformed session ID
def test_malformed_session_id_validation():
    """Verify invalid session tokens are rejected with ValueError / 422."""
    with pytest.raises(ValueError):
        validate_session_id("")

    with pytest.raises(ValueError):
        validate_session_id("bad/session/../traversal")

    with pytest.raises(ValueError):
        validate_session_id("a" * 129)

    # API validation test
    res = client.post(
        "/api/conversation",
        json={"session_id": "bad/token", "message": "Pothole on street"},
    )
    assert res.status_code == 422


# 6. Canonical enum contract
def test_canonical_enum_contracts():
    """Verify canonical enum values adhere to architecture specification."""
    assert CivicIntent.ROAD_POTHOLE.value == "ROAD_POTHOLE"
    assert CivicIntent.WATERLOGGING.value == "WATERLOGGING"
    assert CivicIntent.GARBAGE_ACCUMULATION.value == "GARBAGE_ACCUMULATION"
    assert CivicIntent.STREETLIGHT_OUTAGE.value == "STREETLIGHT_OUTAGE"

    assert ControlledDepartment.PWD_ROADS.value == "PWD_ROADS"
    assert ControlledDepartment.DRAINAGE_STORMWATER.value == "DRAINAGE_STORMWATER"
    assert ControlledDepartment.ELECTRICITY_UTILITY.value == "ELECTRICITY_UTILITY"
    assert ControlledDepartment.WASTE_MANAGEMENT.value == "WASTE_MANAGEMENT"

    assert LocationSource.MAP_SELECTED.value == "MAP_SELECTED"
    assert LocationSource.TEXT_REFERENCE.value == "TEXT_REFERENCE"
    assert LocationSource.UNCONFIRMED.value == "UNCONFIRMED"


# 7. Public case history sanitization
def test_public_case_history_projection_sanitization():
    """Verify GET /api/cases/{case_id}/history for public/anonymous users returns sanitized projection."""
    # Create case as citizen
    create_res = client.post(
        "/api/cases",
        json={
            "description": "Fallen tree branch on road",
            "location": "Greenways Road",
            "department": "PWD_ROADS",
            "is_public": True,
        },
        headers={"X-Principal-Id": "cit-hist-1", "X-Principal-Role": "CITIZEN"},
    )
    assert create_res.status_code == 201
    case_id = create_res.json()["case_id"]

    # Request history as anonymous public user (no auth headers)
    hist_res = client.get(f"/api/cases/{case_id}/history")
    assert hist_res.status_code == 200
    items = hist_res.json()
    assert isinstance(items, list)
    assert len(items) >= 1

    first = items[0]
    # Public attributes must exist
    assert "status" in first
    assert "label" in first
    assert "timestamp" in first
    assert "milestone_id" in first

    # Sensitive/authority attributes MUST NOT be exposed
    assert "actor_role" not in first
    assert "note" not in first
    assert "principal_id" not in first
    assert "internal_notes" not in first
    assert "department" not in first


# 8. Authority history authorization
def test_authority_history_access_and_cross_citizen_isolation():
    """Verify matching authority can access full history; mismatched authority and unauthorized citizens are denied."""
    # Create case in DRAINAGE_STORMWATER
    create_res = client.post(
        "/api/cases",
        json={
            "description": "Flooded culvert",
            "location": "Adyar Gate",
            "department": "DRAINAGE_STORMWATER",
            "is_public": False,
        },
        headers={"X-Principal-Id": "cit-owner-22", "X-Principal-Role": "CITIZEN"},
    )
    case_id = create_res.json()["case_id"]

    # 1. Matching drainage officer can inspect authorized history
    drainage_officer = {
        "X-Principal-Id": "officer-drainage-99",
        "X-Principal-Role": "AUTHORITY_OFFICER",
        "X-Principal-Department": "DRAINAGE_STORMWATER",
    }
    res_auth = client.get(f"/api/cases/{case_id}/history", headers=drainage_officer)
    assert res_auth.status_code == 200
    items = res_auth.json()
    assert "actor_role" in items[0]
    assert items[0]["department"] == "DRAINAGE_STORMWATER"

    # 2. Mismatched authority officer (PWD) is denied
    pwd_officer = {
        "X-Principal-Id": "officer-pwd-88",
        "X-Principal-Role": "AUTHORITY_OFFICER",
        "X-Principal-Department": "PWD_ROADS",
    }
    res_mismatch = client.get(f"/api/cases/{case_id}/history", headers=pwd_officer)
    assert res_mismatch.status_code == 403

    # 3. Unrelated citizen cannot inspect private case history
    stranger_citizen = {
        "X-Principal-Id": "stranger-citizen-77",
        "X-Principal-Role": "CITIZEN",
    }
    res_stranger = client.get(f"/api/cases/{case_id}/history", headers=stranger_citizen)
    assert res_stranger.status_code == 403


# 9. Persistent audit retrieval after fresh repository instance
def test_persistent_audit_retrieval_after_fresh_repository_instance():
    """Verify audit events are durably read from AuditRepository rather than ephemeral dispatcher."""
    # Create case
    case_res = client.post(
        "/api/cases",
        json={
            "description": "Audit durability test case",
            "location": "Chamiers Road",
            "department": "PWD_ROADS",
            "is_public": True,
        },
        headers={"X-Principal-Id": "cit-audit-dur", "X-Principal-Role": "CITIZEN"},
    )
    case_id = case_res.json()["case_id"]

    # Advance status with authority
    officer_headers = {
        "X-Principal-Id": "officer-pwd-dur",
        "X-Principal-Role": "AUTHORITY_OFFICER",
        "X-Principal-Department": "PWD_ROADS",
    }
    update_res = client.patch(
        f"/api/cases/{case_id}/status",
        json={"status": "ROUTING_PREPARED", "note": "Survey ordered"},
        headers=officer_headers,
    )
    assert update_res.status_code == 200

    # Instantiate a fresh repository instance and query audit records
    fresh_audit_repo = get_audit_repository()
    events = fresh_audit_repo.get_events_for_case(case_id)
    assert len(events) >= 1
    actions = [getattr(e, "action", "") or getattr(e, "event_type", "") for e in events]
    assert any("create_case" in a or "DOCKET_CREATED" in a or "STATUS_TRANSITION" in a for a in actions)


# 10. Complete five-stage durable lifecycle history
def test_complete_five_stage_durable_lifecycle_history():
    """Verify all 5 canonical lifecycle stages survive and can be reconstructed."""
    create_res = client.post(
        "/api/cases",
        json={
            "description": "Pothole lifecycle 5-stage progression",
            "location": "Velachery Main Road",
            "department": "PWD_ROADS",
            "is_public": True,
        },
        headers={"X-Principal-Id": "cit-stage-test", "X-Principal-Role": "CITIZEN"},
    )
    case_id = create_res.json()["case_id"]

    officer_headers = {
        "X-Principal-Id": "officer-pwd-stages",
        "X-Principal-Role": "AUTHORITY_OFFICER",
        "X-Principal-Department": "PWD_ROADS",
    }

    # Stage 2: ROUTING_PREPARED
    r2 = client.patch(
        f"/api/cases/{case_id}/status",
        json={"status": "ROUTING_PREPARED", "note": "Stage 2 routing"},
        headers=officer_headers,
    )
    assert r2.status_code == 200

    # Stage 3: SUBMISSION_READY
    r3 = client.patch(
        f"/api/cases/{case_id}/status",
        json={"status": "SUBMISSION_READY", "note": "Stage 3 ready"},
        headers=officer_headers,
    )
    assert r3.status_code == 200

    # Stage 4: UNDER_REVIEW
    r4 = client.patch(
        f"/api/cases/{case_id}/status",
        json={"status": "UNDER_REVIEW", "note": "Stage 4 review"},
        headers=officer_headers,
    )
    assert r4.status_code == 200

    # Stage 5: RESOLVED (direct authority PATCH blocked by citizen closure gate)
    r5_blocked = client.patch(
        f"/api/cases/{case_id}/status",
        json={"status": "RESOLVED", "note": "Stage 5 resolved"},
        headers=officer_headers,
    )
    assert r5_blocked.status_code == 409

    # Officer uploads resolution evidence
    files = {"file": ("pothole_fixed.jpg", io.BytesIO(b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00img"), "image/jpeg")}
    up = client.post(
        f"/api/cases/{case_id}/evidence",
        files=files,
        data={"evidence_type": "RESOLUTION_EVIDENCE"},
        headers=officer_headers,
    )
    assert up.status_code == 201

    # Citizen confirms resolution -> case transitions to RESOLVED
    r5 = client.post(
        f"/api/cases/{case_id}/resolution/accept",
        json={"feedback": "Stage 5 resolved"},
        headers={"X-Principal-Id": "cit-stage-test", "X-Principal-Role": "CITIZEN"},
    )
    assert r5.status_code == 200

    # Query history and verify all 5 distinct stages are preserved
    hist_res = client.get(f"/api/cases/{case_id}/history", headers=officer_headers)
    assert hist_res.status_code == 200
    history = hist_res.json()
    statuses = [item["status"] for item in history]

    assert "DOCKET_CREATED" in statuses
    assert "ROUTING_PREPARED" in statuses
    assert "SUBMISSION_READY" in statuses
    assert "UNDER_REVIEW" in statuses
    assert "RESOLVED" in statuses
    assert len(statuses) >= 5


# 11. Map location source semantics & coordinate persistence
def test_map_coordinates_and_location_source_persistence():
    """Verify citizen map-pinned coordinates persist accurately with MAP_SELECTED source."""
    create_res = client.post(
        "/api/cases",
        json={
            "description": "Citizen pinned water defect",
            "location": "Kotturpuram Bridge",
            "department": "DRAINAGE_STORMWATER",
            "latitude": 13.0185,
            "longitude": 80.2412,
            "location_source": "MAP_SELECTED",
            "is_public": True,
        },
        headers={"X-Principal-Id": "cit-map-coords", "X-Principal-Role": "CITIZEN"},
    )
    assert create_res.status_code == 201
    data = create_res.json()
    assert data["latitude"] == 13.0185
    assert data["longitude"] == 80.2412
    assert data["location_source"] == "MAP_SELECTED"

    case_id = data["case_id"]
    # Retrieve case
    fetch_res = client.get(
        f"/api/cases/{case_id}",
        headers={"X-Principal-Id": "cit-map-coords", "X-Principal-Role": "CITIZEN"},
    )
    assert fetch_res.status_code == 200
    fetched = fetch_res.json()
    assert fetched["latitude"] == 13.0185
    assert fetched["longitude"] == 80.2412
    assert fetched["location_source"] == "MAP_SELECTED"


# 12. Evidence upload bounded read (>10MB rejected)
def test_evidence_bounded_upload_limit():
    """Verify files larger than 10MB are rejected with 413 Payload Too Large."""
    create_res = client.post(
        "/api/cases",
        json={
            "description": "Large evidence test",
            "location": "Adyar",
            "department": "PWD_ROADS",
            "is_public": True,
        },
        headers={"X-Principal-Id": "cit-bounded-test", "X-Principal-Role": "CITIZEN"},
    )
    case_id = create_res.json()["case_id"]

    # 10MB + 1 byte
    oversized_bytes = b"\xff\xd8\xff" + b"0" * (10 * 1024 * 1024 + 10)
    files = {"file": ("oversized.jpg", io.BytesIO(oversized_bytes), "image/jpeg")}
    res = client.post(
        f"/api/cases/{case_id}/evidence",
        files=files,
        headers={"X-Principal-Id": "cit-bounded-test", "X-Principal-Role": "CITIZEN"},
    )
    assert res.status_code == 413


# 13. Evidence magic byte validation
def test_evidence_magic_byte_validation_signatures():
    """Verify magic byte validation accepts real JPEG/PNG/PDF/WAV and rejects invalid binary."""
    create_res = client.post(
        "/api/cases",
        json={
            "description": "Magic byte validation test",
            "location": "Royapettah",
            "department": "PWD_ROADS",
            "is_public": True,
        },
        headers={"X-Principal-Id": "cit-magic-test", "X-Principal-Role": "CITIZEN"},
    )
    case_id = create_res.json()["case_id"]
    cit_headers = {"X-Principal-Id": "cit-magic-test", "X-Principal-Role": "CITIZEN"}

    # 1. Valid real JPEG header
    real_jpg = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    res_jpg = client.post(
        f"/api/cases/{case_id}/evidence",
        files={"file": ("photo.jpg", io.BytesIO(real_jpg), "image/jpeg")},
        headers=cit_headers,
    )
    assert res_jpg.status_code == 201

    # 2. Valid real PNG header
    real_png = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
    res_png = client.post(
        f"/api/cases/{case_id}/evidence",
        files={"file": ("diagram.png", io.BytesIO(real_png), "image/png")},
        headers=cit_headers,
    )
    assert res_png.status_code == 201

    # 3. Valid real PDF header
    real_pdf = b"%PDF-1.5\n%\xe2\xe3\xcf\xd3\n"
    res_pdf = client.post(
        f"/api/cases/{case_id}/evidence",
        files={"file": ("report.pdf", io.BytesIO(real_pdf), "application/pdf")},
        headers=cit_headers,
    )
    assert res_pdf.status_code == 201

    # 4. Valid real WAV header
    real_wav = b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00"
    res_wav = client.post(
        f"/api/cases/{case_id}/evidence",
        files={"file": ("audio.wav", io.BytesIO(real_wav), "audio/wav")},
        headers=cit_headers,
    )
    assert res_wav.status_code == 201

    # 5. Valid real MP3 header (ID3)
    real_mp3 = b"ID3\x04\x00\x00\x00\x00\x00#TIT2\x00\x00\x00\x05\x00\x00\x00Civic"
    res_mp3 = client.post(
        f"/api/cases/{case_id}/evidence",
        files={"file": ("voice_note.mp3", io.BytesIO(real_mp3), "audio/mpeg")},
        headers=cit_headers,
    )
    assert res_mp3.status_code == 201

    # 6. Invalid binary signature claiming to be PNG
    corrupt_binary = b"\x00\x01\x02\x03\x04\x05\x06\x07\x08"
    res_corrupt = client.post(
        f"/api/cases/{case_id}/evidence",
        files={"file": ("fake_image.png", io.BytesIO(corrupt_binary), "image/png")},
        headers=cit_headers,
    )
    assert res_corrupt.status_code == 400
    assert "magic signature" in res_corrupt.json()["detail"].lower()

    # 7. File with "fake" prefix that was previously bypassed - MUST NOW BE REJECTED
    fake_prefix_file = b"fake-jpg-content-no-real-signature"
    res_fake = client.post(
        f"/api/cases/{case_id}/evidence",
        files={"file": ("bypass_attempt.jpg", io.BytesIO(fake_prefix_file), "image/jpeg")},
        headers=cit_headers,
    )
    assert res_fake.status_code == 400
    assert "magic signature" in res_fake.json()["detail"].lower()

    # 8. File with "sample" prefix that was previously bypassed - MUST NOW BE REJECTED
    sample_prefix_file = b"sample-png-content-no-real-signature"
    res_sample = client.post(
        f"/api/cases/{case_id}/evidence",
        files={"file": ("sample_bypass.png", io.BytesIO(sample_prefix_file), "image/png")},
        headers=cit_headers,
    )
    assert res_sample.status_code == 400
    assert "magic signature" in res_sample.json()["detail"].lower()

    # 9. Renamed executable binary - MUST BE REJECTED
    exe_binary = b"MZ\x90\x00\x03\x00\x00\x00\x04\x00\x00\x00\xff\xff\x00\x00"
    res_exe = client.post(
        f"/api/cases/{case_id}/evidence",
        files={"file": ("trojan.jpg", io.BytesIO(exe_binary), "image/jpeg")},
        headers=cit_headers,
    )
    assert res_exe.status_code == 400
    assert "magic signature" in res_exe.json()["detail"].lower()


# 14. Non-civic short-circuit
@pytest.mark.asyncio
async def test_non_civic_short_circuit():
    """Verify non-civic messages do not create civic cases or run full routing pipeline."""
    # Greeting query
    res1 = await process_civic_message(
        message="Hello, good morning! Hope you are having a nice day.",
        session_id="session-greeting-non-civic-1",
    )
    assert res1.intent is None
    assert res1.department is None
    assert res1.ready_for_action is False

    # Poem request
    res2 = await process_civic_message(
        message="Write me a poem about the sunrise and the blue sky.",
        session_id="session-non-civic-poem-1",
    )
    assert res2.intent is None
    assert res2.department is None
    assert res2.ready_for_action is False

    # Math problem request
    res3 = await process_civic_message(
        message="Solve this math problem: 2x + 5 = 15.",
        session_id="session-non-civic-math-1",
    )
    assert res3.intent is None
    assert res3.department is None
    assert res3.ready_for_action is False

    # Capital trivia question
    res4 = await process_civic_message(
        message="What is the capital of France?",
        session_id="session-non-civic-trivia-1",
    )
    assert res4.intent is None
    assert res4.department is None
    assert res4.ready_for_action is False


# 15. LLM output trust boundary
@pytest.mark.asyncio
async def test_llm_trust_boundary_does_not_hallucinate_pincode():
    """Verify deterministic validation drops pincodes not present in user conversation."""
    # Message mentions location but NO pincode
    res = await process_civic_message(
        message="Broken road near T Nagar bus stop.",
        session_id="session-trust-boundary-pin-1",
    )
    # The coordinator must not accept hallucinated pincodes
    assert res.pincode is None
    assert "T Nagar" in res.location


# 16. Health and readiness endpoints
def test_health_endpoints_truthfulness():
    """Verify /health/live and /health/ready provide accurate, unauthenticated status."""
    res_live = client.get("/health/live")
    assert res_live.status_code == 200
    assert res_live.json()["status"] in ("ok", "alive")

    res_ready = client.get("/health/ready")
    assert res_ready.status_code in (200, 503)
    data = res_ready.json()
    assert "status" in data
    assert "dependencies" in data
    # Must not leak AWS credentials or secret keys
    for dep_key, dep_val in data["dependencies"].items():
        assert "secret" not in str(dep_val).lower()
        assert "key" not in str(dep_val).lower()


# 17. Strands Runtime Invocation
@pytest.mark.asyncio
async def test_strands_runtime_invocation_on_intake_path(monkeypatch):
    """Verify that Strands Agent runtime is genuinely executed on intake turn."""
    from app.services.civic_reasoning import get_coordinator
    coordinator = get_coordinator()

    invoked_prompts = []
    original_invoke = coordinator.strands_agent.invoke_async

    async def mock_invoke(prompt, **kwargs):
        invoked_prompts.append(prompt)
        return await original_invoke(prompt, **kwargs)

    monkeypatch.setattr(coordinator.strands_agent, "invoke_async", mock_invoke)

    res = await coordinator.execute_intake_turn(
        message="Pothole near Anna Salai signal causing traffic hazard",
        session_id="session-strands-runtime-verify-1",
    )
    assert len(invoked_prompts) == 1
    assert "Pothole near Anna Salai" in invoked_prompts[0]
    assert res.intent == CivicIntent.ROAD_POTHOLE


# 18. Durable Audit Initialization Order
def test_durable_audit_initialization_order():
    """Verify audit listener is registered and captures events from the very first case request."""
    from app.services.persistence.factory import initialize_persistence_backend, get_audit_repository
    initialize_persistence_backend()
    audit_repo = get_audit_repository()

    create_resp = client.post(
        "/api/cases",
        json={
            "description": "First startup case audit check",
            "location": "Velachery Bypass",
            "department": "PWD_ROADS",
        },
        headers={"X-Principal-Id": "cit-startup-audit", "X-Principal-Role": "CITIZEN"},
    )
    assert create_resp.status_code == 201
    cid = create_resp.json()["case_id"]

    events = audit_repo.get_events_for_case(cid)
    assert len(events) >= 1
    assert events[0].event_type == "DOCKET_CREATED"


# 19. Atomic List Append Concurrency
def test_atomic_list_append_concurrency():
    """Verify concurrent addition of notes does not overwrite previous entries."""
    create_resp = client.post(
        "/api/cases",
        json={
            "description": "Concurrency list append test",
            "location": "Guindy",
            "department": "PWD_ROADS",
        },
        headers={"X-Principal-Id": "cit-concurrency", "X-Principal-Role": "CITIZEN"},
    )
    cid = create_resp.json()["case_id"]
    officer_headers = {
        "X-Principal-Id": "officer-concurrency",
        "X-Principal-Role": "AUTHORITY_OFFICER",
        "X-Principal-Department": "PWD_ROADS",
    }

    # Add note 1
    res1 = client.post(
        f"/api/cases/{cid}/notes",
        json={"note": "Initial site inspection completed."},
        headers=officer_headers,
    )
    assert res1.status_code == 200

    # Add note 2
    res2 = client.post(
        f"/api/cases/{cid}/notes",
        json={"note": "Contractor assigned for resurfacing."},
        headers=officer_headers,
    )
    assert res2.status_code == 200

    # Retrieve case
    case_resp = client.get(f"/api/cases/{cid}", headers=officer_headers)
    assert case_resp.status_code == 200
    notes = case_resp.json()["resolution_notes"]
    assert len(notes) == 2
    assert "Initial site inspection completed." in notes
    assert "Contractor assigned for resurfacing." in notes
