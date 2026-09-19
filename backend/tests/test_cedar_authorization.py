"""Phase 8.3 Focused Cedar Authorization Unit Tests.

Validates the 20 canonical authorization invariants specified in Phase 8.3:
1. Citizen allowed permitted own-case action.
2. Citizen denied authority workflow.
3. Citizen denied another citizen's private case.
4. Authority officer allowed within own department.
5. Authority officer denied different department.
6. Roads officer allowed PWD_ROADS.
7. Roads officer denied DRAINAGE_STORMWATER.
8. Drainage officer allowed DRAINAGE_STORMWATER.
9. Drainage officer denied PWD_ROADS.
10. Supervisor policy.
11. Administrator intended actions.
12. Public denied internal authority action.
13. Public tracking safe.
14. Invalid role denied.
15. Missing principal denied.
16. Missing required department denied.
17. Missing resource department safe.
18. Invalid Cedar request denied.
19. Cedar engine unavailable denied.
20. Policy loading failure denied.
"""

from unittest.mock import MagicMock, patch
import pytest

from app.models.security import (
    ApplicationPrincipal,
    ApplicationRole,
    AuthorizationRequest,
    CivicAction,
)
from app.security.authorization_service import authorization_service
from app.security.cedar_service import CedarService, cedar_service


# ---------------------------------------------------------------------------
# Test Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def citizen_ananya():
    return ApplicationPrincipal(
        principal_id="cit-user-1",
        role=ApplicationRole.CITIZEN,
    )


@pytest.fixture
def citizen_bob():
    return ApplicationPrincipal(
        principal_id="cit-user-2",
        role=ApplicationRole.CITIZEN,
    )


@pytest.fixture
def officer_drainage():
    return ApplicationPrincipal(
        principal_id="officer-drainage-1",
        role=ApplicationRole.AUTHORITY_OFFICER,
        department="DRAINAGE_STORMWATER",
    )


@pytest.fixture
def officer_roads():
    return ApplicationPrincipal(
        principal_id="officer-roads-1",
        role=ApplicationRole.AUTHORITY_OFFICER,
        department="PWD_ROADS",
    )


@pytest.fixture
def supervisor_drainage():
    return ApplicationPrincipal(
        principal_id="supervisor-01",
        role=ApplicationRole.MUNICIPAL_SUPERVISOR,
        department="DRAINAGE_STORMWATER",
    )


@pytest.fixture
def administrator_sundaram():
    return ApplicationPrincipal(
        principal_id="admin-01",
        role=ApplicationRole.ADMINISTRATOR,
    )


@pytest.fixture
def public_user():
    return ApplicationPrincipal(
        principal_id="public-user-1",
        role=ApplicationRole.PUBLIC,
    )


# ---------------------------------------------------------------------------
# 20 Mandatory Cedar Unit Tests
# ---------------------------------------------------------------------------

def test_01_citizen_allowed_permitted_own_case_action(citizen_ananya):
    """1. Citizen allowed to perform permitted own-case actions (create, read, update, add evidence)."""
    # Create case
    decision_create = authorization_service.authorize(
        principal=citizen_ananya,
        action=CivicAction.CREATE_CASE,
        resource_id="new-case-1",
        resource_owner=citizen_ananya.principal_id,
        resource_department="DRAINAGE_STORMWATER",
    )
    assert decision_create.allowed is True
    assert decision_create.decision == "ALLOW"

    # Read own case
    decision_read = authorization_service.authorize(
        principal=citizen_ananya,
        action=CivicAction.READ_OWN_CASE,
        resource_id="case-100",
        resource_owner=citizen_ananya.principal_id,
        resource_department="DRAINAGE_STORMWATER",
    )
    assert decision_read.allowed is True
    assert decision_read.decision == "ALLOW"

    # Update own case
    decision_update = authorization_service.authorize(
        principal=citizen_ananya,
        action=CivicAction.UPDATE_OWN_CASE,
        resource_id="case-100",
        resource_owner=citizen_ananya.principal_id,
        resource_department="DRAINAGE_STORMWATER",
    )
    assert decision_update.allowed is True
    assert decision_update.decision == "ALLOW"

    # Add evidence
    decision_evidence = authorization_service.authorize(
        principal=citizen_ananya,
        action=CivicAction.ADD_EVIDENCE,
        resource_id="case-100",
        resource_owner=citizen_ananya.principal_id,
        resource_department="DRAINAGE_STORMWATER",
    )
    assert decision_evidence.allowed is True
    assert decision_evidence.decision == "ALLOW"


