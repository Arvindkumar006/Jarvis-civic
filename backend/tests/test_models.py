"""Tests for Canonical Models, Controlled Enums, and Validators in Phase 1."""

from datetime import datetime, timezone
import pytest
from pydantic import ValidationError

from app.models.enums import (
    CaseStatus,
    CivicIntent,
    ControlledDepartment,
    EvidenceType,
    UrgencyLevel,
)
from app.models.civic_state import CanonicalCivicState
from app.models.common import (
    ConversationRequest,
    ConversationResponse,
    generate_case_id,
    validate_case_id,
)


class TestControlledEnums:
    """Validate that enums strictly adhere to the controlled vocabulary."""

    def test_civic_intent_members(self):
        expected = {
            "WATERLOGGING",
            "ROAD_POTHOLE",
            "STREETLIGHT_OUTAGE",
            "GARBAGE_ACCUMULATION",
            "DRAINAGE_BLOCKAGE",
            "WATER_SUPPLY_ISSUE",
            "ELECTRICITY_OUTAGE",
            "PUBLIC_INFRASTRUCTURE_DAMAGE",
            "OTHER_CIVIC_ISSUE",
        }
        actual = {intent.value for intent in CivicIntent}
        assert actual == expected

    def test_controlled_department_members(self):
        expected = {
            "MUNICIPAL_CORPORATION",
            "PWD_ROADS",
            "WATER_SUPPLY",
            "ELECTRICITY_UTILITY",
            "WASTE_MANAGEMENT",
            "DRAINAGE_STORMWATER",
            "OTHER_MANUAL_REVIEW",
        }
        actual = {dept.value for dept in ControlledDepartment}
        assert actual == expected

    def test_urgency_level_members(self):
        expected = {"LOW", "MEDIUM", "HIGH", "CRITICAL"}
        actual = {urgency.value for urgency in UrgencyLevel}
        assert actual == expected

    def test_case_status_members(self):
        expected = {
            "DRAFT",
            "DOCKET_CREATED",
            "ROUTING_PREPARED",
            "SUBMISSION_READY",
            "UNDER_REVIEW",
            "RESOLVED",
        }
        actual = {status.value for status in CaseStatus}
        assert actual == expected

    def test_evidence_type_members(self):
        expected = {"TEXT", "IMAGE", "AUDIO", "DOCUMENT"}
        actual = {ev.value for ev in EvidenceType}
        assert actual == expected

    def test_invalid_enum_rejection(self):
        with pytest.raises(ValidationError):
            CanonicalCivicState(intent="NON_EXISTENT_INTENT")

        with pytest.raises(ValidationError):
            CanonicalCivicState(department="FEDERAL_MINISTRY")

        with pytest.raises(ValidationError):
            CanonicalCivicState(urgency="EMERGENCY_NOW")

        with pytest.raises(ValidationError):
            CanonicalCivicState(status="PENDING_ARBITRATION")


