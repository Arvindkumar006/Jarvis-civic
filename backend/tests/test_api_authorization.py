"""Phase 8.3 Real API Authorization and Identity Manipulation Tests.

Validates the runtime authorization invariants specified in Phase 8.3:
1. 401 Unauthorized: missing session on protected auth endpoint or invalid/expired session cookie.
2. 403 Forbidden: authenticated citizen attempting authority action, officer accessing wrong department, public attempting internal operation.
3. 200/201 Success: authenticated principals performing allowed actions.
4. Department Isolation: Drainage Officer vs Roads case, Roads Officer vs Drainage case.
5. Identity Manipulation / Spoofing:
   - Authenticated citizen + X-Simulated-Role: ADMINISTRATOR -> No privilege escalation.
   - Authenticated drainage officer + X-Simulated-Role: ADMINISTRATOR + department: PWD_ROADS -> evaluated as drainage officer.
   - Request body overrides cannot bypass server department evaluation.
6. Runtime Cedar Decision Path Proof:
   - Proves HTTP Request -> authenticated session -> AuthenticatedPrincipal -> AuthorizationService -> cedarpy.is_authorized -> Decision -> Operation.
"""

from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient

import cedarpy
from app.main import app
from app.models.account import UserAccount
from app.models.enums import CaseStatus, ControlledDepartment
from app.models.security import ApplicationRole
from app.security.hasher import password_hasher
from app.security.session import session_store
from app.services.case_store import case_store
from app.services.persistence.account_repository import account_repository

client = TestClient(app)


# ---------------------------------------------------------------------------
# Test Fixtures & Account Setup
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def clean_system():
    """Ensure clean case store and session store before each test."""
    case_store.clear()
    session_store.clear()
    yield
    case_store.clear()
    session_store.clear()


@pytest.fixture
def auth_sessions():
    """Create real authenticated sessions for testing."""
    # 1. Citizen Ananya
    cit_acc = account_repository.get_by_email("citizen@jarviscivic.local")
    if not cit_acc:
        cit_acc = UserAccount(
            principal_id="cit-user-1",
            email="citizen@jarviscivic.local",
            password_hash=password_hasher.hash_password("JarvisCivic2026!"),
            display_name="Ananya Sharma",
            role=ApplicationRole.CITIZEN,
            department=None,
        )
        account_repository.save(cit_acc)
    cit_sess = session_store.create_session(cit_acc)

    # 2. Drainage Officer
    drainage_acc = account_repository.get_by_email("officer@jarviscivic.local")
    if not drainage_acc:
        drainage_acc = UserAccount(
            principal_id="officer-drainage-1",
            email="officer@jarviscivic.local",
            password_hash=password_hasher.hash_password("JarvisCivic2026!"),
            display_name="Officer Rajesh Kumar",
            role=ApplicationRole.AUTHORITY_OFFICER,
            department=ControlledDepartment.DRAINAGE_STORMWATER.value,
        )
        account_repository.save(drainage_acc)
    drainage_sess = session_store.create_session(drainage_acc)

    # 3. Roads Officer
    roads_acc = account_repository.get_by_email("roads.officer@jarviscivic.local")
    if not roads_acc:
        roads_acc = UserAccount(
            principal_id="officer-roads-1",
            email="roads.officer@jarviscivic.local",
            password_hash=password_hasher.hash_password("JarvisCivic2026!"),
            display_name="Officer Suresh Prabhu",
            role=ApplicationRole.AUTHORITY_OFFICER,
            department=ControlledDepartment.PWD_ROADS.value,
        )
        account_repository.save(roads_acc)
    roads_sess = session_store.create_session(roads_acc)

    # 4. Supervisor
    sup_acc = account_repository.get_by_email("supervisor@jarviscivic.local")
    if not sup_acc:
        sup_acc = UserAccount(
            principal_id="supervisor-01",
            email="supervisor@jarviscivic.local",
            password_hash=password_hasher.hash_password("JarvisCivic2026!"),
            display_name="Chief Supervisor Mehta",
            role=ApplicationRole.MUNICIPAL_SUPERVISOR,
            department=ControlledDepartment.DRAINAGE_STORMWATER.value,
        )
        account_repository.save(sup_acc)
    sup_sess = session_store.create_session(sup_acc)

    # 5. Public Account
    pub_acc = account_repository.get_by_email("public@jarviscivic.local")
    if not pub_acc:
        pub_acc = UserAccount(
            principal_id="public-user-1",
            email="public@jarviscivic.local",
            password_hash=password_hasher.hash_password("JarvisCivic2026!"),
            display_name="Public Observer",
            role=ApplicationRole.PUBLIC,
            department=None,
        )
        account_repository.save(pub_acc)
    pub_sess = session_store.create_session(pub_acc)

    return {
        "citizen": cit_sess,
        "drainage_officer": drainage_sess,
        "roads_officer": roads_sess,
        "supervisor": sup_sess,
        "public": pub_sess,
    }