def test_02_citizen_denied_authority_workflow(citizen_ananya):
    """2. Citizen denied authority workflow actions (update status, resolution note, read authority case)."""
    # Update case status
    decision_status = authorization_service.authorize(
        principal=citizen_ananya,
        action=CivicAction.UPDATE_CASE_STATUS,
        resource_id="case-100",
        resource_owner=citizen_ananya.principal_id,
        resource_department="DRAINAGE_STORMWATER",
    )
    assert decision_status.allowed is False
    assert decision_status.decision == "DENY"

    # Add resolution note
    decision_note = authorization_service.authorize(
        principal=citizen_ananya,
        action=CivicAction.ADD_RESOLUTION_NOTE,
        resource_id="case-100",
        resource_owner=citizen_ananya.principal_id,
        resource_department="DRAINAGE_STORMWATER",
    )
    assert decision_note.allowed is False
    assert decision_note.decision == "DENY"

    # Read authority case
    decision_auth_read = authorization_service.authorize(
        principal=citizen_ananya,
        action=CivicAction.READ_AUTHORITY_CASE,
        resource_id="case-100",
        resource_owner=citizen_ananya.principal_id,
        resource_department="DRAINAGE_STORMWATER",
    )
    assert decision_auth_read.allowed is False
    assert decision_auth_read.decision == "DENY"


def test_03_citizen_denied_another_citizens_private_case(citizen_ananya, citizen_bob):
    """3. Citizen denied another citizen's private case."""
    # Ananya tries to read Bob's case
    decision = authorization_service.authorize(
        principal=citizen_ananya,
        action=CivicAction.READ_OWN_CASE,
        resource_id="bob-case-001",
        resource_owner=citizen_bob.principal_id,
        resource_department="DRAINAGE_STORMWATER",
    )
    assert decision.allowed is False
    assert decision.decision == "DENY"

    # Ananya tries to update Bob's case
    decision_up = authorization_service.authorize(
        principal=citizen_ananya,
        action=CivicAction.UPDATE_OWN_CASE,
        resource_id="bob-case-001",
        resource_owner=citizen_bob.principal_id,
        resource_department="DRAINAGE_STORMWATER",
    )
    assert decision_up.allowed is False
    assert decision_up.decision == "DENY"


def test_04_authority_officer_allowed_within_own_department(officer_drainage):
    """4. Authority officer allowed within own department."""
    decision = authorization_service.authorize(
        principal=officer_drainage,
        action=CivicAction.READ_AUTHORITY_CASE,
        resource_id="drain-case-01",
        resource_owner="citizen-99",
        resource_department="DRAINAGE_STORMWATER",
    )
    assert decision.allowed is True
    assert decision.decision == "ALLOW"

    decision_status = authorization_service.authorize(
        principal=officer_drainage,
        action=CivicAction.UPDATE_CASE_STATUS,
        resource_id="drain-case-01",
        resource_owner="citizen-99",
        resource_department="DRAINAGE_STORMWATER",
    )
    assert decision_status.allowed is True
    assert decision_status.decision == "ALLOW"


def test_05_authority_officer_denied_different_department(officer_drainage):
    """5. Authority officer denied different department (e.g. Drainage officer accessing WASTE_MANAGEMENT)."""
    decision = authorization_service.authorize(
        principal=officer_drainage,
        action=CivicAction.READ_AUTHORITY_CASE,
        resource_id="waste-case-01",
        resource_owner="citizen-99",
        resource_department="WASTE_MANAGEMENT",
    )
    assert decision.allowed is False
    assert decision.decision == "DENY"


def test_06_roads_officer_allowed_pwd_roads(officer_roads):
    """6. Roads officer allowed for PWD_ROADS case."""
    decision = authorization_service.authorize(
        principal=officer_roads,
        action=CivicAction.UPDATE_CASE_STATUS,
        resource_id="pothole-case-77",
        resource_owner="citizen-12",
        resource_department="PWD_ROADS",
    )
    assert decision.allowed is True
    assert decision.decision == "ALLOW"


def test_07_roads_officer_denied_drainage_stormwater(officer_roads):
    """7. Roads officer denied DRAINAGE_STORMWATER case."""
    decision = authorization_service.authorize(
        principal=officer_roads,
        action=CivicAction.UPDATE_CASE_STATUS,
        resource_id="flood-case-88",
        resource_owner="citizen-12",
        resource_department="DRAINAGE_STORMWATER",
    )
    assert decision.allowed is False
    assert decision.decision == "DENY"


