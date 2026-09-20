"""Comprehensive Multilingual Extraction, Multi-turn Clarification, and Benchmark Tests.

Validates language independence, Indic script preservation, PIN code extraction,
follow-up location merging without question repetition, and refusal rejection.
"""

import pytest
from app.agents.coordinator import CivicAgentCoordinator, is_unrelated_or_refusal_followup
from app.agents.extraction_agent import CivicExtractionAgent
from app.agents.intent_agent import RequirementIntentAgent, detect_language
from app.llm.ollama_provider import OllamaProvider
from app.models.enums import CivicIntent, ControlledDepartment, LocationSource


@pytest.fixture
def offline_llm():
    return OllamaProvider(base_url="http://127.0.0.1:59999", timeout=0.1)


class TestMultilingualSection11Benchmarks:
    """Test all 9 language benchmarks from Section 11 of the requirement specification."""

    @pytest.mark.asyncio
    async def test_tamil_benchmark(self, offline_llm):
        msg = "குமரன் தெரு புதூர் அம்பத்தூர்"
        assert detect_language(msg) == "Tamil"
        extractor = CivicExtractionAgent(offline_llm)
        res = await extractor.run(msg)
        assert res.street == "குமரன் தெரு"
        assert res.area == "புதூர்"
        assert res.locality == "அம்பத்தூர்"
        assert "குமரன் தெரு" in res.location

    @pytest.mark.asyncio
    async def test_hindi_benchmark(self, offline_llm):
        msg = "गड्ढा है चांदनी चौक में"
        assert detect_language(msg) == "Hindi"
        intent_agent = RequirementIntentAgent(offline_llm)
        extractor = CivicExtractionAgent(offline_llm)
        intent_res = await intent_agent.run(msg)
        assert intent_res.intent == CivicIntent.ROAD_POTHOLE
        extract_res = await extractor.run(msg)
        assert extract_res.locality == "चांदनी चौक" or "चांदनी चौक" in (extract_res.location or "")

    @pytest.mark.asyncio
    async def test_telugu_benchmark(self, offline_llm):
        msg = "అంబత్తూరులో నీరు నిలిచిపోయింది"
        assert detect_language(msg) == "Telugu"
        intent_agent = RequirementIntentAgent(offline_llm)
        extractor = CivicExtractionAgent(offline_llm)
        intent_res = await intent_agent.run(msg)
        assert intent_res.intent == CivicIntent.WATERLOGGING
        extract_res = await extractor.run(msg)
        assert extract_res.locality == "అంబత్తూరు" or "అంబత్తూరు" in (extract_res.location or "")

    @pytest.mark.asyncio
    async def test_kannada_benchmark(self, offline_llm):
        msg = "ಬೆಂಗಳೂರು ರಸ್ತೆ ಗುಂಡಿ"
        assert detect_language(msg) == "Kannada"
        intent_agent = RequirementIntentAgent(offline_llm)
        extractor = CivicExtractionAgent(offline_llm)
        intent_res = await intent_agent.run(msg)
        assert intent_res.intent == CivicIntent.ROAD_POTHOLE
        extract_res = await extractor.run(msg)
        assert extract_res.locality == "ಬೆಂಗಳೂರು" or "ಬೆಂಗಳೂರು" in (extract_res.location or "")

    @pytest.mark.asyncio
    async def test_bengali_benchmark(self, offline_llm):
        msg = "চৌরাস্তার কাছে জল জমে আছে"
        assert detect_language(msg) == "Bengali"
        intent_agent = RequirementIntentAgent(offline_llm)
        extractor = CivicExtractionAgent(offline_llm)
        intent_res = await intent_agent.run(msg)
        assert intent_res.intent == CivicIntent.WATERLOGGING
        extract_res = await extractor.run(msg)
        assert extract_res.street == "চৌরাস্তা" or "চৌরাস্তা" in (extract_res.landmark or extract_res.location or "")

    @pytest.mark.asyncio
    async def test_marathi_benchmark(self, offline_llm):
        msg = "रस्त्यावर खड्डा आहे पुणे"
        assert detect_language(msg) == "Marathi"
        intent_agent = RequirementIntentAgent(offline_llm)
        extractor = CivicExtractionAgent(offline_llm)
        intent_res = await intent_agent.run(msg)
        assert intent_res.intent == CivicIntent.ROAD_POTHOLE
        extract_res = await extractor.run(msg)
        assert extract_res.locality == "पुणे" or "पुणे" in (extract_res.location or "")

    @pytest.mark.asyncio
    async def test_english_benchmark(self, offline_llm):
        msg = "Pothole near Anna Salai Chennai"
        assert detect_language(msg) == "English"
        intent_agent = RequirementIntentAgent(offline_llm)
        extractor = CivicExtractionAgent(offline_llm)
        intent_res = await intent_agent.run(msg)
        assert intent_res.intent == CivicIntent.ROAD_POTHOLE
        extract_res = await extractor.run(msg)
        assert "Anna Salai" in (extract_res.street or extract_res.location or "")
        assert extract_res.locality == "Chennai"

    @pytest.mark.asyncio
    async def test_hinglish_benchmark(self, offline_llm):
        msg = "Anna Salai ke paas road mein bahut potholes hain"
        assert detect_language(msg) in ["Hinglish", "Hindi"]
        intent_agent = RequirementIntentAgent(offline_llm)
        extractor = CivicExtractionAgent(offline_llm)
        intent_res = await intent_agent.run(msg)
        assert intent_res.intent == CivicIntent.ROAD_POTHOLE
        extract_res = await extractor.run(msg)
        assert "Anna Salai" in (extract_res.street or extract_res.landmark or extract_res.location or "")

    @pytest.mark.asyncio
    async def test_mixed_benchmark(self, offline_llm):
        msg = "அண்ணா சாலை near Guindy"
        extractor = CivicExtractionAgent(offline_llm)
        extract_res = await extractor.run(msg)
        assert extract_res.street == "அண்ணா சாலை"
        assert extract_res.locality == "Guindy"


