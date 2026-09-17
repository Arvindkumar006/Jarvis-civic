"""Comprehensive Authorization Matrix Unit Tests for JARVIS Civic.

Phase 3 Core Tests:
Executes the full 18-point authorization matrix directly against
the local Cedar Policy Decision Point (cedar_service).
"""

import pytest
from unittest.mock import patch

from app.models.security import (
    ApplicationPrincipal,
    ApplicationRole,
    AuthorizationRequest,
    CivicAction,
)
from app.security.cedar_service import cedar_service


@pytest.fixture
def citizen_alice():
    return ApplicationPrincipal(
        principal_id="citizen-alice",
        role=ApplicationRole.CITIZEN,
    )


@pytest.fixture
def citizen_bob():
    return ApplicationPrincipal(
        principal_id="citizen-bob",
        role=ApplicationRole.CITIZEN,
    )


@pytest.fixture
def officer_drainage():
    return ApplicationPrincipal(
        principal_id="officer-chen",
        role=ApplicationRole.AUTHORITY_OFFICER,
        department="DRAINAGE_STORMWATER",
    )


@pytest.fixture
def officer_waste():
    return ApplicationPrincipal(
        principal_id="officer-kumar",
        role=ApplicationRole.AUTHORITY_OFFICER,
        department="WASTE_MANAGEMENT",
    )


@pytest.fixture
def supervisor_drainage():
    return ApplicationPrincipal(
        principal_id="supervisor-sharma",
        role=ApplicationRole.MUNICIPAL_SUPERVISOR,
        department="DRAINAGE_STORMWATER",
    )


@pytest.fixture
def administrator_dan():
    return ApplicationPrincipal(
        principal_id="admin-dan",
        role=ApplicationRole.ADMINISTRATOR,
    )


@pytest.fixture
def public_user():
    return ApplicationPrincipal(
        principal_id="anon-user-01",
        role=ApplicationRole.PUBLIC,
    )


# ==============================================================================
# 18-Point Test Matrix
# ==============================================================================

def test_1_citizen_creates_case_allowed(citizen_alice):
    """TEST 1: Citizen creates a case -> ALLOW"""
    req = AuthorizationRequest(
        principal=citizen_alice,
        action=CivicAction.CREATE_CASE,
        resource_id="new_case_01",
        resource_type="CivicCase",
        resource_owner=citizen_alice.principal_id,
        resource_department="DRAINAGE_STORMWATER",
    )
    decision = cedar_service.authorize(req)
    assert decision.allowed is True
    assert decision.decision == "ALLOW"


def test_2_citizen_reads_own_case_allowed(citizen_alice):
    """TEST 2: Citizen reads own case -> ALLOW"""
    req = AuthorizationRequest(
        principal=citizen_alice,
        action=CivicAction.READ_OWN_CASE,
        resource_id="case_alice_01",
        resource_type="CivicCase",
        resource_owner=citizen_alice.principal_id,
        resource_department="DRAINAGE_STORMWATER",
    )
    decision = cedar_service.authorize(req)
    assert decision.allowed is True
    assert decision.decision == "ALLOW"


def test_3_citizen_reads_another_citizens_case_denied(citizen_bob, citizen_alice):
    """TEST 3: Citizen reads another citizen's case -> DENY"""
    req = AuthorizationRequest(
        principal=citizen_bob,
        action=CivicAction.READ_OWN_CASE,
        resource_id="case_alice_01",
        resource_type="CivicCase",
        resource_owner=citizen_alice.principal_id,  # Owned by Alice, Bob is asking
        resource_department="DRAINAGE_STORMWATER",
    )
    decision = cedar_service.authorize(req)
    assert decision.allowed is False
    assert decision.decision == "DENY"


def test_4_citizen_modifies_own_permitted_case_data_allowed(citizen_alice):
    """TEST 4: Citizen modifies own permitted case data -> ALLOW"""
    req = AuthorizationRequest(
        principal=citizen_alice,
        action=CivicAction.UPDATE_OWN_CASE,
        resource_id="case_alice_01",
        resource_type="CivicCase",
        resource_owner=citizen_alice.principal_id,
        resource_department="DRAINAGE_STORMWATER",
    )
    decision = cedar_service.authorize(req)
    assert decision.allowed is True
    assert decision.decision == "ALLOW"


