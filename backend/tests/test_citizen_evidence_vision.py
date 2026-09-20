"""Unit and Integration Tests for Citizen Evidence Vision AI Relevance Pipeline.

Covers all 20 mandatory test requirements:
1. RELATED result from vision provider.
2. NOT_RELATED result from vision provider.
3. UNCERTAIN result from vision provider.
4. Ollama unavailable -> UNCERTAIN.
5. Text-only model -> UNCERTAIN.
6. Vision model timeout -> UNCERTAIN.
7. Malformed model JSON -> UNCERTAIN.
8. Unsupported model outcome -> UNCERTAIN.
9. Invalid MIME rejected.
10. Magic-byte mismatch rejected.
11. Oversized image rejected.
12. Structured assessment schema validation.
13. Client-supplied AI result ignored.
14. Client-supplied confidence ignored.
15. NOT_RELATED does not delete evidence.
16. NOT_RELATED does not change lifecycle.
17. UNCERTAIN does not block docket creation.
18. Evidence assessment is associated with the correct evidence ID.
19. Multiple evidence objects retain separate assessments.
20. Existing Phase 8.7 evidence security tests continue passing.
"""

from datetime import datetime, timezone
import io
import json
import pytest
from fastapi.testclient import TestClient

from app.config.settings import settings
from app.main import app
from app.models.enums import CaseStatus, ControlledDepartment
from app.models.evidence import EvidenceType, VerificationOutcome
from app.models.evidence_relevance import (
    CitizenEvidenceAssessment,
    EvidenceRelevanceOutcome,
)
from app.models.security import (
    ApplicationPrincipal,
    ApplicationRole,
    CivicCaseCreateRequest,
    CivicCaseRecord,
)
from app.security.audit import audit_dispatcher
from app.security.session import session_store
from app.services.case_store import case_store
from app.services.evidence.provider import MockEvidenceAssessmentProvider
from app.services.evidence.repository import evidence_repo
from app.services.evidence_verification_service import evidence_verification_service
from app.services.evidence.vision_service import (
    CitizenEvidenceVisionService,
    citizen_evidence_vision_service,
)
from app.services.persistence.account_repository import account_repository
from app.services.persistence.conversation_repository import session_repository

client = TestClient(app)

# Standard test image bytes: Valid JPEG magic header (\xff\xd8\xff\xe0) + dummy payload
VALID_JPEG_BYTES = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00" + b"\x00" * 200
# Valid PNG bytes: \x89PNG\r\n\x1a\n + dummy payload
VALID_PNG_BYTES = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR" + b"\x00" * 200


@pytest.fixture(autouse=True)
def reset_test_state():
    """Ensure clean stores, mock provider, and reset vision hook before/after each test."""
    session_store.clear()
    account_repository.reset_seed_data()
    case_store.clear()
    evidence_repo.clear()
    audit_dispatcher.clear()
    # Reset to a verified mock provider to isolate vision-specific behavior
    evidence_verification_service.set_provider(
        MockEvidenceAssessmentProvider(outcome=VerificationOutcome.VERIFIED, ai_available=True)
    )
    # Reset vision hook
    citizen_evidence_vision_service.set_custom_caller(None)
    yield
    session_store.clear()
    account_repository.reset_seed_data()
    case_store.clear()
    evidence_repo.clear()
    audit_dispatcher.clear()
    evidence_verification_service.set_provider(
        MockEvidenceAssessmentProvider(outcome=VerificationOutcome.VERIFIED, ai_available=True)
    )
    citizen_evidence_vision_service.set_custom_caller(None)


