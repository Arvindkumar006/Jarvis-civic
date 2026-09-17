"""Property-Style Security Invariant Tests for JARVIS Civic.

Phase 3 Invariant Verification:
1. Invariant 1: No Citizen can read another Citizen's CivicCase across any combination of IDs.
2. Invariant 2: No Citizen can perform Authority-only case status updates under any circumstances.
"""

import pytest
from app.models.security import (
    ApplicationPrincipal,
    ApplicationRole,
    AuthorizationRequest,
    CivicAction,
)
from app.security.cedar_service import cedar_service


@pytest.mark.parametrize(
    "requester_id, owner_id",
    [
        ("citizen-100", "citizen-200"),
        ("citizen-alpha", "citizen-beta"),
        ("user_99", "user_100"),
        ("c_chennai_1", "c_chennai_2"),
        ("random_cit_x", "random_cit_y"),
    ],
)
def test_invariant_citizen_cannot_read_another_citizens_case(requester_id, owner_id):
    """Security Invariant 1: A Citizen can NEVER read another Citizen's case.

    For any Citizen A != Citizen B:
    Evaluation of read_own_case MUST evaluate to DENY.
    """
    assert requester_id != owner_id

    principal = ApplicationPrincipal(
        principal_id=requester_id,
        role=ApplicationRole.CITIZEN,
    )

    req = AuthorizationRequest(
        principal=principal,
        action=CivicAction.READ_OWN_CASE,
        resource_id=f"case_of_{owner_id}",
        resource_type="CivicCase",
        resource_owner=owner_id,
        resource_department="DRAINAGE_STORMWATER",
    )

    decision = cedar_service.authorize(req)
    assert decision.allowed is False, (
        f"Security Invariant VIOLATED: {requester_id} was allowed to read case owned by {owner_id}"
    )
    assert decision.decision == "DENY"


@pytest.mark.parametrize(
    "citizen_id, department, status",
    [
        ("citizen-001", "DRAINAGE_STORMWATER", "RESOLVED"),
        ("citizen-002", "WASTE_MANAGEMENT", "UNDER_REVIEW"),
        ("citizen-003", "PWD_ROADS", "RESOLVED"),
        ("citizen-admin-impersonator", "MUNICIPAL_CORPORATION", "RESOLVED"),
    ],
)
def test_invariant_citizen_cannot_perform_authority_status_update(citizen_id, department, status):
    """Security Invariant 2: A Citizen can NEVER perform Authority-only status updates.

    Even for their own case, a Citizen cannot alter the authority lifecycle state.
    """
    principal = ApplicationPrincipal(
        principal_id=citizen_id,
        role=ApplicationRole.CITIZEN,
    )

    req = AuthorizationRequest(
        principal=principal,
        action=CivicAction.UPDATE_CASE_STATUS,
        resource_id=f"case_owned_by_{citizen_id}",
        resource_type="CivicCase",
        resource_owner=citizen_id,  # Even on own case!
        resource_department=department,
        resource_status=status,
    )

    decision = cedar_service.authorize(req)
    assert decision.allowed is False, (
        f"Security Invariant VIOLATED: Citizen {citizen_id} was allowed to update status to {status}"
    )
    assert decision.decision == "DENY"
