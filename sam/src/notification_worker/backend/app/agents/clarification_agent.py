"""Agent 4: Clarification & Follow-Up Agent.

Checks missing mandatory intake attributes (location is required).
Generates a targeted, polite follow-up question in the citizen's detected language.
"""

from typing import List, Optional
from app.models.reasoning import FollowUpResult
from app.agents.prompts import FOLLOWUP_TEMPLATES
from app.agents.strands_adapter import detect_missing_fields_tool
from app.llm.provider import LLMProvider, LLMStatus


class ClarificationAgent:
    """Agent 4: Clarification & Follow-Up Agent."""

    def __init__(self, provider: LLMProvider):
        self.provider = provider

    def compose_followup_deterministic(
        self,
        missing_fields: List[str],
        language: str,
    ) -> Optional[str]:
        """Compose follow-up question using localized dialect templates."""
        if not missing_fields:
            return None

        # Resolve language key or default to English
        lang_key = language if language in FOLLOWUP_TEMPLATES else "English"
        templates = FOLLOWUP_TEMPLATES[lang_key]

        if "location" in missing_fields:
            return templates.get("location", templates["generic"])
        elif "pincode" in missing_fields:
            return templates.get("pincode", templates["generic"])
        return templates.get("generic")

    async def run(
        self,
        location: Optional[str],
        language: str = "English",
        detected_intent: Optional[str] = None,
    ) -> FollowUpResult:
        """Evaluate intake completeness and compose single clarification question if needed."""
        missing = detect_missing_fields_tool(location)
        ready_for_action = len(missing) == 0

        if ready_for_action:
            return FollowUpResult(
                missing_fields=[],
                followup_question=None,
                ready_for_action=True,
            )

        # Check if local LLM can provide contextual question
        status = await self.provider.check_health()
        if status == LLMStatus.LLM_AVAILABLE:
            prompt = (
                f"Missing fields: {missing}\n"
                f"Citizen language: {language}\n"
                f"Detected intent: {detected_intent or 'General Civic Problem'}\n"
                f"Write EXACTLY ONE polite, short sentence asking the citizen for the missing location."
            )
            llm_question = await self.provider.generate_text(prompt=prompt)
            if llm_question and len(llm_question) > 10:
                return FollowUpResult(
                    missing_fields=missing,
                    followup_question=llm_question.strip().strip('"'),
                    ready_for_action=False,
                )

        # Deterministic vernacular template fallback
        question = self.compose_followup_deterministic(missing, language)
        return FollowUpResult(
            missing_fields=missing,
            followup_question=question,
            ready_for_action=False,
        )