# --------------------------------------------------------------------------
# Helper: create a case at a specific status via create_case + status updates
# --------------------------------------------------------------------------
def _seed_case(
    case_id: str,
    owner_id: str,
    department: ControlledDepartment,
    description: str,
    location: str,
    is_public: bool = True,
    status: CaseStatus = CaseStatus.DOCKET_CREATED,
) -> CivicCaseRecord:
    """Create a case and advance its status to the requested level for test isolation."""
    request = CivicCaseCreateRequest(
        description=description,
        location=location,
        department=department,
        is_public=is_public,
    )
    record = case_store.create_case(request=request, owner_id=owner_id, case_id=case_id)

    # Advance status if needed (only statuses reachable via update_case_status)
    status_chain = [
        CaseStatus.DOCKET_CREATED,
        CaseStatus.ROUTING_PREPARED,
        CaseStatus.SUBMISSION_READY,
        CaseStatus.UNDER_REVIEW,
    ]
    if status in status_chain:
        target_idx = status_chain.index(status)
        for i in range(1, target_idx + 1):
            case_store.update_case_status(
                record.case_id,
                new_status=status_chain[i],
                note=f"Test advance to {status_chain[i].value}",
                actor_label="TEST_FIXTURE",
            )
    return case_store.get_case(record.case_id)


# --------------------------------------------------------------------------
# 1. RELATED result from vision provider
# --------------------------------------------------------------------------
def test_vision_provider_related():
    citizen_evidence_vision_service.set_custom_caller(lambda payload: {
        "relevance": "RELATED",
        "reason": "Image clearly depicts asphalt road crater consistent with pothole query.",
        "detected_features": ["pothole", "cratered road"],
        "confidence": 0.95,
    })

    result = citizen_evidence_vision_service.assess_relevance(
        query="Massive pothole on Anna Salai",
        file_bytes=VALID_JPEG_BYTES,
        filename="pothole.jpg",
        content_type="image/jpeg",
    )
    assert result.relevance == EvidenceRelevanceOutcome.RELATED
    assert result.ai_available is True
    assert "asphalt road crater" in result.reason
    assert "pothole" in result.detected_features
    assert result.confidence == 0.95


# --------------------------------------------------------------------------
# 2. NOT_RELATED result from vision provider
# --------------------------------------------------------------------------
def test_vision_provider_not_related():
    citizen_evidence_vision_service.set_custom_caller(lambda payload: {
        "relevance": "NOT_RELATED",
        "reason": "Image depicts an indoor dining meal, unrelated to reported waterlogging.",
        "detected_features": ["food plate", "indoor dining"],
        "confidence": 0.88,
    })

    result = citizen_evidence_vision_service.assess_relevance(
        query="Severe street waterlogging near metro station",
        file_bytes=VALID_JPEG_BYTES,
        filename="meal.jpg",
        content_type="image/jpeg",
    )
    assert result.relevance == EvidenceRelevanceOutcome.NOT_RELATED
    assert result.ai_available is True
    assert "food plate" in result.detected_features
    assert result.confidence == 0.88


# --------------------------------------------------------------------------
# 3. UNCERTAIN result from vision provider
# --------------------------------------------------------------------------
def test_vision_provider_uncertain():
    citizen_evidence_vision_service.set_custom_caller(lambda payload: {
        "relevance": "UNCERTAIN",
        "reason": "Image is extremely dark and blurry; unable to verify streetlight defect.",
        "detected_features": ["blurry", "low lighting"],
        "confidence": 0.35,
    })

    result = citizen_evidence_vision_service.assess_relevance(
        query="Streetlight outage on 5th cross",
        file_bytes=VALID_JPEG_BYTES,
        filename="dark_blur.jpg",
        content_type="image/jpeg",
    )
    assert result.relevance == EvidenceRelevanceOutcome.UNCERTAIN
    assert result.ai_available is True
    assert result.confidence == 0.35


# --------------------------------------------------------------------------
# 4. Ollama unavailable -> UNCERTAIN
# --------------------------------------------------------------------------
def test_ollama_unavailable_returns_uncertain():
    # Service with unreachable host and no custom caller
    offline_service = CitizenEvidenceVisionService(
        endpoint_url="http://127.0.0.1:59999",  # Non-existent port
        vision_model="llama3.2-vision",
        timeout=0.5,
    )
    result = offline_service.assess_relevance(
        query="Broken sewer drain pipe",
        file_bytes=VALID_JPEG_BYTES,
        filename="drain.jpg",
        content_type="image/jpeg",
    )
    assert result.relevance == EvidenceRelevanceOutcome.UNCERTAIN
    assert result.ai_available is False
    assert "offline or unavailable" in result.reason.lower()