def test_5_citizen_attempts_authority_status_update_denied(citizen_alice):
    """TEST 5: Citizen attempts authority status update -> DENY"""
    req = AuthorizationRequest(
        principal=citizen_alice,
        action=CivicAction.UPDATE_CASE_STATUS,
        resource_id="case_alice_01",
        resource_type="CivicCase",
        resource_owner=citizen_alice.principal_id,
        resource_department="DRAINAGE_STORMWATER",
    )
    decision = cedar_service.authorize(req)
    assert decision.allowed is False
    assert decision.decision == "DENY"


def test_6_authority_officer_reads_permitted_authority_case_allowed(officer_drainage, citizen_alice):
    """TEST 6: AuthorityOfficer reads permitted authority case -> ALLOW"""
    req = AuthorizationRequest(
        principal=officer_drainage,
        action=CivicAction.READ_AUTHORITY_CASE,
        resource_id="case_alice_01",
        resource_type="CivicCase",
        resource_owner=citizen_alice.principal_id,
        resource_department="DRAINAGE_STORMWATER",  # Matches officer department
    )
    decision = cedar_service.authorize(req)
    assert decision.allowed is True
    assert decision.decision == "ALLOW"


def test_7_authority_officer_accesses_case_outside_scope_denied(officer_waste, citizen_alice):
    """TEST 7: AuthorityOfficer accesses case outside permitted scope -> DENY"""
    req = AuthorizationRequest(
        principal=officer_waste,  # WASTE_MANAGEMENT officer
        action=CivicAction.READ_AUTHORITY_CASE,
        resource_id="case_alice_01",
        resource_type="CivicCase",
        resource_owner=citizen_alice.principal_id,
        resource_department="DRAINAGE_STORMWATER",  # DRAINAGE case (mismatch)
    )
    decision = cedar_service.authorize(req)
    assert decision.allowed is False
    assert decision.decision == "DENY"


def test_8_authority_officer_updates_case_status_within_scope_allowed(officer_drainage, citizen_alice):
    """TEST 8: AuthorityOfficer updates case status within scope -> ALLOW"""
    req = AuthorizationRequest(
        principal=officer_drainage,
        action=CivicAction.UPDATE_CASE_STATUS,
        resource_id="case_alice_01",
        resource_type="CivicCase",
        resource_owner=citizen_alice.principal_id,
        resource_department="DRAINAGE_STORMWATER",
    )
    decision = cedar_service.authorize(req)
    assert decision.allowed is True
    assert decision.decision == "ALLOW"


def test_9_citizen_attempts_update_case_status_denied(citizen_bob):
    """TEST 9: Citizen attempts update_case_status -> DENY"""
    req = AuthorizationRequest(
        principal=citizen_bob,
        action=CivicAction.UPDATE_CASE_STATUS,
        resource_id="case_bob_01",
        resource_type="CivicCase",
        resource_owner=citizen_bob.principal_id,
        resource_department="ROAD_POTHOLE",
    )
    decision = cedar_service.authorize(req)
    assert decision.allowed is False
    assert decision.decision == "DENY"


def test_10_municipal_supervisor_reads_permitted_case_allowed(supervisor_drainage, citizen_alice):
    """TEST 10: MunicipalSupervisor reads permitted authority case -> ALLOW"""
    req = AuthorizationRequest(
        principal=supervisor_drainage,
        action=CivicAction.READ_AUTHORITY_CASE,
        resource_id="case_alice_01",
        resource_type="CivicCase",
        resource_owner=citizen_alice.principal_id,
        resource_department="DRAINAGE_STORMWATER",
    )
    decision = cedar_service.authorize(req)
    assert decision.allowed is True
    assert decision.decision == "ALLOW"


def test_11_municipal_supervisor_updates_permitted_status_allowed(supervisor_drainage, citizen_alice):
    """TEST 11: MunicipalSupervisor updates permitted status -> ALLOW"""
    req = AuthorizationRequest(
        principal=supervisor_drainage,
        action=CivicAction.UPDATE_CASE_STATUS,
        resource_id="case_alice_01",
        resource_type="CivicCase",
        resource_owner=citizen_alice.principal_id,
        resource_department="DRAINAGE_STORMWATER",
    )
    decision = cedar_service.authorize(req)
    assert decision.allowed is True
    assert decision.decision == "ALLOW"


