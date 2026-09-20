"""Civic Case Management API Endpoints for JARVIS Civic.

Phase 3 Protected Endpoints:
Enforces Cedar authorization via the Policy Enforcement Point (PEP)
before performing case operations.
"""

from typing import Any, List, Optional, Union
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from app.config.settings import settings
from app.models.enums import CaseStatus, ControlledDepartment, validate_status_transition
from app.models.evidence import (
    DeterministicValidationStatus,
    EvidenceResponse,
    EvidenceType,
)
from app.models.security import (
    ApplicationPrincipal,
    ApplicationRole,
    AuthorizedCaseHistoryItem,
    CaseHistoryItem,
    CitizenResolutionAcceptRequest,
    CitizenResolutionRejectRequest,
    CivicAction,
    CivicCaseCreateRequest,
    CivicCaseRecord,
    CivicCaseStatusUpdateRequest,
    CivicCaseUpdateRequest,
    EvidenceMetadata,
    PublicCaseHistoryItem,
    ResolutionConfirmationRequest,
    ResolutionNoteRequest,
)
from app.models.notification import SanitizedNotificationItem, mask_email
from app.security.audit import audit_dispatcher
from app.security.pep import pep
from app.security.principals import get_current_principal
from app.services.case_store import case_store
from app.services.evidence.repository import evidence_repo
from app.services.evidence_verification_service import evidence_verification_service
from app.services.notifications import notification_service
from app.services.notifications.worker_dispatcher import worker_dispatcher
from app.services.search.opensearch_service import opensearch_service

router = APIRouter(prefix="/api/cases", tags=["Civic Cases"])


@router.post("", response_model=CivicCaseRecord, status_code=status.HTTP_201_CREATED)
def create_case(
    payload: CivicCaseCreateRequest,
    principal: ApplicationPrincipal = Depends(get_current_principal),
) -> CivicCaseRecord:
    """Create a new civic grievance case (Protected by Cedar: create_case)."""
    # Default operational department if not specified
    if not payload.department:
        desc_lower = (payload.description or "").lower()
        if any(w in desc_lower for w in ["water", "flood", "drain", "sewage", "storm", "manhole", "culvert"]):
            payload.department = ControlledDepartment.DRAINAGE_STORMWATER
        else:
            payload.department = ControlledDepartment.PWD_ROADS

    # Enforce policy via PEP
    pep.enforce(
        principal=principal,
        action=CivicAction.CREATE_CASE,
        resource_id="new_case",
        resource_type="CivicCase",
        resource_owner=principal.principal_id,
        resource_department=payload.department.value,
        resource_status=CaseStatus.DOCKET_CREATED.value,
        is_public=payload.is_public,
    )

    # Business operation
    record = case_store.create_case(
        request=payload,
        owner_id=principal.principal_id,
    )

    # Record workflow audit event
    audit_dispatcher.record_workflow_event(
        case_id=record.case_id,
        event_type="DOCKET_CREATED",
        previous_status="NONE",
        new_status=record.status.value,
        principal=principal,
        outcome="SUCCESS",
        metadata={
            "department": record.department,
            "location": record.location,
            "is_public": record.is_public,
        },
    )

    # Dispatch notifications (Citizen confirmation + Authority triage)
    # Failure never rolls back or corrupts the successfully created case
    try:
        worker_dispatcher.dispatch_case_created(record)
    except Exception as notif_err:
        import logging
        logging.getLogger("jarvis.api.cases").critical(
            "Notification dispatch exception on case %s: %s", record.case_id, notif_err
        )

    # OpenSearch Indexing (Phase 8.6): Resilient and non-blocking
    try:
        opensearch_service.index_docket(record)
    except Exception as os_err:
        import logging
        logging.getLogger("jarvis.api.cases").error(
            "OpenSearch indexing exception on case creation %s: %s", record.case_id, os_err
        )

    return record