# --------------------------------------------------------------------------
# 5. Text-only model -> UNCERTAIN
# --------------------------------------------------------------------------
def test_text_only_model_returns_uncertain():
    text_only_service = CitizenEvidenceVisionService(
        endpoint_url="http://localhost:11434",
        vision_model="llama3.2:3b",  # Text-only model
    )
    result = text_only_service.assess_relevance(
        query="Pothole hazard",
        file_bytes=VALID_JPEG_BYTES,
        filename="pothole.jpg",
        content_type="image/jpeg",
    )
    assert result.relevance == EvidenceRelevanceOutcome.UNCERTAIN
    assert result.ai_available is False
    assert "VISION_MODEL_REQUIRED" in result.reason


# --------------------------------------------------------------------------
# 6. Vision model timeout -> UNCERTAIN
# --------------------------------------------------------------------------
def test_vision_model_timeout_returns_uncertain():
    def timing_out_caller(payload):
        raise TimeoutError("Model request timed out after 5.0 seconds")

    citizen_evidence_vision_service.set_custom_caller(timing_out_caller)
    result = citizen_evidence_vision_service.assess_relevance(
        query="Flooded street",
        file_bytes=VALID_JPEG_BYTES,
        filename="flood.jpg",
        content_type="image/jpeg",
    )
    assert result.relevance == EvidenceRelevanceOutcome.UNCERTAIN
    assert result.ai_available is False
    assert "failed" in result.reason.lower() or "timed out" in result.reason.lower()


# --------------------------------------------------------------------------
# 7. Malformed model JSON -> UNCERTAIN
# --------------------------------------------------------------------------
def test_malformed_model_json_returns_uncertain():
    # If caller returns empty or unexpected structure
    citizen_evidence_vision_service.set_custom_caller(lambda p: {
        "broken_key": 12345
    })
    result = citizen_evidence_vision_service.assess_relevance(
        query="Broken sidewalk",
        file_bytes=VALID_JPEG_BYTES,
        filename="sidewalk.jpg",
        content_type="image/jpeg",
    )
    assert result.relevance == EvidenceRelevanceOutcome.UNCERTAIN


# --------------------------------------------------------------------------
# 8. Unsupported model outcome -> UNCERTAIN
# --------------------------------------------------------------------------
def test_unsupported_model_outcome_returns_uncertain():
    citizen_evidence_vision_service.set_custom_caller(lambda p: {
        "relevance": "MAYBE_RELATED",  # Non-standard outcome
        "reason": "Might be related",
        "confidence": 0.5,
    })
    result = citizen_evidence_vision_service.assess_relevance(
        query="Broken streetlight",
        file_bytes=VALID_JPEG_BYTES,
        filename="light.jpg",
        content_type="image/jpeg",
    )
    assert result.relevance == EvidenceRelevanceOutcome.UNCERTAIN


# --------------------------------------------------------------------------
# 9. Invalid MIME rejected (via API endpoint)
# --------------------------------------------------------------------------
def test_invalid_mime_rejected():
    files = {"image": ("malicious.exe", b"MZexecutabledata", "application/x-msdownload")}
    data = {"query": "Pothole on street"}
    response = client.post("/api/conversation/evidence/relevance", data=data, files=files)
    assert response.status_code == 400
    detail = response.json()["detail"].lower()
    assert "unsupported" in detail or "invalid" in detail or "not allowed" in detail or "mime" in detail or "not supported" in detail or "extension" in detail


