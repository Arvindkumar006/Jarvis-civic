"""Comprehensive Authentication and Identity Tests for JARVIS Civic.

Phase 8.1: Backend-Owned Authentication Foundation.
Validates all 30 positive, negative, and security invariant test cases.
"""

from datetime import datetime, timedelta, timezone
import logging
import pytest
from fastapi.testclient import TestClient

from app.config.settings import settings
from app.main import app
from app.models.enums import ControlledDepartment
from app.models.security import ApplicationRole
from app.security.hasher import password_hasher
from app.security.session import AuthSession, session_store
from app.services.persistence.account_repository import account_repository

client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_auth_state():
    """Reset session store and account repository for test isolation."""
    session_store.clear()
    account_repository.reset_seed_data()
    yield
    session_store.clear()
    account_repository.reset_seed_data()


# ---------------------------------------------------------------------------
# 1-6. Successful Login for Every Supported Role
# ---------------------------------------------------------------------------

def test_01_citizen_login_succeeds():
    """1. Citizen login succeeds with valid allocated credentials."""
    response = client.post(
        "/api/auth/login",
        json={"email": "citizen@jarviscivic.local", "password": settings.DEV_DEFAULT_PASSWORD},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["role"] == ApplicationRole.CITIZEN.value
    assert data["principal_id"] == "citizen-01"
    assert data["email"] == "citizen@jarviscivic.local"
    assert data["department"] is None


def test_02_authority_officer_login_succeeds():
    """2. Drainage Authority Officer login succeeds."""
    response = client.post(
        "/api/auth/login",
        json={"email": "officer@jarviscivic.local", "password": settings.DEV_DEFAULT_PASSWORD},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["role"] == ApplicationRole.AUTHORITY_OFFICER.value
    assert data["principal_id"] == "authority-officer-01"
    assert data["department"] == ControlledDepartment.DRAINAGE_STORMWATER.value


def test_03_roads_authority_officer_login_succeeds():
    """3. Roads Authority Officer login succeeds."""
    response = client.post(
        "/api/auth/login",
        json={"email": "roads.officer@jarviscivic.local", "password": settings.DEV_DEFAULT_PASSWORD},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["role"] == ApplicationRole.AUTHORITY_OFFICER.value
    assert data["principal_id"] == "authority-officer-roads-01"
    assert data["department"] == ControlledDepartment.PWD_ROADS.value


def test_04_municipal_supervisor_login_succeeds():
    """4. Municipal Supervisor login succeeds."""
    response = client.post(
        "/api/auth/login",
        json={"email": "supervisor@jarviscivic.local", "password": settings.DEV_DEFAULT_PASSWORD},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["role"] == ApplicationRole.MUNICIPAL_SUPERVISOR.value
    assert data["principal_id"] == "supervisor-01"
    assert data["department"] == ControlledDepartment.DRAINAGE_STORMWATER.value


def test_05_administrator_login_succeeds():
    """5. Administrator login succeeds."""
    response = client.post(
        "/api/auth/login",
        json={"email": "admin@jarviscivic.local", "password": settings.DEV_DEFAULT_PASSWORD},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["role"] == ApplicationRole.ADMINISTRATOR.value
    assert data["principal_id"] == "admin-01"
    assert data["department"] is None


def test_06_public_user_login_succeeds():
    """6. Public User login succeeds as authenticated PUBLIC account."""
    response = client.post(
        "/api/auth/login",
        json={"email": "public@jarviscivic.local", "password": settings.DEV_DEFAULT_PASSWORD},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["role"] == ApplicationRole.PUBLIC.value
    assert data["principal_id"] == "public-01"
    assert data["email"] == "public@jarviscivic.local"


# ---------------------------------------------------------------------------
# 7. Disabled Account Rejected
# ---------------------------------------------------------------------------

def test_07_disabled_account_fails():
    """7. Disabled account fails authentication even with correct password."""
    response = client.post(
        "/api/auth/login",
        json={"email": "disabled@jarviscivic.local", "password": settings.DEV_DEFAULT_PASSWORD},
    )
    assert response.status_code == 401
    assert "disabled" in response.json()["detail"].lower()


# ---------------------------------------------------------------------------
# 8-11. Role, Principal, Department Mapping & Same-Role Differentiation
# ---------------------------------------------------------------------------

def test_08_correct_role_returned():
    """8. Correct canonical role enum is returned from backend account data."""
    response = client.post(
        "/api/auth/login",
        json={"email": "supervisor@jarviscivic.local", "password": settings.DEV_DEFAULT_PASSWORD},
    )
    assert response.status_code == 200
    assert response.json()["role"] == ApplicationRole.MUNICIPAL_SUPERVISOR.value


def test_09_correct_principal_id_returned():
    """9. Correct allocated principal ID is returned from backend account data."""
    response = client.post(
        "/api/auth/login",
        json={"email": "citizen@jarviscivic.local", "password": settings.DEV_DEFAULT_PASSWORD},
    )
    assert response.status_code == 200
    assert response.json()["principal_id"] == "citizen-01"


def test_10_correct_department_returned():
    """10. Correct department scope is returned from backend account data."""
    response = client.post(
        "/api/auth/login",
        json={"email": "officer@jarviscivic.local", "password": settings.DEV_DEFAULT_PASSWORD},
    )
    assert response.status_code == 200
    assert response.json()["department"] == "DRAINAGE_STORMWATER"


def test_11_same_role_authority_accounts_retain_different_departments():
    """11. Same-role authority accounts (Drainage vs Roads) retain their distinct departments."""
    resp1 = client.post(
        "/api/auth/login",
        json={"email": "officer@jarviscivic.local", "password": settings.DEV_DEFAULT_PASSWORD},
    )
    resp2 = client.post(
        "/api/auth/login",
        json={"email": "roads.officer@jarviscivic.local", "password": settings.DEV_DEFAULT_PASSWORD},
    )
    assert resp1.status_code == 200
    assert resp2.status_code == 200
    assert resp1.json()["role"] == resp2.json()["role"] == ApplicationRole.AUTHORITY_OFFICER.value
    assert resp1.json()["department"] == "DRAINAGE_STORMWATER"
    assert resp2.json()["department"] == "PWD_ROADS"
    assert resp1.json()["principal_id"] != resp2.json()["principal_id"]


# ---------------------------------------------------------------------------
# 12-15. Negative Login Cases
# ---------------------------------------------------------------------------

def test_12_unknown_email_fails():
    """12. Unknown email is rejected with 401 Unauthorized."""
    response = client.post(
        "/api/auth/login",
        json={"email": "nonexistent@jarviscivic.local", "password": settings.DEV_DEFAULT_PASSWORD},
    )
    assert response.status_code == 401
    assert "invalid email or password" in response.json()["detail"].lower()


def test_13_incorrect_password_fails():
    """13. Incorrect password for existing account is rejected with 401."""
    response = client.post(
        "/api/auth/login",
        json={"email": "citizen@jarviscivic.local", "password": "WrongPassword123!"},
    )
    assert response.status_code == 401
    assert "invalid email or password" in response.json()["detail"].lower()


def test_14_empty_password_rejected():
    """14. Empty or whitespace password is rejected."""
    response = client.post(
        "/api/auth/login",
        json={"email": "citizen@jarviscivic.local", "password": "   "},
    )
    assert response.status_code == 422


def test_15_malformed_request_rejected():
    """15. Malformed request (invalid email structure or missing fields) is rejected with 422."""
    resp1 = client.post("/api/auth/login", json={"email": "not-an-email", "password": "abc"})
    assert resp1.status_code == 422

    resp2 = client.post("/api/auth/login", json={"email": "citizen@jarviscivic.local"})
    assert resp2.status_code == 422


# ---------------------------------------------------------------------------
# 16-18. Client Identity Manipulation Resistance
# ---------------------------------------------------------------------------

def test_16_client_role_cannot_override_backend_role():
    """16. Client-supplied role in payload or headers CANNOT override backend role."""
    response = client.post(
        "/api/auth/login",
        json={
            "email": "citizen@jarviscivic.local",
            "password": settings.DEV_DEFAULT_PASSWORD,
            "role": "ADMINISTRATOR",
        },
        headers={
            "X-Simulated-Role": "ADMINISTRATOR",
            "X-Principal-Role": "ADMINISTRATOR",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["role"] == ApplicationRole.CITIZEN.value
    assert data["role"] != "ADMINISTRATOR"


def test_17_client_principal_id_cannot_override_backend_principal():
    """17. Client-supplied principal ID cannot override backend principal ID."""
    response = client.post(
        "/api/auth/login",
        json={
            "email": "citizen@jarviscivic.local",
            "password": settings.DEV_DEFAULT_PASSWORD,
            "principal_id": "admin-super-id",
        },
        headers={
            "X-Principal-Id": "admin-super-id",
            "X-Simulated-Principal-Id": "admin-super-id",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["principal_id"] == "citizen-01"
    assert data["principal_id"] != "admin-super-id"


def test_18_client_department_cannot_override_backend_department():
    """18. Client-supplied department cannot override backend department."""
    response = client.post(
        "/api/auth/login",
        json={
            "email": "officer@jarviscivic.local",
            "password": settings.DEV_DEFAULT_PASSWORD,
            "department": "PWD_ROADS",
        },
        headers={
            "X-Simulated-Department": "PWD_ROADS",
            "X-Principal-Department": "PWD_ROADS",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["department"] == "DRAINAGE_STORMWATER"
    assert data["department"] != "PWD_ROADS"


# ---------------------------------------------------------------------------
# 19-22. Session Lifecycle (/api/auth/me, Logout, Expiration)
# ---------------------------------------------------------------------------

def test_19_me_succeeds_after_login():
    """19. GET /api/auth/me succeeds with cookie issued during login."""
    login_resp = client.post(
        "/api/auth/login",
        json={"email": "supervisor@jarviscivic.local", "password": settings.DEV_DEFAULT_PASSWORD},
    )
    assert login_resp.status_code == 200

    # Request /me using cookie automatically handled by TestClient session
    me_resp = client.get("/api/auth/me")
    assert me_resp.status_code == 200
    me_data = me_resp.json()
    assert me_data["email"] == "supervisor@jarviscivic.local"
    assert me_data["role"] == ApplicationRole.MUNICIPAL_SUPERVISOR.value
    assert me_data["principal_id"] == "supervisor-01"


def test_20_me_fails_without_session():
    """20. GET /api/auth/me without session cookie returns 401."""
    fresh_client = TestClient(app)
    response = fresh_client.get("/api/auth/me")
    assert response.status_code == 401
    assert "not authenticated" in response.json()["detail"].lower()


def test_21_me_fails_after_logout():
    """21. GET /api/auth/me fails after logout invalidates the session."""
    login_resp = client.post(
        "/api/auth/login",
        json={"email": "citizen@jarviscivic.local", "password": settings.DEV_DEFAULT_PASSWORD},
    )
    assert login_resp.status_code == 200

    logout_resp = client.post("/api/auth/logout")
    assert logout_resp.status_code == 200

    me_resp = client.get("/api/auth/me")
    assert me_resp.status_code == 401


def test_22_expired_session_fails():
    """22. Expired session is rejected on /api/auth/me."""
    account = account_repository.get_by_email("citizen@jarviscivic.local")
    assert account is not None

    # Manually create an expired session in session_store
    past_time = datetime.now(timezone.utc) - timedelta(hours=1)
    expired_session = AuthSession(
        session_id="expired-session-token-999",
        principal_id=account.principal_id,
        email=account.email,
        display_name=account.display_name,
        role=account.role,
        department=account.department,
        created_at=past_time - timedelta(hours=2),
        expires_at=past_time,
        is_active=True,
    )
    session_store._sessions[expired_session.session_id] = expired_session

    client_with_cookie = TestClient(app)
    client_with_cookie.cookies.set(settings.AUTH_COOKIE_NAME, expired_session.session_id)

    response = client_with_cookie.get("/api/auth/me")
    assert response.status_code == 401
    assert "expired" in response.json()["detail"].lower()


# ---------------------------------------------------------------------------
# 23-24. Cookie Security Flags
# ---------------------------------------------------------------------------

def test_23_session_cookie_is_httponly():
    """23. Set-Cookie header contains HttpOnly flag."""
    response = client.post(
        "/api/auth/login",
        json={"email": "citizen@jarviscivic.local", "password": settings.DEV_DEFAULT_PASSWORD},
    )
    assert response.status_code == 200
    set_cookie = response.headers.get("set-cookie", "")
    assert settings.AUTH_COOKIE_NAME in set_cookie
    assert "httponly" in set_cookie.lower()


def test_24_session_cookie_uses_correct_samesite():
    """24. Set-Cookie header contains SameSite=lax setting."""
    response = client.post(
        "/api/auth/login",
        json={"email": "citizen@jarviscivic.local", "password": settings.DEV_DEFAULT_PASSWORD},
    )
    assert response.status_code == 200
    set_cookie = response.headers.get("set-cookie", "")
    assert f"samesite={settings.AUTH_COOKIE_SAMESITE}".lower() in set_cookie.lower()


# ---------------------------------------------------------------------------
# 25-27. Credential Privacy & Logging Safeguards
# ---------------------------------------------------------------------------

def test_25_password_hash_never_appears_in_api_response():
    """25. Password hash is strictly omitted from login and /me responses."""
    resp1 = client.post(
        "/api/auth/login",
        json={"email": "admin@jarviscivic.local", "password": settings.DEV_DEFAULT_PASSWORD},
    )
    resp2 = client.get("/api/auth/me")

    for resp in (resp1, resp2):
        body = resp.text.lower()
        assert "password_hash" not in body
        assert "$argon2id$" not in body
        assert "password" not in resp.json()


def test_26_password_hash_never_reaches_frontend_model():
    """26. UserAccountResponse schema does not define password_hash field."""
    from app.models.account import UserAccountResponse
    fields = UserAccountResponse.model_fields.keys()
    assert "password_hash" not in fields
    assert "password" not in fields


def test_27_plaintext_password_never_appears_in_logs(caplog):
    """27. Plaintext password never appears in application log records."""
    unique_secret = "UniqueUltraSecretPassword987!"
    with caplog.at_level(logging.DEBUG):
        client.post(
            "/api/auth/login",
            json={"email": "citizen@jarviscivic.local", "password": unique_secret},
        )

    for record in caplog.records:
        assert unique_secret not in record.getMessage()


# ---------------------------------------------------------------------------
# 28-30. Anonymous vs Authenticated PUBLIC & Legacy Compatibility
# ---------------------------------------------------------------------------

def test_28_anonymous_visitor_is_not_authenticated_public():
    """28. Unauthenticated requests default to anonymous-public-user, NOT public-01."""
    fresh_client = TestClient(app)
    # When creating a public tracking case without auth headers or cookies:
    resp = fresh_client.get("/api/cases/test-case-nonexistent")
    # Response is 404 or 403, but verify that unauthenticated identity is anonymous
    from app.security.principals import get_current_principal
    from starlette.requests import Request

    scope = {"type": "http", "method": "GET", "path": "/", "headers": []}
    req = Request(scope)
    principal = get_current_principal(req)
    assert principal.principal_id == "anonymous-public-user"
    assert principal.principal_id != "public-01"


def test_29_authenticated_public_account_resolves_correctly():
    """29. Logging in as public@jarviscivic.local resolves to authenticated public-01."""
    login_resp = client.post(
        "/api/auth/login",
        json={"email": "public@jarviscivic.local", "password": settings.DEV_DEFAULT_PASSWORD},
    )
    assert login_resp.status_code == 200
    data = login_resp.json()
    assert data["email"] == "public@jarviscivic.local"
    assert data["principal_id"] == "public-01"
    assert data["role"] == ApplicationRole.PUBLIC.value


def test_30_legacy_headers_cannot_override_valid_authenticated_session():
    """30. A valid authenticated session strictly overrides any client simulation headers."""
    # Log in as citizen
    login_resp = client.post(
        "/api/auth/login",
        json={"email": "citizen@jarviscivic.local", "password": settings.DEV_DEFAULT_PASSWORD},
    )
    assert login_resp.status_code == 200

    # Submit request with attacker simulation headers attempting to escalate to ADMINISTRATOR
    # Test through /api/cases which uses Depends(get_current_principal)
    # The authenticated session identity must win: principal_id=citizen-01, role=CITIZEN
    headers = {
        "X-Principal-Id": "attacker-admin",
        "X-Principal-Role": "ADMINISTRATOR",
        "X-Simulated-Role": "ADMINISTRATOR",
        "X-Simulated-Principal-Id": "attacker-admin",
        "X-Principal-Department": "PWD_ROADS",
    }
    case_payload = {
        "description": "Pothole in my neighborhood street",
        "location": "First Cross Street",
        "department": "PWD_ROADS",
        "pincode": "600001",
        "is_public": True,
    }
    create_resp = client.post("/api/cases", json=case_payload, headers=headers)
    assert create_resp.status_code == 201
    created_case = create_resp.json()
    # The owner_id MUST be the authenticated principal "citizen-01", NOT "attacker-admin"!
    assert created_case["owner_id"] == "citizen-01"
    assert created_case["owner_id"] != "attacker-admin"
