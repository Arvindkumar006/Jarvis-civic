"""End-to-End Tests for Civic Reasoning Pipeline and Conversation API."""

import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.models.enums import CivicIntent, ControlledDepartment, UrgencyLevel
from app.services.civic_reasoning import process_civic_message

client = TestClient(app)


@pytest.mark.asyncio
async def test_end_to_end_incomplete_complaint_pipeline():
    """Verify incomplete complaint:

    'There is waterlogging outside my house whenever it rains.'
    Must yield:
    - intent: WATERLOGGING
    - department: DRAINAGE_STORMWATER
    - location: None
    - missing_fields: ['location']
    - ready_for_action: False
    - followup_question: asks for location in citizen language
    """
    state = await process_civic_message(
        message="There is waterlogging outside my house whenever it rains.",
        session_id="test-session-101",
        language="English",
    )
    assert state.session_id == "test-session-101"
    assert state.intent == CivicIntent.WATERLOGGING
    assert state.department == ControlledDepartment.DRAINAGE_STORMWATER
    assert state.location is None
    assert state.missing_fields == ["location"]
    assert state.ready_for_action is False
    assert state.followup_question is not None
    assert "location" in state.followup_question.lower() or "street" in state.followup_question.lower()


@pytest.mark.asyncio
async def test_end_to_end_complete_complaint_pipeline():
    """Verify complete complaint with location and PIN code:

    - intent: ROAD_POTHOLE
    - department: PWD_ROADS
    - pincode: string '560038'
    - ready_for_action: True
    - missing_fields: []
    - followup_question: None
    """
    msg = "Deep dangerous pothole at 100 Feet Road, Indiranagar near Metro Pillar 560038"
    state = await process_civic_message(
        message=msg,
        session_id="test-session-102",
        language="English",
    )
    assert state.intent == CivicIntent.ROAD_POTHOLE
    assert state.department == ControlledDepartment.PWD_ROADS
    assert state.location is not None
    assert state.pincode == "560038"
    assert isinstance(state.pincode, str)
    assert state.ready_for_action is True
    assert state.missing_fields == []
    assert state.followup_question is None


@pytest.mark.asyncio
async def test_multilingual_input_preserves_canonical_schema():
    """Verify regional Tamil input produces canonical English schema without errors."""
    msg = "ரோட்டில் தண்ணீர் தேங்கி நிற்கிறது"  # "Water is stagnant on the road"
    state = await process_civic_message(
        message=msg,
        session_id="test-session-tamil",
    )
    assert state.citizen_language == "Tamil"
    assert state.intent == CivicIntent.WATERLOGGING
    assert state.department == ControlledDepartment.DRAINAGE_STORMWATER
    assert state.ready_for_action is False
    assert state.missing_fields == ["location"]
    assert state.followup_question is not None
    # Follow-up question is presented in Tamil
    assert "எங்கு" in state.followup_question or "தெரு" in state.followup_question


def test_conversation_api_endpoint():
    """Test POST /api/conversation returns valid ConversationResponse."""
    payload = {
        "session_id": "api-session-789",
        "message": "Streetlight is not working on 5th Main Road",
        "language": "en",
    }
    response = client.post("/api/conversation", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["session_id"] == "api-session-789"
    assert "state" in data
    state_data = data["state"]
    assert state_data["intent"] == "STREETLIGHT_OUTAGE"
    assert state_data["department"] == "PWD_ROADS"
    assert state_data["location"] is not None
    assert state_data["ready_for_action"] is True


def test_conversation_api_empty_message_rejected():
    """Test POST /api/conversation rejects empty payload with 422."""
    payload = {
        "session_id": "api-session-empty",
        "message": "   ",
        "language": "en",
    }
    response = client.post("/api/conversation", json=payload)
    assert response.status_code == 422