def test_12_administrator_reads_audit_log_allowed(administrator_dan):
    """TEST 12: Administrator reads audit log -> ALLOW"""
    req = AuthorizationRequest(
        principal=administrator_dan,
        action=CivicAction.READ_AUDIT_LOG,
        resource_id="audit_records_all",
        resource_type="AuditRecord",
        resource_department="ALL",
    )
    decision = cedar_service.authorize(req)
    assert decision.allowed is True
    assert decision.decision == "ALLOW"


def test_13_citizen_reads_protected_audit_log_denied(citizen_alice):
    """TEST 13: Citizen reads protected audit log -> DENY"""
    req = AuthorizationRequest(
        principal=citizen_alice,
        action=CivicAction.READ_AUDIT_LOG,
        resource_id="audit_records_all",
        resource_type="AuditRecord",
        resource_department="DRAINAGE_STORMWATER",
    )
    decision = cedar_service.authorize(req)
    assert decision.allowed is False
    assert decision.decision == "DENY"


def test_14_public_tracking_request_allowed(public_user, citizen_alice):
    """TEST 14: Public tracking request on public case -> ALLOW"""
    req = AuthorizationRequest(
        principal=public_user,
        action=CivicAction.READ_PUBLIC_TRACKING,
        resource_id="case_alice_01",
        resource_type="CivicCase",
        resource_owner=citizen_alice.principal_id,
        resource_department="DRAINAGE_STORMWATER",
        is_public=True,
    )
    decision = cedar_service.authorize(req)
    assert decision.allowed is True
    assert decision.decision == "ALLOW"


def test_15_cedar_evaluation_failure_fails_closed(citizen_alice):
    """TEST 15: Cedar/policy evaluation failure -> DENY (Fail Closed)"""
    with patch("cedarpy.is_authorized", side_effect=RuntimeError("Engine fatal error")):
        req = AuthorizationRequest(
            principal=citizen_alice,
            action=CivicAction.READ_OWN_CASE,
            resource_id="case_alice_01",
            resource_type="CivicCase",
            resource_owner=citizen_alice.principal_id,
        )
        decision = cedar_service.authorize(req)
        assert decision.allowed is False
        assert decision.decision == "DENY"
        assert "fail-closed" in decision.reason.lower() or "failed" in decision.reason.lower()


def test_16_unknown_action_denied(citizen_alice):
    """TEST 16: Unknown action -> DENY"""
    # Passing an arbitrary unknown action string
    req = AuthorizationRequest(
        principal=citizen_alice,
        action="delete_case_records",  # Unknown action not in policy
        resource_id="case_alice_01",
        resource_type="CivicCase",
        resource_owner=citizen_alice.principal_id,
    )
    decision = cedar_service.authorize(req)
    assert decision.allowed is False
    assert decision.decision == "DENY"


def test_17_unknown_role_denied():
    """TEST 17: Unknown role -> DENY"""
    unknown_principal = ApplicationPrincipal(
        principal_id="suspicious-user",
        role=ApplicationRole.PUBLIC,  # Resolved safely as public
    )
    req = AuthorizationRequest(
        principal=unknown_principal,
        action=CivicAction.UPDATE_CASE_STATUS,
        resource_id="case_123",
        resource_type="CivicCase",
    )
    decision = cedar_service.authorize(req)
    assert decision.allowed is False
    assert decision.decision == "DENY"


def test_18_cross_citizen_access_attempt_denied(citizen_alice, citizen_bob):
    """TEST 18: Cross-citizen access attempt (Alice -> Bob case) -> DENY"""
    req = AuthorizationRequest(
        principal=citizen_alice,
        action=CivicAction.READ_OWN_CASE,
        resource_id="case_bob_99",
        resource_type="CivicCase",
        resource_owner=citizen_bob.principal_id,
    )
    decision = cedar_service.authorize(req)
    assert decision.allowed is False
    assert decision.decision == "DENY"
