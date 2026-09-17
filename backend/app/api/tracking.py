"""Public Case Tracking API Endpoint for JARVIS Civic.

Phase 3 Public Endpoint:
Permits public citizens and anonymous users to track civic case status
without requiring Citizen authentication.

SECURITY INVARIANT:
Public tracking projections strictly exclude private citizen identity,
contact data, private notes, and internal authorization metadata.
"""

from fastapi import APIRouter, Depends, HTTPException, status

from app.models.security import (
    ApplicationPrincipal,
    CivicAction,
    PublicTrackingProjection,
)
from app.security.pep import pep
from app.security.principals import get_current_principal
from app.services.case_store import case_store

router = APIRouter(prefix="/api/tracking", tags=["Public Tracking"])


@router.get("/{case_id}", response_model=PublicTrackingProjection)
def get_public_tracking(
    case_id: str,
    principal: ApplicationPrincipal = Depends(get_current_principal),
) -> PublicTrackingProjection:
    """Retrieve public-safe tracking projection for a civic grievance case.

    Protected by Cedar under 'read_public_tracking'.
    Does NOT require citizen credentials; unauthenticated requests evaluate safely as PublicUser.
    """
    case = case_store.get_case(case_id)
    if not case:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")

    # Enforce policy via PEP (allowed if case.is_public == True)
    pep.enforce(
        principal=principal,
        action=CivicAction.READ_PUBLIC_TRACKING,
        resource_id=case.case_id,
        resource_type="CivicCase",
        resource_owner=case.owner_id,
        resource_department=case.department,
        resource_status=case.status.value,
        is_public=case.is_public,
    )

    # Return safe public projection ONLY
    return PublicTrackingProjection(
        case_id=case.case_id,
        status=case.status.value,
        recommended_department=case.department,
        created_at=case.created_at,
        updated_at=case.updated_at,
    )
