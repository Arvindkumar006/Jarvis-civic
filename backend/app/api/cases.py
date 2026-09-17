"""Civic Case Management API Endpoints for JARVIS Civic.

Phase 3 Protected Endpoints:
Enforces Cedar authorization via the Policy Enforcement Point (PEP)
before performing case operations.
"""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status

from app.models.enums import CaseStatus
from app.models.security import (
    ApplicationPrincipal,
    CivicAction,
    CivicCaseCreateRequest,
    CivicCaseRecord,
    CivicCaseStatusUpdateRequest,
    CivicCaseUpdateRequest,
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

    if payload.description is not None:
        case.description = payload.description
    if payload.location is not None:
        case.location = payload.location
    if payload.pincode is not None:
        case.pincode = payload.pincode

    return case


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
