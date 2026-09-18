"""Audit Log Inspection API Endpoint for JARVIS Civic.

Phase 3 Protected Endpoint:
Provides access to application-level append-only authorization audit records.

Access Control:
- Administrator: universal audit access
- MunicipalSupervisor: scoped to supervisor's assigned department
- Citizen / Public / AuthorityOfficer: Strictly DENIED (HTTP 403)
"""

from typing import List
from fastapi import APIRouter, Depends, HTTPException, status

from app.models.security import (
    ApplicationPrincipal,
    ApplicationRole,
    CivicAction,
)
from app.security.audit import AuditEvent
from app.security.pep import pep
from app.security.principals import get_current_principal
from app.services.case_store import case_store
from app.services.persistence.factory import get_audit_repository

router = APIRouter(prefix="/api/audit", tags=["Security Audit"])


@router.get("/logs", response_model=List[AuditEvent])
def get_audit_logs(
    principal: ApplicationPrincipal = Depends(get_current_principal),
) -> List[AuditEvent]:
    """Retrieve security audit events.

    Protected by Cedar under 'read_audit_log'.
    """
    # Enforce policy via PEP
    pep.enforce(
        principal=principal,
        action=CivicAction.READ_AUDIT_LOG,
        resource_id="system_audit_records",
        resource_type="AuditRecord",
        resource_department=principal.department,
    )

    audit_repo = get_audit_repository()
    # Supervisor only receives records matching department
    if principal.role == ApplicationRole.MUNICIPAL_SUPERVISOR:
        return audit_repo.get_events(department=principal.department)

    # Administrator receives all records
    return audit_repo.get_events()


@router.get("/cases/{case_id}", response_model=List[AuditEvent])
def get_case_audit_trail(
    case_id: str,
    principal: ApplicationPrincipal = Depends(get_current_principal),
) -> List[AuditEvent]:
    """Retrieve audit events for a specific case.

    Protected by Cedar under 'read_audit_log'.
    Supervisor is scoped to supervisor's assigned department matching case.department.
    Administrator has universal access.
    Citizen / Public / AuthorityOfficer: Strictly DENIED (HTTP 403).
    """
    case = case_store.get_case(case_id)
    if not case:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")

    # Enforce Cedar authorization
    pep.enforce(
        principal=principal,
        action=CivicAction.READ_AUDIT_LOG,
        resource_id=f"audit_case_{case.case_id}",
        resource_type="AuditRecord",
        resource_department=case.department,
    )

    # Supervisor double-check on department
    if principal.role == ApplicationRole.MUNICIPAL_SUPERVISOR:
        if principal.department != case.department:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Department scope mismatch for supervisor audit access",
            )

    audit_repo = get_audit_repository()
    return audit_repo.get_events_for_case(case_id)
