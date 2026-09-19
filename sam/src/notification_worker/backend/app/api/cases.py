"""Civic Case Management API Endpoints for JARVIS Civic.

Phase 3 Protected Endpoints:
Enforces Cedar authorization via the Policy Enforcement Point (PEP)
before performing case operations.
"""

from typing import Any, List, Optional, Union
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from app.config.settings import settings
from app.models.enums import CaseStatus, validate_status_transition
from app.models.security import (
    ApplicationPrincipal,
    ApplicationRole,
    AuthorizedCaseHistoryItem,
    CaseHistoryItem,
    CivicAction,
    CivicCaseCreateRequest,
    CivicCaseRecord,
    CivicCaseStatusUpdateRequest,
    CivicCaseUpdateRequest,
    EvidenceMetadata,
    PublicCaseHistoryItem,
    ResolutionNoteRequest,
)
from app.models.notification import SanitizedNotificationItem, mask_email
from app.security.audit import audit_dispatcher
from app.security.pep import pep
from app.security.principals import get_current_principal
from app.services.case_store import case_store
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


@router.post("/{case_id}/evidence", response_model=EvidenceMetadata, status_code=status.HTTP_201_CREATED)
async def upload_case_evidence(
    case_id: str,
    file: UploadFile = File(...),
    principal: ApplicationPrincipal = Depends(get_current_principal),
) -> EvidenceMetadata:
    """Upload and attach evidence to a civic case.

    CRITICAL SECURITY & EXECUTION ORDER:
    1. Resolve case record
    2. Cedar authorization (action: add_evidence)
    3. ALLOW from Cedar PEP (DENY halts with HTTP 403)
    4. Bounded streaming read (reject oversized uploads before buffering arbitrary data in memory)
    5. Validate file (size <= 10MB, non-empty, allowed extension/MIME, magic byte signatures, sanitize filename)
    6. Upload to S3 evidence repository
    7. Attach URI to case record in persistence store
    8. Record append-only audit event
    """
    # 1. Resolve case
    case = case_store.get_case(case_id)
    if not case:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")

    # 2. Enforce Cedar authorization BEFORE any storage action
    pep.enforce(
        principal=principal,
        action=CivicAction.ADD_EVIDENCE,
        resource_id=case.case_id,
        resource_type="CivicCase",
        resource_owner=case.owner_id,
        resource_department=case.department,
        resource_status=case.status.value,
        is_public=case.is_public,
    )

    # 3. Bounded streaming read (reject oversized uploads before buffering arbitrary data in memory)
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

    # 4. Upload to S3 evidence repository (includes magic byte and extension validation)
    metadata = case_store.evidence_repo.upload_evidence(
        case_id=case_id,
        file_bytes=file_bytes,
        filename=filename,
        content_type=content_type,
    )

    # 5. Attach URI to case
    case_store.add_evidence_uri(case_id, metadata.s3_uri)

    # 6. Dispatch workflow audit event
    audit_dispatcher.record_workflow_event(
        case_id=case_id,
        event_type="EVIDENCE_ATTACHED",
        previous_status=case.status.value,
        new_status=case.status.value,
        principal=principal,
        outcome="SUCCESS",
        metadata={"filename": metadata.filename, "size_bytes": metadata.size_bytes},
    )

    # 7. Dispatch evidence available notification
    try:
        worker_dispatcher.dispatch_evidence_uploaded(case, metadata)
    except Exception as notif_err:
        import logging
        logging.getLogger("jarvis.api.cases").critical(
            "Notification evidence dispatch exception on case %s: %s", case_id, notif_err
        )

    return metadata


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