class TestCanonicalCivicState:
    """Validate canonical state construction, edge cases, and incomplete states."""

    def test_valid_complete_civic_state(self):
        state = CanonicalCivicState(
            case_id="NS-CHN-2026-9E4B",
            session_id="sess-12345",
            intent=CivicIntent.ROAD_POTHOLE,
            department=ControlledDepartment.PWD_ROADS,
            description="Deep crater pothole causing vehicle damage",
            location="100 Feet Road, Indiranagar",
            landmark="Near Metro Pillar 42",
            pincode="560038",
            urgency=UrgencyLevel.HIGH,
            urgency_rationale="Active risk of two-wheeler accidents",
            evidence=[EvidenceType.IMAGE, EvidenceType.TEXT],
            evidence_uris=["storage/evidence/pothole1.jpg"],
            citizen_language="English",
            confidence=0.95,
            missing_fields=[],
            ready_for_action=True,
            status=CaseStatus.DRAFT,
        )
        assert state.case_id == "NS-CHN-2026-9E4B"
        assert state.pincode == "560038"
        assert isinstance(state.pincode, str)
        assert state.ready_for_action is True
        assert state.confidence == 0.95
        assert isinstance(state.created_at, datetime)
        assert state.created_at.tzinfo is not None

    def test_incomplete_complaint_scenario(self):
        """Scenario: 'There is waterlogging outside my house whenever it rains.'

        Must represent:
        - intent = WATERLOGGING
        - department = DRAINAGE_STORMWATER
        - urgency = HIGH
        - location = None
        - missing_fields = ["location"]
        - ready_for_action = False
        """
        state = CanonicalCivicState(
            description="There is waterlogging outside my house whenever it rains.",
            intent=CivicIntent.WATERLOGGING,
            department=ControlledDepartment.DRAINAGE_STORMWATER,
            urgency=UrgencyLevel.HIGH,
            location=None,
            missing_fields=["location"],
            ready_for_action=False,
            followup_question="Could you please share your street name or nearby landmark?",
        )
        assert state.intent == CivicIntent.WATERLOGGING
        assert state.department == ControlledDepartment.DRAINAGE_STORMWATER
        assert state.urgency == UrgencyLevel.HIGH
        assert state.location is None
        assert state.missing_fields == ["location"]
        assert state.ready_for_action is False
        assert state.followup_question is not None

    def test_pincode_validation_rules(self):
        # Valid 6-digit Indian PIN code must be accepted as string
        state = CanonicalCivicState(pincode="600028")
        assert state.pincode == "600028"
        assert isinstance(state.pincode, str)

        # PIN code with leading 0 must be rejected
        with pytest.raises(ValidationError) as excinfo:
            CanonicalCivicState(pincode="012345")
        assert "Invalid PIN code" in str(excinfo.value)

        # PIN code with fewer than 6 digits must be rejected
        with pytest.raises(ValidationError):
            CanonicalCivicState(pincode="60002")

        # PIN code with non-numeric characters must be rejected
        with pytest.raises(ValidationError):
            CanonicalCivicState(pincode="60002A")

        # Non-string integer PIN code must be rejected
        with pytest.raises(ValidationError) as excinfo:
            CanonicalCivicState(pincode=600028)
        assert "Pincode must be provided as a string" in str(excinfo.value)

    def test_confidence_range_validation(self):
        # Valid confidence boundary values
        state_min = CanonicalCivicState(confidence=0.0)
        assert state_min.confidence == 0.0

        state_max = CanonicalCivicState(confidence=1.0)
        assert state_max.confidence == 1.0

        state_mid = CanonicalCivicState(confidence=0.75)
        assert state_mid.confidence == 0.75

        # Out of bounds (< 0.0)
        with pytest.raises(ValidationError):
            CanonicalCivicState(confidence=-0.1)

        # Out of bounds (> 1.0)
        with pytest.raises(ValidationError):
            CanonicalCivicState(confidence=1.01)

    def test_case_id_pattern_validation(self):
        # Valid case ID
        state = CanonicalCivicState(case_id="NS-BLR-2026-A8F2")
        assert state.case_id == "NS-BLR-2026-A8F2"

        # Invalid case ID format
        with pytest.raises(ValidationError) as excinfo:
            CanonicalCivicState(case_id="CASE-12345")
        assert "Invalid case_id" in str(excinfo.value)


class TestCommonUtilitiesAndRequests:
    """Validate Case ID generation, regex validation, and request/response models."""

    def test_generate_and_validate_case_id(self):
        case_id = generate_case_id(city_code="CHN", year=2026)
        assert validate_case_id(case_id) is True
        assert case_id.startswith("NS-CHN-2026-")
        assert len(case_id.split("-")[-1]) == 4

        # Custom city code (3 or 4 letters)
        case_id_blr = generate_case_id(city_code="BLR", year=2026)
        assert validate_case_id(case_id_blr) is True
        assert case_id_blr.startswith("NS-BLR-2026-")

    def test_validate_case_id_negative_cases(self):
        assert validate_case_id("invalid") is False
        assert validate_case_id("NS-C-2026-1234") is False
        assert validate_case_id("NS-CHN-26-1234") is False
        assert validate_case_id("NS-CHN-2026-123") is False
        assert validate_case_id(12345) is False

    def test_conversation_request_response_models(self):
        req = ConversationRequest(
            session_id="session-xyz",
            message="Streetlight is not working on 5th cross road",
            language="en",
        )
        assert req.session_id == "session-xyz"
        assert req.message == "Streetlight is not working on 5th cross road"

        state = CanonicalCivicState(
            intent=CivicIntent.STREETLIGHT_OUTAGE,
            department=ControlledDepartment.ELECTRICITY_UTILITY,
        )
        resp = ConversationResponse(session_id="session-xyz", state=state)
        assert resp.session_id == "session-xyz"
        assert resp.state.intent == CivicIntent.STREETLIGHT_OUTAGE