@router.get("/{case_id}", response_model=CivicCaseRecord)
def get_case(
    case_id: str,
    principal: ApplicationPrincipal = Depends(get_current_principal),
) -> CivicCaseRecord:
    """Retrieve full civic case record (Protected by Cedar).

    - Citizen: evaluated under 'read_own_case' (must be owner)
    - Authority/Supervisor/Admin: evaluated under 'read_authority_case' (must match department scope)
    - Public: Denied
    """
    case = case_store.get_case(case_id)
    if not case:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")

    # Determine applicable action based on role
    action = (
        CivicAction.READ_OWN_CASE
        if principal.role.value == "CITIZEN"
        else CivicAction.READ_AUTHORITY_CASE
    )

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

    return case


@router.patch("/{case_id}", response_model=CivicCaseRecord)
def update_case(
    case_id: str,
    payload: CivicCaseUpdateRequest,
    principal: ApplicationPrincipal = Depends(get_current_principal),
) -> CivicCaseRecord:
    """Update citizen's own case details (Protected by Cedar: update_own_case)."""
    case = case_store.get_case(case_id)
    if not case:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")

    pep.enforce(
        principal=principal,
        action=CivicAction.UPDATE_OWN_CASE,
        resource_id=case.case_id,
        resource_type="CivicCase",
        resource_owner=case.owner_id,
        resource_department=case.department,
        resource_status=case.status.value,
        is_public=case.is_public,
    )

    updated = case_store.update_case(
        case_id=case_id,
        description=payload.description,
        location=payload.location,
        pincode=payload.pincode,
    )
    if updated:
        try:
            opensearch_service.update_docket(updated)
        except Exception as os_err:
            import logging
            logging.getLogger("jarvis.api.cases").error(
                "OpenSearch update exception on case %s: %s", case_id, os_err
            )
    return updated or case


@router.patch("/{case_id}/status", response_model=CivicCaseRecord)
def update_case_status(
    case_id: str,
    payload: CivicCaseStatusUpdateRequest,
    principal: ApplicationPrincipal = Depends(get_current_principal),
) -> CivicCaseRecord:
    """Update case status (Protected by Cedar: update_case_status).

    Permitted only for AuthorityOfficer (in department), MunicipalSupervisor, or Admin.
    Denied for Citizens and Public.
    """
    # 1. Resolve case
    case = case_store.get_case(case_id)
    if not case:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")

    # 2. Enforce Cedar authorization FIRST (fail-closed)
    pep.enforce(
        principal=principal,
        action=CivicAction.UPDATE_CASE_STATUS,
        resource_id=case.case_id,
        resource_type="CivicCase",
        resource_owner=case.owner_id,
        resource_department=case.department,
        resource_status=case.status.value,
        is_public=case.is_public,
    )

    # Closure Gate Restriction: Direct transition to RESOLVED is strictly prohibited for authority status updates.
    if payload.status == CaseStatus.RESOLVED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Direct transition to RESOLVED is restricted: case closure is gated on authenticated citizen resolution confirmation.",
        )

    # 3. Validate lifecycle state machine transition (Single-step forward only)
    validate_status_transition(case.status, payload.status)

    prev_status = case.status.value
    expected_status = case.status
    # 4. Mutate persistent store with concurrency safeguard
    updated = case_store.update_case_status(
        case_id=case_id,
        new_status=payload.status,
        note=payload.note,
        actor_label=principal.role.value,
        expected_current_status=expected_status,
    )

    # 5. Record append-only workflow audit event
    try:
        audit_dispatcher.record_workflow_event(
            case_id=case_id,
            event_type="STATUS_TRANSITION",
            previous_status=prev_status,
            new_status=payload.status.value,
            principal=principal,
            outcome="SUCCESS",
            metadata={"note": payload.note} if payload.note else {},
        )
    except Exception as audit_err:
        import logging
        logging.getLogger("jarvis.api.cases").critical(
            "Audit event recording failed after status transition on case %s: %s", case_id, audit_err
        )
    # 6. Dispatch workflow stage transition notification
    try:
        worker_dispatcher.dispatch_workflow_stage_changed(
            case=updated or case,
            previous_status=prev_status,
            new_status=payload.status.value,
        )
    except Exception as notif_err:
        import logging
        logging.getLogger("jarvis.api.cases").critical(
            "Notification stage dispatch exception on case %s: %s", case_id, notif_err
        )

    # OpenSearch Projection Update (Phase 8.6): Resilient and non-blocking
    try:
        opensearch_service.update_docket(updated or case)
    except Exception as os_err:
        import logging
        logging.getLogger("jarvis.api.cases").error(
            "OpenSearch update exception on case status update %s: %s", case_id, os_err
        )

    return updated or case


