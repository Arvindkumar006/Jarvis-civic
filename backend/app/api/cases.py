"""Civic Case Management API Endpoints for JARVIS Civic.

Phase 3 Protected Endpoints:
Enforces Cedar authorization via the Policy Enforcement Point (PEP)
before performing case operations.
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from app.models.enums import CaseStatus, validate_status_transition
from app.models.security import (
    ApplicationPrincipal,
    CaseHistoryItem,
    CivicAction,
    CivicCaseCreateRequest,
    CivicCaseRecord,
    CivicCaseStatusUpdateRequest,
    CivicCaseUpdateRequest,
    EvidenceMetadata,
    ResolutionNoteRequest,
)
from app.security.audit import audit_dispatcher
from app.security.pep import pep
from app.security.principals import get_current_principal
from app.services.case_store import case_store

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

    return updated or case


@router.get("/{case_id}/history", response_model=List[CaseHistoryItem])
def get_case_history(
    case_id: str,
    principal: ApplicationPrincipal = Depends(get_current_principal),
) -> List[CaseHistoryItem]:
    """Retrieve sanitized lifecycle history for a case.

    Protected:
    - Public cases accessible via read_public_tracking.
    - Citizens accessible for their own cases.
    - Authorities/Supervisors/Admins accessible for assigned department cases.
    """
    case = case_store.get_case(case_id)
    if not case:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")

    action = (
        CivicAction.READ_PUBLIC_TRACKING
        if case.is_public
        else (
            CivicAction.READ_OWN_CASE
            if principal.role.value == "CITIZEN"
            else CivicAction.READ_AUTHORITY_CASE
        )
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

    return case_store.get_case_history(case_id)


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
    4. Validate file (size <= 10MB, non-empty, allowed extension/MIME, sanitize filename)
    5. Upload to S3 evidence repository
    6. Attach URI to case record in persistence store
    7. Record append-only audit event
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

    # 3. Read and validate file bytes
    file_bytes = await file.read()
    filename = file.filename or "evidence_attachment.jpg"
    content_type = file.content_type or "image/jpeg"

    # 4. Upload to S3 evidence repository
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

    return metadata

