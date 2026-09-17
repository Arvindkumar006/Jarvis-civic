"""Audit Log Inspection API Endpoint for JARVIS Civic.

Phase 3 Protected Endpoint:
Provides access to application-level append-only authorization audit records.

Access Control:
- Administrator: universal audit access
- MunicipalSupervisor: scoped to supervisor's assigned department
- Citizen / Public / AuthorityOfficer: Strictly DENIED (HTTP 403)
"""

from typing import List
from fastapi import APIRouter, Depends

from app.models.security import (
    ApplicationPrincipal,
    ApplicationRole,
    CivicAction,
)
from app.security.audit import AuditEvent, audit_dispatcher
from app.security.pep import pep
from app.security.principals import get_current_principal

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

    # Supervisor only receives records matching department
    if principal.role == ApplicationRole.MUNICIPAL_SUPERVISOR:
        return audit_dispatcher.get_events(department=principal.department)

    # Administrator receives all records
    return audit_dispatcher.get_events()