@router.post("/{case_id}/resolution/accept", response_model=CivicCaseRecord)
def accept_resolution(
    case_id: str,
    payload: CitizenResolutionAcceptRequest = CitizenResolutionAcceptRequest(),
    principal: ApplicationPrincipal = Depends(get_current_principal),
) -> CivicCaseRecord:
    """Accept case resolution and trigger final case closure (Protected by Cedar: accept_resolution).

    Permitted strictly for the authenticated citizen case owner.
    Denied for administrators, authorities, supervisors, and public users.
    """
    case = case_store.get_case(case_id)
    if not case:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")

    # 1. Enforce Cedar authorization FIRST (fail-closed)
    pep.enforce(
        principal=principal,
        action=CivicAction.ACCEPT_RESOLUTION,
        resource_id=case.case_id,
        resource_type="CivicCase",
        resource_owner=case.owner_id,
        resource_department=case.department,
        resource_status=case.status.value,
        is_public=case.is_public,
    )

    # 2. Idempotency safeguard: if case is already RESOLVED and confirmed, return existing record
    if case.status == CaseStatus.RESOLVED and case.resolution_confirmed:
        return case

    # 3. Pre-condition: Case must have verified resolution evidence with valid deterministic validation
    evidence_records = evidence_repo.list_evidence_for_case(case_id)
    valid_resolution_ev = [
        e for e in evidence_records
        if e.evidence_type == EvidenceType.RESOLUTION_EVIDENCE
        and e.validation_status == DeterministicValidationStatus.VALID
    ]
    if not valid_resolution_ev:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot accept resolution: docket lacks verified resolution evidence with valid deterministic validation.",
        )

    # 4. Pre-condition: Case must be in UNDER_REVIEW status
    if case.status != CaseStatus.UNDER_REVIEW:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot accept resolution: case must be in 'UNDER_REVIEW' status, currently '{case.status.value}'.",
        )

    # 5. Persist citizen confirmation and transition directly to RESOLVED
    prev_status = case.status.value
    updated = case_store.confirm_and_resolve_case(
        case_id=case_id,
        feedback=payload.feedback,
        actor_label=principal.role.value,
    )

    # 6. Record append-only workflow audit events
    try:
        audit_dispatcher.record_workflow_event(
            case_id=case_id,
            event_type="RESOLUTION_ACCEPTED",
            previous_status=prev_status,
            new_status=CaseStatus.RESOLVED.value,
            principal=principal,
            outcome="SUCCESS",
            metadata={
                "feedback": payload.feedback,
                "active_attempt": case.active_resolution_attempt,
                "evidence_count": len(valid_resolution_ev),
            },
        )
        audit_dispatcher.record_workflow_event(
            case_id=case_id,
            event_type="STATUS_TRANSITION",
            previous_status=prev_status,
            new_status=CaseStatus.RESOLVED.value,
            principal=principal,
            outcome="SUCCESS",
            metadata={"note": "Citizen confirmed resolution; docket transitioned to RESOLVED"},
        )
    except Exception as audit_err:
        import logging
        logging.getLogger("jarvis.api.cases").critical(
            "Audit event recording failed after resolution acceptance on case %s: %s", case_id, audit_err
        )

    # 7. Update OpenSearch docket index
    try:
        opensearch_service.update_docket(updated or case)
    except Exception as os_err:
        import logging
        logging.getLogger("jarvis.api.cases").error(
            "OpenSearch update exception on resolution accept %s: %s", case_id, os_err
        )

    # 8. Dispatch notifications (Citizen receipt + Authority alert)
    try:
        worker_dispatcher.dispatch_resolution_confirmed(
            case=updated or case,
            feedback=payload.feedback,
        )
    except Exception as notif_err:
        import logging
        logging.getLogger("jarvis.api.cases").critical(
            "Notification dispatch exception on resolution accept %s: %s", case_id, notif_err
        )

    return updated or case


