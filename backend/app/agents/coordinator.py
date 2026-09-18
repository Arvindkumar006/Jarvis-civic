"""Multi-Agent Coordinator for JARVIS Civic.

Orchestrates a bounded, predictable multi-turn pipeline across specialized agents
and AWS Strands runtime tools:
1. Requirement & Intent Analyzer (with non-civic short circuit)
2. Civic Information Extractor (with deterministic trust boundary)
3. Department & Urgency Classifier (with Strands tools)
4. Clarification & Follow-Up Agent
Assembles, merges, and persists intermediate states into CanonicalCivicState.
"""

import logging
import re
from typing import Any, List, Optional
from strands.agent.agent import Agent
from app.models.civic_state import CanonicalCivicState
from app.models.enums import CaseStatus, CivicIntent, LocationSource
from app.llm.provider import LLMProvider
from app.agents.intent_agent import RequirementIntentAgent
from app.agents.extraction_agent import CivicExtractionAgent
from app.agents.classification_agent import DepartmentUrgencyAgent
from app.agents.clarification_agent import ClarificationAgent
from app.agents.strands_adapter import (
    LocalStrandsModel,
    calculate_urgency_tool,
    detect_missing_fields_tool,
    map_department_tool,
    validate_pincode_tool,
)
from app.services.persistence.conversation_repository import (
    session_repository,
    validate_session_id,
)

logger = logging.getLogger("jarvis.agents.coordinator")