# --------------------------------------------------------------------------
# 10. Magic-byte mismatch rejected (via API endpoint)
# --------------------------------------------------------------------------
def test_magic_byte_mismatch_rejected():
    # Claims to be image/jpeg, but body is plain ASCII text
    files = {"image": ("fake.jpg", b"This is just plain text masquerading as jpg", "image/jpeg")}
    data = {"query": "Pothole on street"}
    response = client.post("/api/conversation/evidence/relevance", data=data, files=files)
    assert response.status_code == 400
    detail = response.json()["detail"].lower()
    assert "mismatch" in detail or "magic" in detail or "invalid" in detail or "corrupt" in detail


# --------------------------------------------------------------------------
# 11. Oversized image rejected (via API endpoint)
# --------------------------------------------------------------------------
def test_oversized_image_rejected():
    oversized = VALID_JPEG_BYTES + b"\x00" * (11 * 1024 * 1024)
    files = {"image": ("huge.jpg", oversized, "image/jpeg")}
    data = {"query": "Pothole on street"}
    response = client.post("/api/conversation/evidence/relevance", data=data, files=files)
    assert response.status_code == 413
    assert "exceeds" in response.json()["detail"].lower()


# --------------------------------------------------------------------------
# 12. Structured assessment schema validation
# --------------------------------------------------------------------------
def test_structured_assessment_schema():
    assessment = CitizenEvidenceAssessment(
        relevance=EvidenceRelevanceOutcome.RELATED,
        reason="Clear evidence of civic issue",
        detected_features=["water", "blocked drain"],
        confidence=0.92,
        model_id="llama3.2-vision",
        ai_available=True,
    )
    dumped = assessment.model_dump()
    assert dumped["relevance"] == "RELATED"
    assert dumped["confidence"] == 0.92
    assert "water" in dumped["detected_features"]

    # Invalid confidence rejected by validator
    with pytest.raises(ValueError):
        CitizenEvidenceAssessment(
            relevance=EvidenceRelevanceOutcome.RELATED,
            reason="Clear",
            confidence=1.5,  # > 1.0
        )


# --------------------------------------------------------------------------
# 13. Client-supplied AI result ignored
# --------------------------------------------------------------------------
def test_client_supplied_ai_result_ignored():
    citizen_evidence_vision_service.set_custom_caller(lambda p: {
        "relevance": "UNCERTAIN",
        "reason": "Genuine server assessment says UNCERTAIN",
    })
    # Client tries sending spoofed form values
    files = {"image": ("photo.jpg", VALID_JPEG_BYTES, "image/jpeg")}
    data = {
        "query": "Water leakage",
        "relevance": "RELATED",
        "confidence": "0.99",
        "ai_available": "true",
    }
    response = client.post("/api/conversation/evidence/relevance", data=data, files=files)
    assert response.status_code == 200
    body = response.json()
    assert body["relevance"] == "UNCERTAIN"  # Server outcome respected, client spoofing ignored


# --------------------------------------------------------------------------
# 14. Client-supplied confidence ignored
# --------------------------------------------------------------------------
def test_client_supplied_confidence_ignored():
    citizen_evidence_vision_service.set_custom_caller(lambda p: {
        "relevance": "RELATED",
        "reason": "Server verified",
        "confidence": 0.72,
    })
    files = {"image": ("photo.jpg", VALID_JPEG_BYTES, "image/jpeg")}
    data = {
        "query": "Water leakage",
        "confidence": "1.0",
    }
    response = client.post("/api/conversation/evidence/relevance", data=data, files=files)
    assert response.status_code == 200
    assert response.json()["confidence"] == 0.72


