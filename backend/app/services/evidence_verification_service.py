"""Authoritative Evidence Verification Service for JARVIS Civic.

Phase 8.7: Centralized backend orchestration service combining Cedar authorization,
deterministic file validation (magic bytes, MIME, SHA-256), secure persistence,
advisory AI assessment, append-only audit logging, and notification dispatch.
"""

from datetime import datetime, timezone
import logging
import secrets
from typing import List, Optional

from fastapi import HTTPException, status

from app.config.settings import settings
from app.models.evidence import (
    DeterministicValidationResult,
    DeterministicValidationStatus,
    EvidenceRecord,
    EvidenceResponse,
    EvidenceType,
    EvidenceVerificationRecord,
    VerificationOutcome,
)
from app.models.security import (
    ApplicationPrincipal,
    CivicAction,
    CivicCaseRecord,
    EvidenceMetadata,
)
from app.security.audit import audit_dispatcher
from app.security.pep import pep
from app.services.evidence.provider import (
    DeterministicFallbackProvider,
    EvidenceAssessmentProvider,
    OllamaEvidenceAssessmentProvider,
)
from app.services.evidence.repository import evidence_repo
from app.services.evidence.validation import validate_evidence_file_deterministic
from app.services.notifications.worker_dispatcher import worker_dispatcher
from app.services.case_store import case_store

logger = logging.getLogger("jarvis.evidence.service")