def _seed_case(department: str = "DRAINAGE_STORMWATER", owner_id: str = "cit-user-1") -> str:
    """Helper to seed a case directly in case_store."""
    from app.models.security import CivicCaseCreateRequest
    req = CivicCaseCreateRequest(
        description="Drainage overflow blocking road access",
        location="Anna Salai Junction",
        department=ControlledDepartment(department),
        is_public=True,
    )
    record = case_store.create_case(req, owner_id=owner_id)
    return record.case_id


# ---------------------------------------------------------------------------
# 1. Authentication Semantics (401 vs 403)
# ---------------------------------------------------------------------------

def test_api_401_no_session_on_protected_auth_endpoint():
    """GET /api/auth/me without session cookie returns HTTP 401 Unauthorized."""
    res = client.get("/api/auth/me")
    assert res.status_code == 401
    assert "Not authenticated" in res.json()["detail"] or "log in" in res.json()["detail"]


def test_api_401_invalid_or_expired_session_cookie():
    """Request with invalid or expired jarvis_session_id cookie returns HTTP 401 Unauthorized."""
    # Attempt on cases endpoint with bogus session cookie
    cookies = {"jarvis_session_id": "bogus-expired-session-id-12345"}
    res = client.get("/api/cases/case-001", cookies=cookies)
    assert res.status_code == 401
    assert "expired or is invalid" in res.json()["detail"].lower()


def test_api_403_citizen_attempting_authority_status_update(auth_sessions):
    """Authenticated Citizen attempting PATCH /api/cases/{case_id}/status returns HTTP 403 Forbidden."""
    case_id = _seed_case(department="DRAINAGE_STORMWATER", owner_id="cit-user-1")
    cit_cookie = {"jarvis_session_id": auth_sessions["citizen"].session_id}

    # Citizen tries to advance status to ROUTING_PREPARED
    res = client.patch(
        f"/api/cases/{case_id}/status",
        json={"status": "ROUTING_PREPARED", "note": "Citizen trying to change status"},
        cookies=cit_cookie,
    )
    assert res.status_code == 403
    assert res.json() == {"detail": "Authorization denied"}


def test_api_403_public_account_attempting_internal_operation(auth_sessions):
    """Authenticated PUBLIC user attempting to read another citizen's case or status update returns 403."""
    case_id = _seed_case(department="DRAINAGE_STORMWATER", owner_id="cit-user-1")
    pub_cookie = {"jarvis_session_id": auth_sessions["public"].session_id}

    # Public user attempts to read private case
    res = client.get(f"/api/cases/{case_id}", cookies=pub_cookie)
    assert res.status_code == 403
    assert res.json() == {"detail": "Authorization denied"}

    # Public user attempts to inspect audit logs
    res_audit = client.get("/api/audit/logs", cookies=pub_cookie)
    assert res_audit.status_code == 403
    assert res_audit.json() == {"detail": "Authorization denied"}


# ---------------------------------------------------------------------------
# 2. Department Jurisdiction Tests (Drainage vs Roads)
# ---------------------------------------------------------------------------