@router.post("/{case_id}/resolution/reject", response_model=CivicCaseRecord)
def reject_resolution(
    case_id: str,
    payload: CitizenResolutionRejectRequest,
    principal: ApplicationPrincipal = Depends(get_current_principal),
) -> CivicCaseRecord:
    """Reject case resolution and return to authority for corrective rework (Protected by Cedar: reject_resolution).

    Permitted strictly for the authenticated citizen case owner.
    Denied for administrators, authorities, supervisors, and public users.
    Requires substantive explanation of why resolution is rejected (reason >= 5 chars).
    """
    case = case_store.get_case(case_id)
    if not case:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")

    # 1. Enforce Cedar authorization FIRST (fail-closed)
    pep.enforce(
        principal=principal,
        action=CivicAction.REJECT_RESOLUTION,
        resource_id=case.case_id,
        resource_type="CivicCase",
        resource_owner=case.owner_id,
        resource_department=case.department,
        resource_status=case.status.value,
        is_public=case.is_public,
    )

    # 2. Cannot reject an already resolved docket
    if case.status == CaseStatus.RESOLVED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot reject resolution on an already resolved case.",
        )

    # 3. Pre-condition: Must have resolution evidence submitted
    evidence_records = evidence_repo.list_evidence_for_case(case_id)
    resolution_ev = [e for e in evidence_records if e.evidence_type == EvidenceType.RESOLUTION_EVIDENCE]
    if not resolution_ev:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot reject resolution: no resolution evidence has been submitted for this docket.",
        )

    # 4. Pre-condition: Case must be in UNDER_REVIEW
    if case.status != CaseStatus.UNDER_REVIEW:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot reject resolution: case must be in 'UNDER_REVIEW' status, currently '{case.status.value}'.",
        )

    # 5. Persist rejection, increment rejection_count, store feedback, append notes
    updated = case_store.reject_resolution(
        case_id=case_id,
        reason=payload.reason,
        actor_label=principal.role.value,
    )

    # 6. Record append-only workflow audit event
    try:
        audit_dispatcher.record_workflow_event(
            case_id=case_id,
            event_type="RESOLUTION_REJECTED",
            previous_status=case.status.value,
            new_status=case.status.value,
            principal=principal,
            outcome="SUCCESS",
            metadata={
                "reason": payload.reason,
                "rejection_count": updated.rejection_count if updated else case.rejection_count + 1,
                "active_attempt": case.active_resolution_attempt,
            },
        )
    except Exception as audit_err:
        import logging
        logging.getLogger("jarvis.api.cases").critical(
            "Audit event recording failed after resolution rejection on case %s: %s", case_id, audit_err
        )

    # 7. Update OpenSearch docket index
    try:
        opensearch_service.update_docket(updated or case)
    except Exception as os_err:
        import logging
        logging.getLogger("jarvis.api.cases").error(
            "OpenSearch update exception on resolution reject %s: %s", case_id, os_err
        )

    # 8. Dispatch notification to responsible authority alerting them of rework requirement
    try:
        worker_dispatcher.dispatch_resolution_rejected(
            case=updated or case,
            reason=payload.reason,
        )
    except Exception as notif_err:
        import logging
        logging.getLogger("jarvis.api.cases").critical(
            "Notification dispatch exception on resolution reject %s: %s", case_id, notif_err
        )

    return updated or case