def test_08_drainage_officer_allowed_drainage_stormwater(officer_drainage):
    """8. Drainage officer allowed for DRAINAGE_STORMWATER case."""
    decision = authorization_service.authorize(
        principal=officer_drainage,
        action=CivicAction.UPDATE_CASE_STATUS,
        resource_id="flood-case-88",
        resource_owner="citizen-12",
        resource_department="DRAINAGE_STORMWATER",
    )
    assert decision.allowed is True
    assert decision.decision == "ALLOW"


def test_09_drainage_officer_denied_pwd_roads(officer_drainage):
    """9. Drainage officer denied PWD_ROADS case."""
    decision = authorization_service.authorize(
        principal=officer_drainage,
        action=CivicAction.UPDATE_CASE_STATUS,
        resource_id="pothole-case-77",
        resource_owner="citizen-12",
        resource_department="PWD_ROADS",
    )
    assert decision.allowed is False
    assert decision.decision == "DENY"


def test_10_supervisor_policy(supervisor_drainage):
    """10. Supervisor policy: allowed within assigned department, denied outside department."""
    # Within department: allowed for case workflow and audit log
    dec_case = authorization_service.authorize(
        principal=supervisor_drainage,
        action=CivicAction.READ_AUTHORITY_CASE,
        resource_id="flood-case-88",
        resource_department="DRAINAGE_STORMWATER",
    )
    assert dec_case.allowed is True
    assert dec_case.decision == "ALLOW"

    dec_audit = authorization_service.authorize(
        principal=supervisor_drainage,
        action=CivicAction.READ_AUDIT_LOG,
        resource_id="audit-drainage-01",
        resource_type="AuditRecord",
        resource_department="DRAINAGE_STORMWATER",
    )
    assert dec_audit.allowed is True
    assert dec_audit.decision == "ALLOW"

    # Outside department: strictly denied
    dec_wrong_case = authorization_service.authorize(
        principal=supervisor_drainage,
        action=CivicAction.READ_AUTHORITY_CASE,
        resource_id="roads-case-01",
        resource_department="PWD_ROADS",
    )
    assert dec_wrong_case.allowed is False
    assert dec_wrong_case.decision == "DENY"

    dec_wrong_audit = authorization_service.authorize(
        principal=supervisor_drainage,
        action=CivicAction.READ_AUDIT_LOG,
        resource_id="audit-roads-01",
        resource_type="AuditRecord",
        resource_department="PWD_ROADS",
    )
    assert dec_wrong_audit.allowed is False
    assert dec_wrong_audit.decision == "DENY"


def test_11_administrator_intended_actions(administrator_sundaram):
    """11. Administrator allowed only intended administrator actions defined in schema."""
    # Permitted defined operations
    dec_status = authorization_service.authorize(
        principal=administrator_sundaram,
        action=CivicAction.UPDATE_CASE_STATUS,
        resource_id="any-case-01",
        resource_department="DRAINAGE_STORMWATER",
    )
    assert dec_status.allowed is True

    dec_audit = authorization_service.authorize(
        principal=administrator_sundaram,
        action=CivicAction.READ_AUDIT_LOG,
        resource_id="audit-system",
        resource_type="AuditRecord",
        resource_department="PWD_ROADS",
    )
    assert dec_audit.allowed is True

    # Undefined/arbitrary action not in schema fails closed
    dec_unknown_action = authorization_service.authorize(
        principal=administrator_sundaram,
        action="delete_system_database",
        resource_id="db-root",
        resource_type="CivicCase",
    )
    assert dec_unknown_action.allowed is False
    assert dec_unknown_action.decision == "DENY"


def test_12_public_denied_internal_authority_action(public_user):
    """12. Public denied internal authority actions and private records."""
    # Denied case status update
    dec_status = authorization_service.authorize(
        principal=public_user,
        action=CivicAction.UPDATE_CASE_STATUS,
        resource_id="case-100",
        resource_department="DRAINAGE_STORMWATER",
    )
    assert dec_status.allowed is False
    assert dec_status.decision == "DENY"

    # Denied read authority case
    dec_auth = authorization_service.authorize(
        principal=public_user,
        action=CivicAction.READ_AUTHORITY_CASE,
        resource_id="case-100",
        resource_department="DRAINAGE_STORMWATER",
    )
    assert dec_auth.allowed is False
    assert dec_auth.decision == "DENY"

    # Denied audit log
    dec_audit = authorization_service.authorize(
        principal=public_user,
        action=CivicAction.READ_AUDIT_LOG,
        resource_id="audit-100",
        resource_type="AuditRecord",
    )
    assert dec_audit.allowed is False
    assert dec_audit.decision == "DENY"