def test_api_drainage_officer_allowed_drainage_denied_roads(auth_sessions):
    """Drainage officer ALLOWED on DRAINAGE case, strictly DENIED (403) on ROADS case."""
    drainage_case_id = _seed_case(department="DRAINAGE_STORMWATER")
    roads_case_id = _seed_case(department="PWD_ROADS")

    drainage_cookie = {"jarvis_session_id": auth_sessions["drainage_officer"].session_id}

    # 1. Drainage officer on DRAINAGE case -> ALLOW (200 OK)
    res_allow = client.patch(
        f"/api/cases/{drainage_case_id}/status",
        json={"status": "ROUTING_PREPARED", "note": "Drainage team assigned"},
        cookies=drainage_cookie,
    )
    assert res_allow.status_code == 200
    assert res_allow.json()["status"] == "ROUTING_PREPARED"

    # 2. Drainage officer on ROADS case -> DENY (403 Forbidden)
    res_deny = client.patch(
        f"/api/cases/{roads_case_id}/status",
        json={"status": "ROUTING_PREPARED", "note": "Drainage officer trying roads case"},
        cookies=drainage_cookie,
    )
    assert res_deny.status_code == 403
    assert res_deny.json() == {"detail": "Authorization denied"}


def test_api_roads_officer_allowed_roads_denied_drainage(auth_sessions):
    """Roads officer ALLOWED on ROADS case, strictly DENIED (403) on DRAINAGE case."""
    drainage_case_id = _seed_case(department="DRAINAGE_STORMWATER")
    roads_case_id = _seed_case(department="PWD_ROADS")

    roads_cookie = {"jarvis_session_id": auth_sessions["roads_officer"].session_id}

    # 1. Roads officer on ROADS case -> ALLOW (200 OK)
    res_allow = client.patch(
        f"/api/cases/{roads_case_id}/status",
        json={"status": "ROUTING_PREPARED", "note": "Roads inspection underway"},
        cookies=roads_cookie,
    )
    assert res_allow.status_code == 200
    assert res_allow.json()["status"] == "ROUTING_PREPARED"

    # 2. Roads officer on DRAINAGE case -> DENY (403 Forbidden)
    res_deny = client.patch(
        f"/api/cases/{drainage_case_id}/status",
        json={"status": "ROUTING_PREPARED", "note": "Roads officer trying drainage case"},
        cookies=roads_cookie,
    )
    assert res_deny.status_code == 403
    assert res_deny.json() == {"detail": "Authorization denied"}


# ---------------------------------------------------------------------------
# 3. Identity Manipulation & Anti-Spoofing Tests (Section 27)
# ---------------------------------------------------------------------------

def test_api_attack_authenticated_citizen_spoofing_admin_header(auth_sessions):
    """Authenticated Citizen adding X-Simulated-Role: ADMINISTRATOR is NOT escalated (returns 403)."""
    case_id = _seed_case(department="DRAINAGE_STORMWATER", owner_id="cit-user-1")
    cit_cookie = {"jarvis_session_id": auth_sessions["citizen"].session_id}

    spoof_headers = {
        "X-Simulated-Role": "ADMINISTRATOR",
        "X-Simulated-Principal-Id": "super-admin",
        "X-Principal-Role": "ADMINISTRATOR",
    }

    # Attacker tries to update status with session cookie + admin headers
    res = client.patch(
        f"/api/cases/{case_id}/status",
        json={"status": "RESOLVED", "note": "Hacked transition"},
        cookies=cit_cookie,
        headers=spoof_headers,
    )
    # SESSION IDENTITY WINS: Evaluated strictly as Citizen -> Cedar DENIES with 403
    assert res.status_code == 403
    assert res.json() == {"detail": "Authorization denied"}