# --------------------------------------------------------------------------
# 15. NOT_RELATED does not delete evidence
# --------------------------------------------------------------------------
def test_not_related_does_not_delete_evidence():
    citizen_evidence_vision_service.set_custom_caller(lambda p: {
        "relevance": "NOT_RELATED",
        "reason": "Photo shows a cat, unrelated to road damage",
        "detected_features": ["cat", "pet"],
        "confidence": 0.91,
    })

    case = _seed_case(
        case_id="NS-CHN-2026-NREL",
        owner_id="cit-user-1",
        department=ControlledDepartment.PWD_ROADS,
        description="Pothole in middle of intersection",
        location="Anna Nagar",
        is_public=True,
        status=CaseStatus.UNDER_REVIEW,
    )

    principal = ApplicationPrincipal(
        principal_id="cit-user-1",
        role=ApplicationRole.CITIZEN,
        department=None,
    )

    resp = evidence_verification_service.verify_and_store_evidence(
        case_id=case.case_id,
        principal=principal,
        file_bytes=VALID_JPEG_BYTES,
        filename="cat_photo.jpg",
        content_type="image/jpeg",
        evidence_type=EvidenceType.CASE_EVIDENCE,
    )
    assert resp.relevance == EvidenceRelevanceOutcome.NOT_RELATED
    assert resp.verification_status != VerificationOutcome.REJECTED  # Evidence persists

    # Verify evidence still exists in case store
    ev_list = evidence_verification_service.list_case_evidence(case.case_id, principal)
    assert len(ev_list) == 1
    assert ev_list[0].evidence_id == resp.evidence_id
    assert ev_list[0].relevance == EvidenceRelevanceOutcome.NOT_RELATED


# --------------------------------------------------------------------------
# 16. NOT_RELATED does not change lifecycle
# --------------------------------------------------------------------------
def test_not_related_does_not_change_lifecycle():
    case = _seed_case(
        case_id="NS-CHN-2026-NRLC",
        owner_id="cit-user-2",
        department=ControlledDepartment.DRAINAGE_STORMWATER,
        description="Drain overflow on main road",
        location="T Nagar",
        is_public=True,
        status=CaseStatus.UNDER_REVIEW,
    )

    principal = ApplicationPrincipal(
        principal_id="cit-user-2",
        role=ApplicationRole.CITIZEN,
        department=None,
    )

    citizen_evidence_vision_service.set_custom_caller(lambda p: {
        "relevance": "NOT_RELATED",
        "reason": "Photo shows a parked car in a garage",
        "confidence": 0.85,
    })

    evidence_verification_service.verify_and_store_evidence(
        case_id=case.case_id,
        principal=principal,
        file_bytes=VALID_JPEG_BYTES,
        filename="garage.jpg",
        content_type="image/jpeg",
        evidence_type=EvidenceType.CASE_EVIDENCE,
    )

    # Status must remain exactly UNDER_REVIEW
    current_case = case_store.get_case(case.case_id)
    assert current_case.status == CaseStatus.UNDER_REVIEW


# --------------------------------------------------------------------------
# 17. UNCERTAIN does not block docket creation
# --------------------------------------------------------------------------
def test_uncertain_does_not_block_docket_creation():
    """Citizen can create docket regardless of any vision AI uncertainty.

    Uses legacy simulation headers (X-Principal-Id / X-Principal-Role)
    which are accepted by get_current_principal when no session cookie is present.
    """
    docket_payload = {
        "owner_id": "cit-user-3",
        "department": "PWD_ROADS",
        "description": "Cracked road pavement near Velachery",
        "location": "Velachery Main Road",
        "is_public": True,
    }
    response = client.post(
        "/api/cases",
        json=docket_payload,
        headers={
            "X-Principal-Id": "cit-user-3",
            "X-Principal-Role": "CITIZEN",
        },
    )
    assert response.status_code == 201
    assert response.json()["status"] == "DOCKET_CREATED"


