"""Multi-Agent Coordinator for JARVIS Civic.

Orchestrates a bounded, predictable single-pass pipeline across the 4 specialized agents:
1. Intent & Requirement Analyzer
2. Civic Information Extractor
3. Department & Urgency Classifier
4. Clarification & Follow-Up Agent
Assembles intermediate results into CanonicalCivicState.
"""

from typing import Optional
from app.models.civic_state import CanonicalCivicState
from app.models.enums import CaseStatus
from app.llm.provider import LLMProvider
from app.agents.intent_agent import RequirementIntentAgent
from app.agents.extraction_agent import CivicExtractionAgent
from app.agents.classification_agent import DepartmentUrgencyAgent
from app.agents.clarification_agent import ClarificationAgent


class CivicAgentCoordinator:
    """Bounded pipeline orchestrator across the 4 specialized Strands agents."""

    def __init__(self, provider: LLMProvider):
        self.provider = provider
        self.intent_agent = RequirementIntentAgent(provider)
        self.extraction_agent = CivicExtractionAgent(provider)
        self.classification_agent = DepartmentUrgencyAgent()
        self.clarification_agent = ClarificationAgent(provider)

    async def execute_intake_turn(
        self,
        message: str,
        session_id: str,
        language_hint: Optional[str] = "English",
        current_case_id: Optional[str] = None,
    ) -> CanonicalCivicState:
        """Run a single bounded execution pass over citizen communication."""
        # 1. Intent Analysis
        intent_res = await self.intent_agent.run(message, language_hint)

        # 2. Information Extraction
        extract_res = await self.extraction_agent.run(message)

        # 3. Department & Urgency Classification
        classify_res = await self.classification_agent.run(
            intent=intent_res.intent,
            hazard_flags=extract_res.hazard_flags,
        )

        # 4. Clarification & Follow-Up Check
        followup_res = await self.clarification_agent.run(
            location=extract_res.location,
            language=intent_res.language,
            detected_intent=intent_res.intent.value,
        )

        # 5. Assemble Canonical State
        state = CanonicalCivicState(
            case_id=current_case_id,
            session_id=session_id,
            intent=intent_res.intent,
            department=classify_res.department,
            description=extract_res.description or intent_res.initial_description,
            location=extract_res.location,
            landmark=extract_res.landmark,
            pincode=extract_res.pincode,
            urgency=classify_res.urgency,
            urgency_rationale=classify_res.urgency_rationale,
            citizen_language=intent_res.language,
            confidence=intent_res.confidence,
            missing_fields=followup_res.missing_fields,
            followup_question=followup_res.followup_question,
            ready_for_action=followup_res.ready_for_action,
            status=CaseStatus.DRAFT,
        )

        return state
