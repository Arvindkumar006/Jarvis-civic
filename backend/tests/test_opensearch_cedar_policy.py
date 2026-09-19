"""Unit tests for Cedar Authorization on CivicDocketSearch (Phase 8.6).

Tests that Cedar PDP strictly enforces:
- AuthorityOfficer may search own department (ALLOW)
- AuthorityOfficer cannot search another department (DENY)
- MunicipalSupervisor may search own department (ALLOW)
- MunicipalSupervisor cannot search another department (DENY)
- Administrator may search any department or ALL (ALLOW)
- Citizen cannot search dockets (DENY - default deny)
- PublicUser cannot search dockets (DENY - default deny)
- Missing / empty department fails closed (DENY)
"""

import pytest
from app.models.security import (
    ApplicationPrincipal,
    ApplicationRole,
    AuthorizationRequest,
    CivicAction,
)
from app.security.cedar_service import CedarService


@pytest.fixture
def cedar_pdp() -> CedarService:
    service = CedarService()
    assert service.is_healthy(), "Cedar PDP must be successfully initialized"
    return service


def test_authority_officer_search_own_department_allowed(cedar_pdp: CedarService):
    """Authority officer searching their assigned department is ALLOWED by Policy G."""
    principal = ApplicationPrincipal(
        principal_id="officer-drainage-01",
        role=ApplicationRole.AUTHORITY_OFFICER,
        department="DRAINAGE_STORMWATER",
    )
    req = AuthorizationRequest(
        principal=principal,
        action=CivicAction.SEARCH_DOCKETS,
        resource_id="DRAINAGE_STORMWATER",
        resource_type="CivicDocketSearch",
        resource_department="DRAINAGE_STORMWATER",
    )
    decision = cedar_pdp.authorize(req)
    assert decision.allowed is True
    assert decision.decision == "ALLOW"


def test_authority_officer_search_other_department_denied(cedar_pdp: CedarService):
    """Authority officer attempting to search another department is DENIED."""
    principal = ApplicationPrincipal(
        principal_id="officer-drainage-01",
        role=ApplicationRole.AUTHORITY_OFFICER,
        department="DRAINAGE_STORMWATER",
    )
    req = AuthorizationRequest(
        principal=principal,
        action=CivicAction.SEARCH_DOCKETS,
        resource_id="PWD_ROADS",
        resource_type="CivicDocketSearch",
        resource_department="PWD_ROADS",
    )
    decision = cedar_pdp.authorize(req)
    assert decision.allowed is False
    assert decision.decision == "DENY"


def test_municipal_supervisor_search_own_department_allowed(cedar_pdp: CedarService):
    """Municipal supervisor searching their assigned department is ALLOWED by Policy H."""
    principal = ApplicationPrincipal(
        principal_id="supervisor-water-01",
        role=ApplicationRole.MUNICIPAL_SUPERVISOR,
        department="WATER_SUPPLY",
    )
    req = AuthorizationRequest(
        principal=principal,
        action=CivicAction.SEARCH_DOCKETS,
        resource_id="WATER_SUPPLY",
        resource_type="CivicDocketSearch",
        resource_department="WATER_SUPPLY",
    )
    decision = cedar_pdp.authorize(req)
    assert decision.allowed is True
    assert decision.decision == "ALLOW"


def test_municipal_supervisor_search_other_department_denied(cedar_pdp: CedarService):
    """Municipal supervisor searching another department is DENIED."""
    principal = ApplicationPrincipal(
        principal_id="supervisor-water-01",
        role=ApplicationRole.MUNICIPAL_SUPERVISOR,
        department="WATER_SUPPLY",
    )
    req = AuthorizationRequest(
        principal=principal,
        action=CivicAction.SEARCH_DOCKETS,
        resource_id="HEALTH_SANITATION",
        resource_type="CivicDocketSearch",
        resource_department="HEALTH_SANITATION",
    )
    decision = cedar_pdp.authorize(req)
    assert decision.allowed is False
    assert decision.decision == "DENY"


def test_administrator_search_any_department_allowed(cedar_pdp: CedarService):
    """Administrator searching any department or ALL is ALLOWED by Policy F."""
    principal = ApplicationPrincipal(
        principal_id="admin-master-01",
        role=ApplicationRole.ADMINISTRATOR,
        department=None,
    )
    # Test specific department
    req1 = AuthorizationRequest(
        principal=principal,
        action=CivicAction.SEARCH_DOCKETS,
        resource_id="PWD_ROADS",
        resource_type="CivicDocketSearch",
        resource_department="PWD_ROADS",
    )
    dec1 = cedar_pdp.authorize(req1)
    assert dec1.allowed is True
    assert dec1.decision == "ALLOW"

    # Test ALL
    req2 = AuthorizationRequest(
        principal=principal,
        action=CivicAction.SEARCH_DOCKETS,
        resource_id="ALL",
        resource_type="CivicDocketSearch",
        resource_department="ALL",
    )
    dec2 = cedar_pdp.authorize(req2)
    assert dec2.allowed is True
    assert dec2.decision == "ALLOW"


def test_citizen_search_dockets_denied(cedar_pdp: CedarService):
    """Citizen role attempting search_dockets is strictly DENIED (default deny)."""
    principal = ApplicationPrincipal(
        principal_id="citizen-ravi-01",
        role=ApplicationRole.CITIZEN,
        department=None,
    )
    req = AuthorizationRequest(
        principal=principal,
        action=CivicAction.SEARCH_DOCKETS,
        resource_id="DRAINAGE_STORMWATER",
        resource_type="CivicDocketSearch",
        resource_department="DRAINAGE_STORMWATER",
    )
    decision = cedar_pdp.authorize(req)
    assert decision.allowed is False
    assert decision.decision == "DENY"


def test_public_user_search_dockets_denied(cedar_pdp: CedarService):
    """PublicUser role attempting search_dockets is strictly DENIED (default deny)."""
    principal = ApplicationPrincipal(
        principal_id="public-visitor-01",
        role=ApplicationRole.PUBLIC,
        department=None,
    )
    req = AuthorizationRequest(
        principal=principal,
        action=CivicAction.SEARCH_DOCKETS,
        resource_id="DRAINAGE_STORMWATER",
        resource_type="CivicDocketSearch",
        resource_department="DRAINAGE_STORMWATER",
    )
    decision = cedar_pdp.authorize(req)
    assert decision.allowed is False
    assert decision.decision == "DENY"


def test_missing_resource_department_fails_closed(cedar_pdp: CedarService):
    """Missing or empty department context fails closed."""
    principal = ApplicationPrincipal(
        principal_id="officer-drainage-01",
        role=ApplicationRole.AUTHORITY_OFFICER,
        department="DRAINAGE_STORMWATER",
    )
    req = AuthorizationRequest(
        principal=principal,
        action=CivicAction.SEARCH_DOCKETS,
        resource_id="EMPTY_DEPT",
        resource_type="CivicDocketSearch",
        resource_department=None,
    )
    decision = cedar_pdp.authorize(req)
    assert decision.allowed is False
    assert decision.decision == "DENY"
