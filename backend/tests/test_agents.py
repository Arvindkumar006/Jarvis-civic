"""Tests for AWS Strands Agents, Tools, and Sub-agent Logic."""

import pytest
from app.llm.ollama_provider import OllamaProvider
from app.models.enums import CivicIntent, ControlledDepartment, UrgencyLevel
from app.agents.intent_agent import RequirementIntentAgent, detect_language
from app.agents.extraction_agent import CivicExtractionAgent
from app.agents.classification_agent import DepartmentUrgencyAgent
from app.agents.clarification_agent import ClarificationAgent
from app.agents.strands_adapter import (
    calculate_urgency_tool,
    detect_missing_fields_tool,
    map_department_tool,
    validate_pincode_tool,
)


@pytest.fixture
def offline_provider():
    return OllamaProvider(base_url="http://127.0.0.1:59999", timeout=0.2)


class TestStrandsCustomTools:
    """Validate registered Strands tools."""

    def test_validate_pincode_tool(self):
        assert validate_pincode_tool("600028") is True
        assert validate_pincode_tool("560038") is True
        assert validate_pincode_tool("012345") is False  # Leading 0 invalid
        assert validate_pincode_tool("60002") is False  # 5 digits invalid
        assert validate_pincode_tool("6000288") is False  # 7 digits invalid
        assert validate_pincode_tool("ABCDEF") is False

    def test_map_department_tool(self):
        assert map_department_tool(CivicIntent.WATERLOGGING.value) == ControlledDepartment.DRAINAGE_STORMWATER.value
        assert map_department_tool(CivicIntent.ROAD_POTHOLE.value) == ControlledDepartment.PWD_ROADS.value
        assert map_department_tool(CivicIntent.STREETLIGHT_OUTAGE.value) == ControlledDepartment.PWD_ROADS.value
        assert map_department_tool(CivicIntent.GARBAGE_ACCUMULATION.value) == ControlledDepartment.PWD_ROADS.value
        assert map_department_tool(CivicIntent.ELECTRICITY_OUTAGE.value) == ControlledDepartment.PWD_ROADS.value
        assert map_department_tool(CivicIntent.OTHER_CIVIC_ISSUE.value) == ControlledDepartment.PWD_ROADS.value

    def test_calculate_urgency_tool(self):
        # Baseline waterlogging
        res1 = calculate_urgency_tool(CivicIntent.WATERLOGGING.value, [])
        assert res1["urgency"] in [UrgencyLevel.MEDIUM.value, UrgencyLevel.HIGH.value]

        # Live wire hazard elevates to CRITICAL
        res2 = calculate_urgency_tool(CivicIntent.ELECTRICITY_OUTAGE.value, ["Live electrical wire hazard"])
        assert res2["urgency"] == UrgencyLevel.CRITICAL.value
        assert "Acute public safety hazard" in res2["rationale"]

    def test_detect_missing_fields_tool(self):
        assert detect_missing_fields_tool(None) == ["location"]
        assert detect_missing_fields_tool("") == ["location"]
        assert detect_missing_fields_tool("Anna Nagar 2nd Avenue") == []


class TestIntentAgent:
    """Validate Requirement & Intent Analyzer agent."""

    @pytest.mark.asyncio
    async def test_waterlogging_intent(self, offline_provider):
        agent = RequirementIntentAgent(offline_provider)
        res = await agent.run("There is severe waterlogging outside my house whenever it rains.")
        assert res.intent == CivicIntent.WATERLOGGING
        assert res.is_civic is True
        assert res.confidence >= 0.8

    @pytest.mark.asyncio
    async def test_pothole_intent(self, offline_provider):
        agent = RequirementIntentAgent(offline_provider)
        res = await agent.run("Dangerous deep pothole on the road causing bikes to slip.")
        assert res.intent == CivicIntent.ROAD_POTHOLE
        assert res.is_civic is True

    @pytest.mark.asyncio
    async def test_streetlight_intent(self, offline_provider):
        agent = RequirementIntentAgent(offline_provider)
        res = await agent.run("Streetlight not working for the past 3 days, complete darkness.")
        assert res.intent == CivicIntent.STREETLIGHT_OUTAGE

    @pytest.mark.asyncio
    async def test_non_civic_greeting(self, offline_provider):
        agent = RequirementIntentAgent(offline_provider)
        res = await agent.run("Hello, good morning!")
        assert res.is_civic is False
        assert res.intent == CivicIntent.OTHER_CIVIC_ISSUE

    def test_language_detection(self):
        assert detect_language("Water logging on street") == "English"
        assert detect_language("ரோட்டில் தண்ணீர் தேங்கி நிற்கிறது") == "Tamil"
        assert detect_language("सड़क पर बहुत सारा पानी भर गया है") == "Hindi"
        assert detect_language("Yeh pani kahan se aa raha hai sadak par") == "Hinglish"


class TestExtractionAgent:
    """Validate Civic Information Extractor anti-hallucination and regex extraction."""

    @pytest.mark.asyncio
    async def test_missing_location_evaluates_to_none(self, offline_provider):
        agent = CivicExtractionAgent(offline_provider)
        res = await agent.run("There is waterlogging outside my house whenever it rains.")
        assert res.location is None
        assert res.pincode is None

    @pytest.mark.asyncio
    async def test_location_and_pincode_extraction(self, offline_provider):
        agent = CivicExtractionAgent(offline_provider)
        msg = "There is waterlogging at 3rd Main Road, Anna Nagar, Chennai 600028 near Shiva Temple."
        res = await agent.run(msg)
        assert res.location is not None
        assert "Anna Nagar" in res.location or "Road" in res.location
        assert res.pincode == "600028"
        assert isinstance(res.pincode, str)
        assert res.landmark is not None
        assert "Shiva Temple" in res.landmark

    @pytest.mark.asyncio
    async def test_hazard_flag_extraction(self, offline_provider):
        agent = CivicExtractionAgent(offline_provider)
        msg = "Road broken with open manhole and live wire sparking."
        res = await agent.run(msg)
        assert len(res.hazard_flags) >= 2
        assert any("wire" in h.lower() for h in res.hazard_flags)
        assert any("manhole" in h.lower() for h in res.hazard_flags)


class TestClarificationAgent:
    """Validate follow-up question synthesis."""

    @pytest.mark.asyncio
    async def test_clarification_for_missing_location(self, offline_provider):
        agent = ClarificationAgent(offline_provider)
        res = await agent.run(location=None, language="English", detected_intent="WATERLOGGING")
        assert res.ready_for_action is False
        assert res.missing_fields == ["location"]
        assert res.followup_question is not None
        assert "street" in res.followup_question.lower() or "where" in res.followup_question.lower()

    @pytest.mark.asyncio
    async def test_clarification_tamil_language(self, offline_provider):
        agent = ClarificationAgent(offline_provider)
        res = await agent.run(location=None, language="Tamil", detected_intent="WATERLOGGING")
        assert res.ready_for_action is False
        assert "எங்கு" in res.followup_question or "தெரு" in res.followup_question

    @pytest.mark.asyncio
    async def test_clarification_ready_when_location_present(self, offline_provider):
        agent = ClarificationAgent(offline_provider)
        res = await agent.run(location="100 Feet Road, Indiranagar", language="English")
        assert res.ready_for_action is True
        assert res.missing_fields == []
        assert res.followup_question is None