@router.post("/{case_id}/resolution/request-confirmation", response_model=CivicCaseRecord)
def request_citizen_confirmation(
    case_id: str,
    payload: ResolutionConfirmationRequest = ResolutionConfirmationRequest(),
    principal: ApplicationPrincipal = Depends(get_current_principal),
) -> CivicCaseRecord:
    """Request citizen confirmation on submitted resolution evidence (Protected by Cedar: request_citizen_confirmation).

    Permitted exclusively for AuthorityOfficer and MunicipalSupervisor within matching department scope.
    Strictly denied for Administrator, Citizen, and Public roles.
    """
    case = case_store.get_case(case_id)
    if not case:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")

    # 1. Enforce Cedar authorization FIRST (fail-closed)
    pep.enforce(
        principal=principal,
        action=CivicAction.REQUEST_CITIZEN_CONFIRMATION,
        resource_id=case.case_id,
        resource_type="CivicCase",
        resource_owner=case.owner_id,
        resource_department=case.department,
        resource_status=case.status.value,
        is_public=case.is_public,
    )

    # 2. Gate Condition: case.status == UNDER_REVIEW
    if case.status != CaseStatus.UNDER_REVIEW:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot request citizen confirmation: case must be in 'UNDER_REVIEW' status, currently '{case.status.value}'.",
        )

    # 3. Gate Condition: active resolution attempt exists
    if not case.active_resolution_attempt:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot request citizen confirmation: no active resolution attempt exists for this docket.",
        )

    # 4. Gate Condition: valid deterministic RESOLUTION_EVIDENCE exists
    evidence_records = evidence_repo.list_evidence_for_case(case_id)
    valid_resolution_ev = [
        e for e in evidence_records
        if e.evidence_type == EvidenceType.RESOLUTION_EVIDENCE
        and e.validation_status == DeterministicValidationStatus.VALID
    ]
    if not valid_resolution_ev:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot request citizen confirmation: docket lacks verified resolution evidence with valid deterministic validation.",
        )

    # 5. Gate Condition: resolution evidence belongs to the active attempt
    attempt_ev = [
        e for e in valid_resolution_ev
        if e.resolution_attempt == case.active_resolution_attempt
    ]
    if not attempt_ev:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot request citizen confirmation: no valid resolution evidence found belonging to active attempt '{case.active_resolution_attempt}'.",
        )

    # 6. Gate Condition: active resolution attempt is not rejected
    # If case was rejected, evidence uploaded prior to or at rejection timestamp belongs to a rejected attempt
    if case.resolution_rejected_at is not None:
        fresh_attempt_ev = [
            e for e in attempt_ev
            if e.created_at > case.resolution_rejected_at
        ]
        if not fresh_attempt_ev:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Cannot request citizen confirmation: active resolution attempt was rejected. New resolution evidence and corrective rework must be submitted.",
            )

    # 7. Gate Condition: non-empty persisted resolution message exists
    # Single authoritative message rule:
    # Use existing persisted message on case or active evidence record; do NOT overwrite!
    effective_msg = case.resolution_message
    if not effective_msg or not effective_msg.strip():
        for ev in attempt_ev:
            if getattr(ev, "resolution_message", None) and ev.resolution_message.strip():
                effective_msg = ev.resolution_message.strip()
                break

    if not effective_msg or not effective_msg.strip():
        # If payload provides a message, populate it if absent
        if payload.message and payload.message.strip():
            effective_msg = payload.message.strip()
            case_store.set_active_resolution_attempt(
                case_id=case_id,
                attempt_id=case.active_resolution_attempt,
                resolution_message=effective_msg,
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Cannot request citizen confirmation: non-empty persisted resolution message required.",
            )

    # 8. Persist confirmation request in backend store
    updated = case_store.request_citizen_confirmation(
        case_id=case_id,
        actor_label=principal.role.value,
    )

    # 9. Record append-only workflow audit event
    try:
        audit_dispatcher.record_workflow_event(
            case_id=case_id,
            event_type="CITIZEN_CONFIRMATION_REQUESTED",
            previous_status=case.status.value,
            new_status=case.status.value,
            principal=principal,
            outcome="SUCCESS",
            metadata={
                "active_attempt": case.active_resolution_attempt,
                "resolution_message": effective_msg,
                "evidence_count": len(attempt_ev),
            },
        )
    except Exception as audit_err:
        import logging
        logging.getLogger("jarvis.api.cases").critical(
            "Audit event recording failed on request citizen confirmation for case %s: %s", case_id, audit_err
        )

    # 10. Update OpenSearch docket index
    try:
        opensearch_service.update_docket(updated or case)
    except Exception as os_err:
        import logging
        logging.getLogger("jarvis.api.cases").error(
            "OpenSearch update exception on request citizen confirmation %s: %s", case_id, os_err
        )

    # 11. Dispatch notification to citizen alerting them that confirmation is requested
    try:
        worker_dispatcher.dispatch_resolution_ready(
            case=updated or case,
            proposed_notes=effective_msg,
        )
    except Exception as notif_err:
        import logging
        logging.getLogger("jarvis.api.cases").critical(
            "Notification dispatch exception on request citizen confirmation %s: %s", case_id, notif_err
        )

    return updated or case