class TestPincodeExtraction:
    """Test standard Indian 6-digit PIN code extraction across ASCII and Indic numerals."""

    @pytest.mark.asyncio
    async def test_standard_ascii_pincode(self, offline_llm):
        extractor = CivicExtractionAgent(offline_llm)
        res = await extractor.run("Pothole on Kumaran Street Pudur 600053 near bus stop")
        assert res.pincode == "600053"

    @pytest.mark.asyncio
    async def test_indic_tamil_numerals_pincode(self, offline_llm):
        extractor = CivicExtractionAgent(offline_llm)
        # ௬௦௦௦௫௩ = 600053
        res = await extractor.run("குமரன் தெரு புதூர் ௬௦௦௦௫௩")
        assert res.pincode == "600053"

    @pytest.mark.asyncio
    async def test_indic_devanagari_numerals_pincode(self, offline_llm):
        extractor = CivicExtractionAgent(offline_llm)
        # ११०२३४ = 110234
        res = await extractor.run("चांदनी चौक ११०२३४")
        assert res.pincode == "110234"

    @pytest.mark.asyncio
    async def test_invalid_arbitrary_numbers_not_pincode(self, offline_llm):
        extractor = CivicExtractionAgent(offline_llm)
        # 012345 has leading 0 (invalid Indian pincode)
        res = await extractor.run("Ref number 012345 near road")
        assert res.pincode != "012345"