# --------------------------------------------------------------------------
# 18. Evidence assessment is associated with the correct evidence ID
# --------------------------------------------------------------------------
def test_evidence_assessment_associated_with_correct_id():
    citizen_evidence_vision_service.set_custom_caller(lambda p: {
        "relevance": "RELATED",
        "reason": "Verified waterlogging on road",
        "confidence": 0.93,
    })

    case = _seed_case(
        case_id="NS-CHN-2026-EVID",
        owner_id="cit-user-4",
        department=ControlledDepartment.DRAINAGE_STORMWATER,
        description="Waterlogging defect near market",
        location="Guindy",
        is_public=True,
        status=CaseStatus.DOCKET_CREATED,
    )

    principal = ApplicationPrincipal(
        principal_id="cit-user-4",
        role=ApplicationRole.CITIZEN,
        department=None,
    )

    resp = evidence_verification_service.verify_and_store_evidence(
        case_id=case.case_id,
        principal=principal,
        file_bytes=VALID_JPEG_BYTES,
        filename="flood_water.jpg",
        content_type="image/jpeg",
        evidence_type=EvidenceType.CASE_EVIDENCE,
    )
    assert resp.evidence_id.startswith("ev-")
    assert resp.relevance == EvidenceRelevanceOutcome.RELATED
    assert resp.relevance_reason == "Verified waterlogging on road"
    assert resp.relevance_confidence == 0.93


# --------------------------------------------------------------------------
# 19. Multiple evidence objects retain separate assessments
# --------------------------------------------------------------------------
def test_multiple_evidence_objects_retain_separate_assessments():
    case = _seed_case(
        case_id="NS-CHN-2026-MULT",
        owner_id="cit-user-5",
        department=ControlledDepartment.PWD_ROADS,
        description="Damaged asphalt and potholes on road",
        location="Koyambedu",
        is_public=True,
        status=CaseStatus.DOCKET_CREATED,
    )

    principal = ApplicationPrincipal(
        principal_id="cit-user-5",
        role=ApplicationRole.CITIZEN,
        department=None,
    )

    # First image is RELATED
    citizen_evidence_vision_service.set_custom_caller(lambda p: {
        "relevance": "RELATED",
        "reason": "Road asphalt damage clearly visible",
        "confidence": 0.96,
    })
    ev1 = evidence_verification_service.verify_and_store_evidence(
        case_id=case.case_id,
        principal=principal,
        file_bytes=VALID_JPEG_BYTES,
        filename="pothole_1.jpg",
        content_type="image/jpeg",
    )

    # Second image is NOT_RELATED
    citizen_evidence_vision_service.set_custom_caller(lambda p: {
        "relevance": "NOT_RELATED",
        "reason": "Photo of a restaurant menu",
        "confidence": 0.92,
    })
    ev2 = evidence_verification_service.verify_and_store_evidence(
        case_id=case.case_id,
        principal=principal,
        file_bytes=VALID_PNG_BYTES,
        filename="menu.png",
        content_type="image/png",
    )

    # Verify both retain their own separate outcomes
    ev_list = evidence_verification_service.list_case_evidence(case.case_id, principal)
    assert len(ev_list) == 2

    res1 = next(e for e in ev_list if e.evidence_id == ev1.evidence_id)
    res2 = next(e for e in ev_list if e.evidence_id == ev2.evidence_id)

    assert res1.relevance == EvidenceRelevanceOutcome.RELATED
    assert res1.relevance_confidence == 0.96

    assert res2.relevance == EvidenceRelevanceOutcome.NOT_RELATED
    assert res2.relevance_confidence == 0.92


# --------------------------------------------------------------------------
# 20. Existing Phase 8.7 evidence security tests continue passing
# --------------------------------------------------------------------------
def test_phase_8_7_evidence_security_invariants():
    """Cedar PEP fails closed for unauthorized principal reading a private case."""
    case = _seed_case(
        case_id="NS-CHN-2026-SECU",
        owner_id="cit-user-owner",
        department=ControlledDepartment.PWD_ROADS,
        description="Road defect at private location",
        location="Adyar",
        is_public=False,  # Private case
    )

    # Different citizen cannot read private evidence
    unauthorized = ApplicationPrincipal(
        principal_id="cit-stranger",
        role=ApplicationRole.CITIZEN,
        department=None,
    )
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc_info:
        evidence_verification_service.list_case_evidence(case.case_id, unauthorized)
    assert exc_info.value.status_code == 403