@router.post("/{case_id}/notes", response_model=CivicCaseRecord)
@router.post("/{case_id}/resolution-note", response_model=CivicCaseRecord)
def add_resolution_note(
    case_id: str,
    payload: ResolutionNoteRequest,
    principal: ApplicationPrincipal = Depends(get_current_principal),
) -> CivicCaseRecord:
    """Add an authority resolution note (Protected by Cedar: add_resolution_note)."""
    case = case_store.get_case(case_id)
    if not case:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")

    pep.enforce(
        principal=principal,
        action=CivicAction.ADD_RESOLUTION_NOTE,
        resource_id=case.case_id,
        resource_type="CivicCase",
        resource_owner=case.owner_id,
        resource_department=case.department,
        resource_status=case.status.value,
        is_public=case.is_public,
    )

    updated = case_store.add_resolution_note(
        case_id=case_id,
        note=payload.note,
        actor_label=principal.role.value,
    )

    audit_dispatcher.record_workflow_event(
        case_id=case_id,
        event_type="RESOLUTION_NOTE_ADDED",
        previous_status=case.status.value,
        new_status=case.status.value,
        principal=principal,
        outcome="SUCCESS",
        metadata={"note": payload.note},
    )

    # OpenSearch Projection Update (Phase 8.6): Resilient and non-blocking
    try:
        opensearch_service.update_docket(updated or case)
    except Exception as os_err:
        import logging
        logging.getLogger("jarvis.api.cases").error(
            "OpenSearch update exception on resolution note %s: %s", case_id, os_err
        )

    return updated or case


@router.get("/{case_id}/history", response_model=Union[List[AuthorizedCaseHistoryItem], List[PublicCaseHistoryItem]])
def get_case_history(
    case_id: str,
    principal: ApplicationPrincipal = Depends(get_current_principal),
) -> Any:
    """Retrieve sanitized lifecycle history for a case.

    Protected:
    - Public: receives PublicCaseHistoryItem (actor_role, note, department, internal fields stripped).
    - Citizen: evaluated under read_own_case (must be owner); receives PublicCaseHistoryItem (clean citizen-safe milestones).
    - Authorities/Supervisors/Admins: evaluated under read_authority_case; receives AuthorizedCaseHistoryItem.
    """
    case = case_store.get_case(case_id)
    if not case:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")

    is_authority_user = principal.role in (
        ApplicationRole.AUTHORITY_OFFICER,
        ApplicationRole.MUNICIPAL_SUPERVISOR,
        ApplicationRole.ADMINISTRATOR,
    )

    if is_authority_user:
        action = CivicAction.READ_AUTHORITY_CASE
    elif principal.role == ApplicationRole.CITIZEN:
        action = CivicAction.READ_OWN_CASE
    else:
        action = CivicAction.READ_PUBLIC_TRACKING

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

    raw_history = case_store.get_case_history(case_id)

    if is_authority_user:
        return [
            AuthorizedCaseHistoryItem(
                milestone_id=h.milestone_id,
                status=h.status,
                label=h.label,
                timestamp=h.timestamp,
                department=h.department,
                description=h.description,
                actor_role=h.actor_role,
                note=h.note,
            )
            for h in raw_history
        ]

    # Public or Citizen: Strictly PublicCaseHistoryItem projection
    return [
        PublicCaseHistoryItem(
            milestone_id=h.milestone_id,
            status=h.status,
            label=h.label,
            timestamp=h.timestamp,
            description=h.description,
        )
        for h in raw_history
    ]