class EvidenceVerificationService:
    """Authoritative backend orchestration point for civic evidence verification."""

    def __init__(self, provider: Optional[EvidenceAssessmentProvider] = None):
        if provider is not None:
            self.provider = provider
        else:
            # By default, use local Ollama provider if enabled in settings, otherwise deterministic fallback
            self.provider = OllamaEvidenceAssessmentProvider()

    def set_provider(self, provider: EvidenceAssessmentProvider) -> None:
        """Swap assessment provider (e.g. for testing isolated AI outcomes)."""
        self.provider = provider

    def verify_and_store_evidence(
        self,
        case_id: str,
        principal: ApplicationPrincipal,
        file_bytes: bytes,
        filename: str,
        content_type: str,
        evidence_type: EvidenceType = EvidenceType.CASE_EVIDENCE,
        resolution_attempt: Optional[str] = None,
        resolution_message: Optional[str] = None,
    ) -> EvidenceResponse:
        """Execute complete evidence verification and persistence pipeline.

        Pipeline:
        1. Resolve case record
        2. Cedar authorization (Action: add_evidence vs add_resolution_evidence)
        3. Deterministic file validation (pre-persistence, rejects malformed/mismatched files)
        4. Cryptographic SHA-256 computation
        5. Secure S3/Local persistence
        6. Advisory AI assessment
        7. Trusted server-side record creation
        8. Audit logging
        9. Notification dispatch
        10. Sanitized response projection
        """
        # 1. Resolve case
        case = case_store.get_case(case_id)
        if not case:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Case '{case_id}' not found")

        # 2. Cedar Authorization
        # Select action based on evidence type
        if evidence_type == EvidenceType.RESOLUTION_EVIDENCE:
            action = CivicAction.ADD_RESOLUTION_EVIDENCE
        else:
            action = CivicAction.ADD_EVIDENCE

        # Enforce Cedar PEP (halts with HTTP 403 if unauthorized)
        pep.enforce(
            principal=principal,
            action=action,
            resource_id=case.case_id,
            resource_type="CivicCase",
            resource_owner=case.owner_id,
            resource_department=case.department,
            resource_status=case.status.value,
            is_public=case.is_public,
        )

        # 3. Deterministic Validation BEFORE persistence
        validation_result: DeterministicValidationResult = validate_evidence_file_deterministic(
            file_bytes=file_bytes,
            filename=filename,
            declared_content_type=content_type,
        )

        if not validation_result.is_valid:
            # Audit rejected evidence attempt
            audit_dispatcher.record_workflow_event(
                case_id=case_id,
                event_type="EVIDENCE_VALIDATION_REJECTED",
                previous_status=case.status.value,
                new_status=case.status.value,
                principal=principal,
                outcome="FAILURE",
                metadata={
                    "status": validation_result.status.value,
                    "error": validation_result.error_message,
                    "filename": validation_result.sanitized_filename,
                    "size_bytes": validation_result.size_bytes,
                },
            )

            # Map validation failure to appropriate HTTP status code
            if validation_result.status == DeterministicValidationStatus.FILE_TOO_LARGE:
                err_code = status.HTTP_413_CONTENT_TOO_LARGE
            else:
                err_code = status.HTTP_400_BAD_REQUEST

            raise HTTPException(status_code=err_code, detail=validation_result.error_message)

        # 4. Generate server-side identifiers
        evidence_id = f"ev-{secrets.token_hex(6)}"
        verification_id = f"ver-{secrets.token_hex(6)}"
        now = datetime.now(timezone.utc)

        # 5. Secure Persistence in Evidence Storage
        clean_filename = validation_result.sanitized_filename
        storage_meta: EvidenceMetadata = case_store.evidence_repo.upload_evidence(
            case_id=case_id,
            file_bytes=file_bytes,
            filename=clean_filename,
            content_type=validation_result.detected_content_type,
        )
        case_store.add_evidence_uri(case_id, storage_meta.s3_uri)

        # 6. Advisory AI Assessment — non-blocking background thread.
        # Evidence stores immediately with UNCERTAIN; AI updates the record when done.
        # This prevents CPU-bound vision inference from blocking the HTTP response.
        import threading

        _is_image = (
            validation_result.detected_content_type.startswith("image/")
            or clean_filename.lower().endswith((".jpg", ".jpeg", ".png", ".webp"))
        )

        # 7. Persist Structured Verification Record immediately with UNCERTAIN placeholder
        ver_record = EvidenceVerificationRecord(
            verification_id=verification_id,
            evidence_id=evidence_id,
            case_id=case_id,
            deterministic_validation_result=validation_result.status,
            verification_status=VerificationOutcome.UNCERTAIN,
            verification_reason="AI assessment in progress; deterministic validation passed.",
            assessment_provider="pending",
            assessment_model=None,
            assessment_timestamp=now,
            ai_available=False,
            ai_confidence=None,
            detected_characteristics=["deterministic_validation_passed"],
            relevance=None,
            relevance_reason=None,
            relevance_detected_features=[],
            relevance_confidence=None,
            created_at=now,
        )
        evidence_repo.save_verification(ver_record)

        # Background AI thread — captures locals by value
        _provider = self.provider
        _case_desc = case.description
        _department = case.department
        _detected_ct = validation_result.detected_content_type

        def _run_ai_assessment() -> None:
            try:
                assessment = _provider.assess(
                    case_id=case_id,
                    case_description=_case_desc,
                    department=_department,
                    evidence_type=evidence_type,
                    filename=clean_filename,
                    content_type=_detected_ct,
                    file_bytes=file_bytes,
                    resolution_attempt=resolution_attempt,
                )
                rel_assessment = None
                if evidence_type == EvidenceType.CASE_EVIDENCE and _is_image:
                    from app.services.evidence.provider import (
                        DeterministicFallbackProvider,
                        MockEvidenceAssessmentProvider,
                    )
                    from app.models.evidence_relevance import (
                        CitizenEvidenceAssessment,
                        EvidenceRelevanceOutcome,
                    )
                    from app.services.evidence.vision_service import citizen_evidence_vision_service
                    if citizen_evidence_vision_service._custom_caller is not None:
                        rel_assessment = citizen_evidence_vision_service.assess_relevance(
                            query=_case_desc or "",
                            file_bytes=file_bytes,
                            filename=clean_filename,
                            content_type=_detected_ct,
                        )
                    elif isinstance(_provider, MockEvidenceAssessmentProvider):
                        rel_assessment = CitizenEvidenceAssessment(
                            relevance=(
                                EvidenceRelevanceOutcome.RELATED
                                if assessment.outcome in (VerificationOutcome.VERIFIED, VerificationOutcome.LIKELY_VERIFIED)
                                else EvidenceRelevanceOutcome.UNCERTAIN
                            ),
                            confidence=assessment.confidence or 0.95,
                            reason=assessment.reason,
                            detected_features=assessment.detected_characteristics,
                            model_id="mock-vision",
                            timestamp=assessment.timestamp,
                        )
                    elif isinstance(_provider, DeterministicFallbackProvider):
                        rel_assessment = CitizenEvidenceAssessment(
                            relevance=EvidenceRelevanceOutcome.UNCERTAIN,
                            confidence=None,
                            reason=assessment.reason,
                            detected_features=assessment.detected_characteristics,
                            model_id="deterministic-fallback",
                            timestamp=assessment.timestamp,
                        )
                    else:
                        rel_assessment = citizen_evidence_vision_service.assess_relevance(
                            query=_case_desc or "",
                            file_bytes=file_bytes,
                            filename=clean_filename,
                            content_type=_detected_ct,
                        )
                ver_record.verification_status = assessment.outcome
                ver_record.verification_reason = assessment.reason
                ver_record.assessment_provider = assessment.provider_id
                ver_record.assessment_model = assessment.model_id
                ver_record.assessment_timestamp = assessment.timestamp
                ver_record.ai_available = assessment.ai_available
                ver_record.ai_confidence = assessment.confidence
                ver_record.detected_characteristics = assessment.detected_characteristics
                if rel_assessment:
                    ver_record.relevance = rel_assessment.relevance
                    ver_record.relevance_reason = rel_assessment.reason
                    ver_record.relevance_detected_features = rel_assessment.detected_features
                    ver_record.relevance_confidence = rel_assessment.confidence
                evidence_repo.save_verification(ver_record)

                # Update persisted EvidenceRecord
                saved_rec = evidence_repo.get_evidence(case_id, evidence_id)
                if saved_rec:
                    saved_rec.verification_status = assessment.outcome
                    saved_rec.verification_reason = assessment.reason
                    saved_rec.ai_confidence = assessment.confidence
                    if rel_assessment:
                        saved_rec.relevance = rel_assessment.relevance
                        saved_rec.relevance_reason = rel_assessment.reason
                        saved_rec.relevance_detected_features = rel_assessment.detected_features
                        saved_rec.relevance_confidence = rel_assessment.confidence
                    evidence_repo.save_evidence(saved_rec)

                logger.info(
                    "Background AI assessment complete for evidence %s: %s",
                    evidence_id, assessment.outcome.value,
                )
            except Exception as exc:
                logger.warning("Background AI assessment failed for evidence %s: %s", evidence_id, exc)

        ai_thread = threading.Thread(target=_run_ai_assessment, daemon=True)
        ai_thread.start()
        # Allow fast/mock providers to complete within 0.2s without blocking user experience for slow models
        ai_thread.join(timeout=0.2)

        # 8. Persist Authoritative Evidence Record
        # Server derives uploader metadata from AuthenticatedPrincipal
        submitting_officer = principal.principal_id if evidence_type == EvidenceType.RESOLUTION_EVIDENCE else None
        officer_dept = principal.department if evidence_type == EvidenceType.RESOLUTION_EVIDENCE else None
        attempt_ref = resolution_attempt or f"attempt-{case.rejection_count + 1}" if evidence_type == EvidenceType.RESOLUTION_EVIDENCE else None
        clean_msg = resolution_message.strip() if resolution_message and resolution_message.strip() else None

        if evidence_type == EvidenceType.RESOLUTION_EVIDENCE and attempt_ref:
            case_store.set_active_resolution_attempt(
                case_id=case_id,
                attempt_id=attempt_ref,
                resolution_message=clean_msg,
            )
            if clean_msg:
                case_store.add_resolution_note(
                    case_id=case_id,
                    note=clean_msg,
                    actor_label=principal.role.value,
                )

        rec = EvidenceRecord(
            evidence_id=evidence_id,
            case_id=case_id,
            uploaded_by_principal=principal.principal_id,
            uploader_role=principal.role.value,
            evidence_type=evidence_type,
            filename=clean_filename,
            content_type=validation_result.detected_content_type,
            size_bytes=validation_result.size_bytes,
            storage_key=storage_meta.object_key,
            s3_uri=storage_meta.s3_uri,
            sha256=validation_result.sha256,
            validation_status=validation_result.status,
            verification_status=ver_record.verification_status,
            verification_reason=ver_record.verification_reason,
            ai_assessment=None,  # populated by background AI thread if still running
            ai_confidence=ver_record.ai_confidence,
            relevance=ver_record.relevance,
            relevance_reason=ver_record.relevance_reason,
            relevance_detected_features=ver_record.relevance_detected_features or [],
            relevance_confidence=ver_record.relevance_confidence,
            resolution_attempt=attempt_ref,
            resolution_message=clean_msg,
            submitting_authority_principal=submitting_officer,
            authority_department=officer_dept,
            created_at=now,
            verified_at=now,
        )
        evidence_repo.save_evidence(rec)

        # 9. Audit Logging via existing audit infrastructure
        event_name = (
            "RESOLUTION_EVIDENCE_ATTACHED"
            if evidence_type == EvidenceType.RESOLUTION_EVIDENCE
            else "EVIDENCE_ATTACHED"
        )
        audit_dispatcher.record_workflow_event(
            case_id=case_id,
            event_type=event_name,
            previous_status=case.status.value,
            new_status=case.status.value,
            principal=principal,
            outcome="SUCCESS",
            metadata={
                "evidence_id": evidence_id,
                "evidence_type": evidence_type.value,
                "sha256": validation_result.sha256,
                "validation_status": validation_result.status.value,
                "verification_status": ver_record.verification_status.value,
                "ai_available": False,
                "ai_confidence": None,
                "resolution_attempt": attempt_ref,
                "resolution_message": clean_msg,
                "is_advisory": True,
            },
        )

        # 10. Notification Integration
        try:
            if evidence_type == EvidenceType.RESOLUTION_EVIDENCE:
                # Notify citizen case owner that authority has uploaded resolution evidence
                worker_dispatcher.dispatch_resolution_ready(
                    case, proposed_notes=clean_msg or f"Resolution evidence '{clean_filename}' attached by {principal.principal_id}"
                )
            else:
                # Ordinary case evidence uploaded -> notify authority
                worker_dispatcher.dispatch_evidence_uploaded(case, storage_meta)
        except Exception as notif_err:
            logger.critical("Notification dispatch exception for evidence %s: %s", evidence_id, notif_err)

        # 11. Return sanitized response projection
        return EvidenceResponse(
            evidence_id=rec.evidence_id,
            case_id=rec.case_id,
            evidence_type=rec.evidence_type,
            filename=rec.filename,
            content_type=rec.content_type,
            size_bytes=rec.size_bytes,
            sha256=rec.sha256,
            validation_status=rec.validation_status,
            verification_status=rec.verification_status,
            verification_reason=rec.verification_reason,
            ai_confidence=rec.ai_confidence,
            relevance=rec.relevance,
            relevance_reason=rec.relevance_reason,
            relevance_detected_features=rec.relevance_detected_features,
            relevance_confidence=rec.relevance_confidence,
            resolution_attempt=rec.resolution_attempt,
            resolution_message=rec.resolution_message,
            object_key=rec.storage_key,
            s3_uri=rec.s3_uri,
            created_at=rec.created_at,
            verified_at=rec.verified_at,
        )

    def list_case_evidence(
        self,
        case_id: str,
        principal: ApplicationPrincipal,
    ) -> List[EvidenceResponse]:
        """List verified evidence records for a case, protected by Cedar READ_EVIDENCE."""
        case = case_store.get_case(case_id)
        if not case:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Case '{case_id}' not found")

        # Authorize via Cedar READ_EVIDENCE
        pep.enforce(
            principal=principal,
            action=CivicAction.READ_EVIDENCE,
            resource_id=case.case_id,
            resource_type="CivicCase",
            resource_owner=case.owner_id,
            resource_department=case.department,
            resource_status=case.status.value,
            is_public=case.is_public,
        )

        records = evidence_repo.list_evidence_for_case(case_id)
        return [
            EvidenceResponse(
                evidence_id=r.evidence_id,
                case_id=r.case_id,
                evidence_type=r.evidence_type,
                filename=r.filename,
                content_type=r.content_type,
                size_bytes=r.size_bytes,
                sha256=r.sha256,
                validation_status=r.validation_status,
                verification_status=r.verification_status,
                verification_reason=r.verification_reason,
                ai_confidence=r.ai_confidence,
                relevance=r.relevance,
                relevance_reason=r.relevance_reason,
                relevance_detected_features=r.relevance_detected_features,
                relevance_confidence=r.relevance_confidence,
                resolution_attempt=r.resolution_attempt,
                resolution_message=r.resolution_message,
                created_at=r.created_at,
                verified_at=r.verified_at,
            )
            for r in records
        ]


# Global singleton service
evidence_verification_service = EvidenceVerificationService()