def test_api_attack_drainage_officer_spoofing_roads_department_header(auth_sessions):
    """Authenticated Drainage Officer spoofing PWD_ROADS department header is NOT escalated."""
    roads_case_id = _seed_case(department="PWD_ROADS")
    drainage_cookie = {"jarvis_session_id": auth_sessions["drainage_officer"].session_id}

    spoof_headers = {
        "X-Simulated-Role": "AUTHORITY_OFFICER",
        "X-Simulated-Department": "PWD_ROADS",
        "X-Principal-Department": "PWD_ROADS",
    }

    # Attacker tries to update ROADS case using drainage session + roads department header
    res = client.patch(
        f"/api/cases/{roads_case_id}/status",
        json={"status": "ROUTING_PREPARED"},
        cookies=drainage_cookie,
        headers=spoof_headers,
    )
    # SESSION IDENTITY WINS: Evaluated as DRAINAGE_STORMWATER -> Cedar DENIES with 403
    assert res.status_code == 403
    assert res.json() == {"detail": "Authorization denied"}


def test_api_attack_body_department_manipulation_cannot_bypass_cedar(auth_sessions):
    """Request body department cannot alter the persisted case department or bypass Cedar."""
    roads_case_id = _seed_case(department="PWD_ROADS")
    drainage_cookie = {"jarvis_session_id": auth_sessions["drainage_officer"].session_id}

    # Attacker sends department="DRAINAGE_STORMWATER" in body
    res = client.patch(
        f"/api/cases/{roads_case_id}/status",
        json={
            "status": "ROUTING_PREPARED",
            "department": "DRAINAGE_STORMWATER",
        },
        cookies=drainage_cookie,
    )
    # Backend loads actual case from persistence (PWD_ROADS) -> Cedar DENIES with 403
    assert res.status_code == 403
    assert res.json() == {"detail": "Authorization denied"}


# ---------------------------------------------------------------------------
# 4. Runtime Cedar Decision Path Proof (Section 28)
# ---------------------------------------------------------------------------

def test_api_runtime_cedar_decision_path_proof(auth_sessions):
    """PROVE the full runtime call chain:
    HTTP Request
    -> authenticated session (jarvis_session_id)
    -> AuthenticatedPrincipal (Officer Rajesh Kumar)
    -> AuthorizationService.enforce
    -> cedarpy.is_authorized
    -> decision ALLOW
    -> status update operation executes successfully.
    """
    case_id = _seed_case(department="DRAINAGE_STORMWATER")
    drainage_cookie = {"jarvis_session_id": auth_sessions["drainage_officer"].session_id}

    # Wrap cedarpy.is_authorized with a spy to prove it is called on the live runtime path
    original_is_authorized = cedarpy.is_authorized
    call_records = []

    def spy_is_authorized(*args, **kwargs):
        call_records.append({"args": args, "kwargs": kwargs})
        return original_is_authorized(*args, **kwargs)

    with patch("cedarpy.is_authorized", side_effect=spy_is_authorized):
        res = client.patch(
            f"/api/cases/{case_id}/status",
            json={"status": "ROUTING_PREPARED", "note": "Live Cedar execution verified"},
            cookies=drainage_cookie,
        )
        assert res.status_code == 200
        assert res.json()["status"] == "ROUTING_PREPARED"

    # Verify cedarpy.is_authorized was called on the runtime path
    assert len(call_records) >= 1, "cedarpy.is_authorized was NEVER called during endpoint execution!"

    last_call = call_records[-1]
    req_dict = last_call["kwargs"].get("request") or last_call["args"][0]

    expected_pid = auth_sessions["drainage_officer"].principal_id
    assert req_dict["principal"]["type"] == "JarvisCivic::AuthorityOfficer"
    assert req_dict["principal"]["id"] == expected_pid
    assert req_dict["action"]["id"] == "update_case_status"
    assert req_dict["resource"]["id"] == case_id

    # Verify entities passed to Cedar contain the authenticated department
    entities = last_call["kwargs"].get("entities") or last_call["args"][2]
    principal_entity = next((e for e in entities if e["uid"]["id"] == expected_pid), None)
    assert principal_entity is not None
    assert principal_entity["attrs"]["department"] == "DRAINAGE_STORMWATER"
