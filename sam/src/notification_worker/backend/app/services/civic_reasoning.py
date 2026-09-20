"""Civic Reasoning Application Service for JARVIS Civic.

Exposes high-level orchestration across the multi-agent pipeline for API routes.
"""

from typing import Optional
from app.models.civic_state import CanonicalCivicState
from app.llm.ollama_provider import OllamaProvider
from app.agents.coordinator import CivicAgentCoordinator

# Default singleton provider & coordinator (thread-safe, stateless)
_provider = OllamaProvider()
_coordinator = CivicAgentCoordinator(_provider)


def get_coordinator() -> CivicAgentCoordinator:
    """Return the singleton CivicAgentCoordinator instance."""
    return _coordinator


async def process_civic_message(
    message: str,
    session_id: str,
    language: Optional[str] = "en",
    current_case_id: Optional[str] = None,
    previous_state: Optional[CanonicalCivicState] = None,
) -> CanonicalCivicState:
    """Entry point for processing a citizen conversation turn.

    Executes:
    1. Intent & Requirement Analysis
    2. Civic Information Extraction
    3. Recommended Department & Objective Urgency Classification
    4. Clarification Check & Vernacular Follow-Up Generation
    5. Returns populated CanonicalCivicState.
    """
    clean_message = message.strip()
    if not clean_message:
        raise ValueError("Citizen message cannot be empty.")

    state = await _coordinator.execute_intake_turn(
        message=clean_message,
        session_id=session_id,
        language_hint=language or "English",
        current_case_id=current_case_id,
        client_prev_state=previous_state,
    )
    return state

