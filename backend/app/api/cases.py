"""Civic Case Management API Endpoints for JARVIS Civic.

Phase 3 Protected Endpoints:
Enforces Cedar authorization via the Policy Enforcement Point (PEP)
before performing case operations.
"""

from typing import Optional
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from app.models.enums import CaseStatus
from app.models.security import (
    ApplicationPrincipal,
    CivicAction,
    CivicCaseCreateRequest,
    CivicCaseRecord,
    CivicCaseStatusUpdateRequest,
    CivicCaseUpdateRequest,
    EvidenceMetadata,
    ResolutionNoteRequest,
)
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
    case = case_store.get_case(case_id)
    if not case:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")

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

    updated = case_store.update_case_status(
        case_id=case_id,
        new_status=payload.status,
        note=payload.note,
    )
    return updated or case


@router.post("/{case_id}/notes", response_model=CivicCaseRecord)
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

    updated = case_store.add_resolution_note(case_id=case_id, note=payload.note)
    return updated or case


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

    return metadata

