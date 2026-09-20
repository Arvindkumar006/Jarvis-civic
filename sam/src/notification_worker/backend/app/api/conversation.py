import logging
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from app.config.settings import settings
from app.models.common import ConversationRequest, ConversationResponse
from app.models.evidence_relevance import CitizenEvidenceAssessment
from app.models.security import ApplicationPrincipal
from app.security.principals import get_current_principal
from app.services.civic_reasoning import process_civic_message
from app.services.evidence.validation import validate_evidence_file_deterministic
from app.services.evidence.vision_service import citizen_evidence_vision_service

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
            previous_state=request.previous_state,
        )
        return ConversationResponse(
            session_id=request.session_id,
            state=updated_state,
            reply=updated_state.followup_question,
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


@router.post("/conversation/evidence/relevance", response_model=CitizenEvidenceAssessment, status_code=status.HTTP_200_OK)
async def assess_conversation_evidence_relevance(
    query: str = Form(..., description="Citizen civic query / problem statement"),
    image: UploadFile = File(..., description="Citizen attached image file"),
    principal: ApplicationPrincipal = Depends(get_current_principal),
) -> CitizenEvidenceAssessment:
    """Assess visual relevance of an attached image against a citizen's reported issue.

    Advisory only: does NOT modify lifecycle, delete grievance, or alter department routing.
    Reuses existing deterministic validation (MIME, size, magic bytes, integrity).
    """
    clean_query = query.strip()
    if not clean_query:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Citizen query cannot be empty when assessing evidence relevance.",
        )

    # 1. Read file with size boundary check
    max_bytes = settings.MAX_EVIDENCE_SIZE_BYTES
    chunk_size = 1024 * 1024
    chunks = []
    total_read = 0

    while True:
        chunk = await image.read(chunk_size)
        if not chunk:
            break
        total_read += len(chunk)
        if total_read > max_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail=f"Evidence file size exceeds maximum limit of {max_bytes // (1024 * 1024)} MB",
            )
        chunks.append(chunk)

    file_bytes = b"".join(chunks)
    filename = image.filename or "evidence_attachment.jpg"
    declared_content_type = image.content_type or "image/jpeg"

    # 2. Reuse authoritative deterministic evidence validation (Rule 4 & 14)
    validation_result = validate_evidence_file_deterministic(
        file_bytes=file_bytes,
        filename=filename,
        declared_content_type=declared_content_type,
    )

    if not validation_result.is_valid:
        if validation_result.status.value == "FILE_TOO_LARGE":
            err_code = status.HTTP_413_CONTENT_TOO_LARGE
        else:
            err_code = status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=err_code, detail=validation_result.error_message)

    # 3. Modality check: Must be image
    if not validation_result.detected_content_type.startswith("image/"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Evidence relevance assessment requires an image artifact (got {validation_result.detected_content_type}).",
        )

    # 4. Invoke Vision AI assessment
    return citizen_evidence_vision_service.assess_relevance(
        query=clean_query,
        file_bytes=file_bytes,
        filename=validation_result.sanitized_filename,
        content_type=validation_result.detected_content_type,
    )