@router.post("/{case_id}/evidence", response_model=EvidenceResponse, status_code=status.HTTP_201_CREATED)
async def upload_case_evidence(
    case_id: str,
    file: UploadFile = File(...),
    evidence_type: EvidenceType = Form(EvidenceType.CASE_EVIDENCE),
    resolution_attempt: Optional[str] = Form(None),
    resolution_message: Optional[str] = Form(None),
    principal: ApplicationPrincipal = Depends(get_current_principal),
) -> EvidenceResponse:
    """Upload, verify, and attach evidence to a civic case.

    CRITICAL SECURITY & EXECUTION ORDER:
    1. Resolve case record
    2. Cedar authorization (action: add_evidence vs add_resolution_evidence)
    3. ALLOW from Cedar PEP (DENY halts with HTTP 403)
    4. Bounded streaming read (reject oversized uploads before buffering arbitrary data in memory)
    5. Deterministic validation (magic bytes, MIME, SHA-256)
    6. Secure persistence
    7. Advisory AI assessment
    8. Trusted server-side record creation
    9. Append-only audit event
    10. Notification dispatch
    """
    case = case_store.get_case(case_id)
    if not case:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")

    # Enforce Cedar authorization BEFORE streaming or buffering file
    action = (
        CivicAction.ADD_RESOLUTION_EVIDENCE
        if evidence_type == EvidenceType.RESOLUTION_EVIDENCE
        else CivicAction.ADD_EVIDENCE
    )
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

    # Bounded streaming read (reject oversized uploads before buffering arbitrary data in memory)
    max_bytes = settings.MAX_EVIDENCE_SIZE_BYTES
    chunk_size = 1024 * 1024  # 1MB chunks
    chunks = []
    total_read = 0

    while True:
        chunk = await file.read(chunk_size)
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
    filename = file.filename or "evidence_attachment.jpg"
    content_type = file.content_type or "image/jpeg"

    return evidence_verification_service.verify_and_store_evidence(
        case_id=case_id,
        principal=principal,
        file_bytes=file_bytes,
        filename=filename,
        content_type=content_type,
        evidence_type=evidence_type,
        resolution_attempt=resolution_attempt,
        resolution_message=resolution_message,
    )


@router.get("/{case_id}/evidence", response_model=List[EvidenceResponse])
def list_case_evidence(
    case_id: str,
    principal: ApplicationPrincipal = Depends(get_current_principal),
) -> List[EvidenceResponse]:
    """Retrieve verified evidence records for a case, authorized by Cedar READ_EVIDENCE."""
    return evidence_verification_service.list_case_evidence(case_id=case_id, principal=principal)


@router.get("/{case_id}/notifications", response_model=List[SanitizedNotificationItem])
def get_case_notifications(
    case_id: str,
    principal: ApplicationPrincipal = Depends(get_current_principal),
) -> List[SanitizedNotificationItem]:
    """Retrieve sanitized notification delivery history for a case.

    Protected by Cedar authorization:
    - Citizen: evaluated under read_own_case (must be case owner).
    - Authorities/Supervisors/Admins: evaluated under read_authority_case (must match department).
    - Public / Unauthenticated: Denied (HTTP 403 / 401).

    Sanitization: Never leaks SMTP credentials, password hashes, session IDs,
    or other recipients' private information.
    """
    case = case_store.get_case(case_id)
    if not case:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")

    action = (
        CivicAction.READ_OWN_CASE
        if principal.role == ApplicationRole.CITIZEN
        else CivicAction.READ_AUTHORITY_CASE
    )

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

    raw_records = notification_service.get_case_notifications(case_id)
    return [
        SanitizedNotificationItem(
            notification_id=r.notification_id,
            case_id=r.case_id,
            event_type=r.event_type,
            recipient_role=r.recipient_role,
            recipient_masked_email=mask_email(r.recipient_email),
            subject=r.subject,
            status=r.status,
            created_at=r.created_at,
            sent_at=r.sent_at,
            failed_at=r.failed_at,
        )
        for r in raw_records
    ]