class TestClarificationEngineAndFollowUp:
    """Test multi-turn context awareness, refusal rejection, and never asking redundant questions."""

    @pytest.mark.asyncio
    async def test_multi_turn_followup_success(self, offline_llm):
        coordinator = CivicAgentCoordinator(offline_llm)

        # Turn 1: Problem statement without location
        turn1 = await coordinator.execute_intake_turn(
            session_id="session-multiturn-1",
            message="தண்ணீர் தேங்கி நிற்கிறது",
        )
        assert turn1.intent == CivicIntent.WATERLOGGING
        assert "location" in (turn1.missing_fields or [])
        assert turn1.ready_for_action is False
        assert turn1.followup_question is not None

        # Turn 2: Location response in Tamil
        turn2 = await coordinator.execute_intake_turn(
            session_id="session-multiturn-1",
            message="குமரன் தெரு புதூர் அம்பத்தூர்",
            prev_state=turn1,
        )
        assert turn2.intent == CivicIntent.WATERLOGGING
        assert turn2.street == "குமரன் தெரு"
        assert turn2.area == "புதூர்"
        assert turn2.locality == "அம்பத்தூர்"
        assert "குமரன் தெரு, புதூர், அம்பத்தூர்" in (turn2.location or "")
        # Location MUST be satisfied and NOT re-asked
        assert "location" not in (turn2.missing_fields or [])
        assert turn2.ready_for_action is True
        assert turn2.followup_question is None

    @pytest.mark.asyncio
    async def test_refusal_is_rejected_as_location(self, offline_llm):
        coordinator = CivicAgentCoordinator(offline_llm)

        turn1 = await coordinator.execute_intake_turn(
            session_id="session-multiturn-2",
            message="There is a deep pothole",
        )
        assert "location" in (turn1.missing_fields or [])

        # Turn 2: Citizen replies "I don't know"
        turn2 = await coordinator.execute_intake_turn(
            session_id="session-multiturn-2",
            message="I don't know",
            prev_state=turn1,
        )
        # Must NOT accept "I don't know" as location
        assert turn2.location is None
        assert "location" in (turn2.missing_fields or [])
        assert turn2.ready_for_action is False

    @pytest.mark.asyncio
    async def test_tamil_refusal_is_rejected_as_location(self, offline_llm):
        coordinator = CivicAgentCoordinator(offline_llm)

        turn1 = await coordinator.execute_intake_turn(
            session_id="session-multiturn-3",
            message="தண்ணீர் தேங்கி நிற்கிறது",
        )
        assert "location" in (turn1.missing_fields or [])

        # Turn 2: Citizen replies "தெரியாது"
        turn2 = await coordinator.execute_intake_turn(
            session_id="session-multiturn-3",
            message="தெரியாது",
            prev_state=turn1,
        )
        assert turn2.location is None
        assert "location" in (turn2.missing_fields or [])
        assert turn2.ready_for_action is False

    @pytest.mark.asyncio
    async def test_input_with_location_never_asks_for_location(self, offline_llm):
        coordinator = CivicAgentCoordinator(offline_llm)

        # "அம்பத்தூரில் தண்ணீர் தேங்கி நிற்கிறது" has location "அம்பத்தூர்"
        res = await coordinator.execute_intake_turn(
            session_id="session-multiturn-4",
            message="அம்பத்தூரில் தண்ணீர் தேங்கி நிற்கிறது",
        )
        assert res.intent == CivicIntent.WATERLOGGING
        assert "location" not in (res.missing_fields or [])
        assert res.ready_for_action is True
        assert res.followup_question is None

    def test_refusal_detector_matrix(self):
        assert is_unrelated_or_refusal_followup("I don't know") is True
        assert is_unrelated_or_refusal_followup("I dont remember") is True
        assert is_unrelated_or_refusal_followup("hello") is True
        assert is_unrelated_or_refusal_followup("thank you") is True
        assert is_unrelated_or_refusal_followup("there is another problem") is True
        assert is_unrelated_or_refusal_followup("தெரியாது") is True
        assert is_unrelated_or_refusal_followup("ஞாபகம் இல்லை") is True
        assert is_unrelated_or_refusal_followup("வணக்கம்") is True
        assert is_unrelated_or_refusal_followup("नहीं पता") is True
        assert is_unrelated_or_refusal_followup("தெரியாதுங்க") is True

        # Valid location answers must NOT be detected as refusals
        assert is_unrelated_or_refusal_followup("குமரன் தெரு புதூர் அம்பத்தூர்") is False
        assert is_unrelated_or_refusal_followup("Near Shiva Temple") is False
        assert is_unrelated_or_refusal_followup("चांदनी चौक") is False
        assert is_unrelated_or_refusal_followup("Opposite bus stand") is False