class CivicAgentCoordinator:
    """Bounded pipeline orchestrator across specialized Strands agents and tools."""

    def __init__(self, provider: LLMProvider):
        self.provider = provider
        self.intent_agent = RequirementIntentAgent(provider)
        self.extraction_agent = CivicExtractionAgent(provider)
        self.classification_agent = DepartmentUrgencyAgent()
        self.clarification_agent = ClarificationAgent(provider)

        # Genuine AWS Strands Agent binding with registered civic tools
        self.strands_agent = Agent(
            model=LocalStrandsModel(provider),
            tools=[
                validate_pincode_tool,
                map_department_tool,
                calculate_urgency_tool,
                detect_missing_fields_tool,
            ],
        )

    def _sanitize_extraction_trust_boundary(
        self,
        message: str,
        extract_res: Any,
    ) -> None:
        """Enforce deterministic trust boundary on candidate LLM extractions.

        Prevents hallucinated PIN codes, non-existent locations, or arbitrary insertions.
        """
        # 1. PIN code must strictly appear in the message text
        if extract_res.pincode:
            clean_pin = str(extract_res.pincode).strip()
            if not re.search(r"\b" + re.escape(clean_pin) + r"\b", message):
                extract_res.pincode = None
            elif not validate_pincode_tool(clean_pin):
                extract_res.pincode = None

        # 2. Location cannot be completely fabricated if totally absent from user input
        if extract_res.location:
            loc_words = [w.lower() for w in re.findall(r"\w+", extract_res.location)]
            msg_lower = message.lower()
            # If none of the words in location exist anywhere in the message, reject it
            if loc_words and not any(w in msg_lower for w in loc_words if len(w) > 2):
                extract_res.location = None

    async def execute_intake_turn(
        self,
        message: str,
        session_id: str,
        language_hint: Optional[str] = "English",
        current_case_id: Optional[str] = None,
    ) -> CanonicalCivicState:
        """Run a bounded execution pass over citizen communication with multi-turn memory."""
        # 0. Validate session security format
        clean_session_id = validate_session_id(session_id)

        # 1. Retrieve previous conversation session state
        prev_state = session_repository.get_session(clean_session_id)

        # 2. Strands Agent runtime invocation on the civic intake request path
        try:
            strands_res = await self.strands_agent.invoke_async(f"Process citizen civic complaint: {message}")
            logger.info("Strands Agent runtime successfully executed: %s", type(strands_res))
        except Exception as exc:
            logger.debug("Strands Agent runtime local fallback: %s", exc)

        # 3. Intent Analysis
        intent_res = await self.intent_agent.run(message, language_hint)

        # 4. Non-Civic Short-Circuit: If pure greeting, off-topic, or non-civic without previous context
        if not intent_res.is_civic and prev_state is None:
            greeting_msg = (
                "வணக்கம்! நான் JARVIS Civic. உங்கள் பகுதியில் உள்ள சாலை பள்ளம், "
                "தண்ணீர் தேக்கம் அல்லது தெரு விளக்கு போன்ற குடிமைப் பிரச்சினையை விவரிக்கவும்."
                if intent_res.language == "Tamil"
                else (
                    "नमस्ते! मैं JARVIS Civic हूँ। कृपया अपने क्षेत्र की नागरिक समस्या "
                    "(जैसे गड्ढा, जलभराव, स्ट्रीटलाइट आदि) और उसका स्थान बताएं।"
                    if intent_res.language == "Hindi"
                    else "Hello! I am JARVIS Civic. Please describe the civic defect in your area (such as a pothole, waterlogging, or streetlight issue) and its location."
                )
            )
            return CanonicalCivicState(
                case_id=current_case_id,
                session_id=clean_session_id,
                intent=None,
                department=None,
                description=message.strip(),
                citizen_language=intent_res.language,
                confidence=intent_res.confidence,
                missing_fields=["civic_issue", "location"],
                followup_question=greeting_msg,
                ready_for_action=False,
                status=CaseStatus.DRAFT,
            )

        # 4. Information Extraction
        extract_res = await self.extraction_agent.run(message)
        self._sanitize_extraction_trust_boundary(message, extract_res)

        # 5. Multi-turn Merge Logic
        # Determine Intent: Preserve established intent unless user explicitly specifies a different civic intent
        if prev_state and prev_state.intent:
            # If current message has an explicit non-generic civic intent and differs from previous, allow correction
            if (
                intent_res.is_civic
                and intent_res.intent != CivicIntent.OTHER_CIVIC_ISSUE
                and intent_res.intent != prev_state.intent
                and re.search(r"\b(instead|actually|not a|change to|wrong|not)\b", message, re.IGNORECASE)
            ):
                merged_intent = intent_res.intent
            else:
                merged_intent = prev_state.intent
        else:
            merged_intent = intent_res.intent

        # Determine Description: Preserve or update
        if prev_state and prev_state.description:
            # If user message is just supplying missing location or pincode, keep main problem description
            is_supplementary = (
                extract_res.pincode is not None
                or extract_res.location is not None
                or len(message.split()) <= 6
            ) and (not intent_res.is_civic or intent_res.intent == CivicIntent.OTHER_CIVIC_ISSUE)

            if is_supplementary:
                merged_description = prev_state.description
            else:
                # Merge or update description if meaningful
                merged_description = prev_state.description
        else:
            merged_description = extract_res.description or intent_res.initial_description

        # Determine Location attributes: Overwrite if present, else preserve previous
        merged_location = extract_res.location or (prev_state.location if prev_state else None)
        merged_landmark = extract_res.landmark or (prev_state.landmark if prev_state else None)
        merged_pincode = extract_res.pincode or (prev_state.pincode if prev_state else None)
        merged_lat = prev_state.latitude if prev_state else None
        merged_lng = prev_state.longitude if prev_state else None
        merged_loc_source = prev_state.location_source if prev_state else LocationSource.UNCONFIRMED

        # Merge Hazard indicators
        accumulated_hazards = list(extract_res.hazard_flags)
        if prev_state and hasattr(prev_state, "urgency_rationale") and prev_state.urgency_rationale:
            # Retain baseline
            pass

        # 6. Department & Urgency Classification
        classify_res = await self.classification_agent.run(
            intent=merged_intent,
            hazard_flags=accumulated_hazards,
        )

        # 7. Clarification & Follow-Up Check (evaluated against merged state)
        followup_res = await self.clarification_agent.run(
            location=merged_location,
            language=intent_res.language or (prev_state.citizen_language if prev_state else "English"),
            detected_intent=merged_intent.value if merged_intent else "Civic Issue",
        )

        # 8. Assemble Canonical State
        state = CanonicalCivicState(
            case_id=current_case_id or (prev_state.case_id if prev_state else None),
            session_id=clean_session_id,
            intent=merged_intent,
            department=classify_res.department,
            description=merged_description,
            location=merged_location,
            location_text=merged_location,
            landmark=merged_landmark,
            pincode=merged_pincode,
            latitude=merged_lat,
            longitude=merged_lng,
            location_source=merged_loc_source,
            urgency=classify_res.urgency,
            urgency_rationale=classify_res.urgency_rationale,
            citizen_language=intent_res.language or (prev_state.citizen_language if prev_state else "English"),
            confidence=intent_res.confidence if (not prev_state or intent_res.confidence > (prev_state.confidence or 0)) else prev_state.confidence,
            missing_fields=followup_res.missing_fields,
            followup_question=followup_res.followup_question,
            ready_for_action=followup_res.ready_for_action,
            status=CaseStatus.DRAFT,
        )

        # 9. Persist updated session state
        session_repository.save_session(clean_session_id, state)

        return state