def test_13_public_tracking_safe(public_user, citizen_ananya):
    """13. Public tracking safe: allowed when is_public is True, denied when is_public is False."""
    # Public tracking permitted when is_public == True
    dec_public_yes = authorization_service.authorize(
        principal=public_user,
        action=CivicAction.READ_PUBLIC_TRACKING,
        resource_id="case-pub-1",
        resource_department="DRAINAGE_STORMWATER",
        is_public=True,
    )
    assert dec_public_yes.allowed is True
    assert dec_public_yes.decision == "ALLOW"

    # Public tracking denied when is_public == False (private case)
    dec_public_no = authorization_service.authorize(
        principal=public_user,
        action=CivicAction.READ_PUBLIC_TRACKING,
        resource_id="case-priv-1",
        resource_department="DRAINAGE_STORMWATER",
        is_public=False,
    )
    assert dec_public_no.allowed is False
    assert dec_public_no.decision == "DENY"


def test_14_invalid_role_denied():
    """14. Unknown/invalid role denied (fails closed)."""
    fake_principal = MagicMock()
    fake_principal.principal_id = "hacker-1"
    fake_principal.role = "SUPER_ROOT_GOD_MODE"
    fake_principal.department = "DRAINAGE_STORMWATER"

    dec = authorization_service.authorize(
        principal=fake_principal,
        action=CivicAction.UPDATE_CASE_STATUS,
        resource_id="case-1",
        resource_department="DRAINAGE_STORMWATER",
    )
    assert dec.allowed is False
    assert dec.decision == "DENY"
    assert "Unknown or invalid principal role" in dec.reason


def test_15_missing_principal_denied():
    """15. Missing principal denied (fails closed)."""
    dec = authorization_service.authorize(
        principal=None,
        action=CivicAction.CREATE_CASE,
        resource_id="case-1",
    )
    assert dec.allowed is False
    assert dec.decision == "DENY"
    assert "Missing or invalid principal" in dec.reason


def test_16_missing_required_department_denied():
    """16. Missing department denied where department is required for authority officer."""
    officer_no_dept = ApplicationPrincipal(
        principal_id="officer-nodept",
        role=ApplicationRole.AUTHORITY_OFFICER,
        department=None,
    )
    dec = authorization_service.authorize(
        principal=officer_no_dept,
        action=CivicAction.UPDATE_CASE_STATUS,
        resource_id="drain-case-1",
        resource_department="DRAINAGE_STORMWATER",
    )
    assert dec.allowed is False
    assert dec.decision == "DENY"


def test_17_missing_resource_department_safe(officer_drainage):
    """17. Resource with missing department handled safely (cannot match officer department)."""
    dec = authorization_service.authorize(
        principal=officer_drainage,
        action=CivicAction.UPDATE_CASE_STATUS,
        resource_id="case-no-dept",
        resource_department=None,
    )
    assert dec.allowed is False
    assert dec.decision == "DENY"


def test_18_invalid_cedar_request_denied(officer_drainage):
    """18. Invalid Cedar request fails closed (e.g. unknown resource type)."""
    dec = authorization_service.authorize(
        principal=officer_drainage,
        action=CivicAction.UPDATE_CASE_STATUS,
        resource_id="res-1",
        resource_type="NonExistentResourceType",
    )
    assert dec.allowed is False
    assert dec.decision == "DENY"
    assert "fail-closed" in dec.reason.lower()


def test_19_cedar_engine_unavailable_denied(officer_drainage):
    """19. Cedar engine unavailable fails closed."""
    mock_pdp = MagicMock()
    mock_pdp.is_healthy.return_value = False

    service = authorization_service.__class__(cedar_pdp=mock_pdp)
    dec = service.authorize(
        principal=officer_drainage,
        action=CivicAction.UPDATE_CASE_STATUS,
        resource_id="case-1",
        resource_department="DRAINAGE_STORMWATER",
    )
    assert dec.allowed is False
    assert dec.decision == "DENY"
    assert "unavailable" in dec.reason.lower()


def test_20_policy_loading_failure_denied(officer_drainage):
    """20. Policy loading failure does not result in implicit allow."""
    # Simulate failed policy compilation
    broken_pdp = CedarService.__new__(CedarService)
    broken_pdp._initialized = False
    broken_pdp.schema_str = ""
    broken_pdp.policies_str = ""

    service = authorization_service.__class__(cedar_pdp=broken_pdp)
    dec = service.authorize(
        principal=officer_drainage,
        action=CivicAction.UPDATE_CASE_STATUS,
        resource_id="case-1",
        resource_department="DRAINAGE_STORMWATER",
    )
    assert dec.allowed is False
    assert dec.decision == "DENY"
    assert "unavailable" in dec.reason.lower() or "uninitialized" in dec.reason.lower()
