"""Citizen Conversation Intake API Route for JARVIS Civic."""

import logging
from fastapi import APIRouter, HTTPException, status
from app.models.common import ConversationRequest, ConversationResponse
from app.services.civic_reasoning import process_civic_message

logger = logging.getLogger("jarvis.api.conversation")

router = APIRouter(prefix="/api", tags=["Citizen Conversation"])


@router.post("/conversation", response_model=ConversationResponse, status_code=status.HTTP_200_OK)
async def intake_conversation(request: ConversationRequest) -> ConversationResponse:
    """Intake citizen message, run multi-agent reasoning loop, and return structured state."""
    try:
        updated_state = await process_civic_message(
            message=request.message,
            session_id=request.session_id,
            language=request.language,
        )
        return ConversationResponse(
            session_id=request.session_id,
            state=updated_state,
        )
    except ValueError as ve:
        logger.warning("Civic intake validation failure: %s", ve)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(ve),
        )
    except Exception as exc:
        logger.error("Internal error during civic intake reasoning: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An internal error occurred during civic intake reasoning. Please retry.",
        )
