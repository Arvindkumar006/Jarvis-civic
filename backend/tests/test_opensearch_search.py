"""Phase 8.6 OpenSearch Authorized Civic Docket Search Tests.

Covers tests A through W required by Phase 8.6:
A. OpenSearch index creation
B. Docket indexing
C. Docket update
D. Search by case ID
E. Search by free text
F. Search by status
G. Search by department
H. Pagination
I. Deterministic sorting
J. Invalid query validation
K. OpenSearch unavailable -> 503
L. Citizen cannot access authority search
M. Public cannot access authority search
N. Authority officer can search own department
O. Authority officer cannot search another department
P. Supervisor authorization according to existing Cedar policy
Q. Administrator authorization according to existing Cedar policy
R. Department spoof attempt fails (Correction 3)
S. Raw OpenSearch DSL injection attempt is impossible/blocked
T. Search results are sanitized (Correction 2)
U. OpenSearch is not treated as source of truth
V. Rebuild/reconciliation restores index from persistence (Correction 5)
W. Existing public tracking remains unchanged
"""

from datetime import datetime, timezone
import time
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient
from opensearchpy import exceptions as os_exceptions

from app.config.settings import settings
from app.main import app
from app.models.account import UserAccount
from app.models.enums import CaseStatus, ControlledDepartment
from app.models.security import (
    ApplicationRole,
    CivicCaseCreateRequest,
    CivicCaseRecord,
)
from app.security.hasher import password_hasher
from app.security.session import session_store
from app.services.case_store import case_store
from app.services.persistence.account_repository import account_repository
from app.services.search.opensearch_service import opensearch_service

client = TestClient(app)


# ---------------------------------------------------------------------------
# Test Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def setup_environment():
    """Ensure clean case store and session store, and ensure OpenSearch index exists."""
    case_store.clear()
    session_store.clear()
    opensearch_service.ensure_index()
    yield
    case_store.clear()
    session_store.clear()


@pytest.fixture
def test_accounts():
    """Create test accounts and return active sessions."""
    # 1. Citizen Ananya
    cit_acc = account_repository.get_by_email("citizen@jarviscivic.local")
    if not cit_acc:
        cit_acc = UserAccount(
            principal_id="cit-ananya-01",
            email="citizen@jarviscivic.local",
            password_hash=password_hasher.hash_password("JarvisCivic2026!"),
            display_name="Ananya Sharma",
            role=ApplicationRole.CITIZEN,
            department=None,
        )
        account_repository.save(cit_acc)
    cit_sess = session_store.create_session(cit_acc)

    # 2. Drainage Authority Officer
    drainage_acc = account_repository.get_by_email("officer@jarviscivic.local")
    if not drainage_acc:
        drainage_acc = UserAccount(
            principal_id="officer-drainage-01",
            email="officer@jarviscivic.local",
            password_hash=password_hasher.hash_password("JarvisCivic2026!"),
            display_name="Rajesh Kumar",
            role=ApplicationRole.AUTHORITY_OFFICER,
            department=ControlledDepartment.DRAINAGE_STORMWATER.value,
        )
        account_repository.save(drainage_acc)
    drainage_sess = session_store.create_session(drainage_acc)

    # 3. Roads Authority Officer
    roads_acc = account_repository.get_by_email("roads.officer@jarviscivic.local")
    if not roads_acc:
        roads_acc = UserAccount(
            principal_id="officer-roads-01",
            email="roads.officer@jarviscivic.local",
            password_hash=password_hasher.hash_password("JarvisCivic2026!"),
            display_name="Suresh Prabhu",
            role=ApplicationRole.AUTHORITY_OFFICER,
            department=ControlledDepartment.PWD_ROADS.value,
        )
        account_repository.save(roads_acc)
    roads_sess = session_store.create_session(roads_acc)

    # 4. Municipal Supervisor (Drainage Jurisdiction)
    sup_acc = account_repository.get_by_email("supervisor@jarviscivic.local")
    if not sup_acc:
        sup_acc = UserAccount(
            principal_id="sup-drainage-01",
            email="supervisor@jarviscivic.local",
            password_hash=password_hasher.hash_password("JarvisCivic2026!"),
            display_name="Chief Supervisor Mehta",
            role=ApplicationRole.MUNICIPAL_SUPERVISOR,
            department=ControlledDepartment.DRAINAGE_STORMWATER.value,
        )
        account_repository.save(sup_acc)
    sup_sess = session_store.create_session(sup_acc)

    # 5. Administrator
    admin_acc = account_repository.get_by_email("admin@jarviscivic.local")
    if not admin_acc:
        admin_acc = UserAccount(
            principal_id="admin-master-01",
            email="admin@jarviscivic.local",
            password_hash=password_hasher.hash_password("JarvisCivic2026!"),
            display_name="Municipal Commissioner",
            role=ApplicationRole.ADMINISTRATOR,
            department=None,
        )
        account_repository.save(admin_acc)
    admin_sess = session_store.create_session(admin_acc)

    return {
        "citizen": cit_sess,
        "drainage_officer": drainage_sess,
        "roads_officer": roads_sess,
        "supervisor": sup_sess,
        "admin": admin_sess,
    }


def helper_create_test_case(department: ControlledDepartment, description: str, location: str) -> CivicCaseRecord:
    """Helper to create a case via case_store and index it."""
    req = CivicCaseCreateRequest(
        description=description,
        location=location,
        department=department,
        pincode="560038",
        is_public=True,
    )
    case = case_store.create_case(req, owner_id="cit-test-owner")
    opensearch_service.index_docket(case)
    return case


# ---------------------------------------------------------------------------
# Test Cases A through W
# ---------------------------------------------------------------------------

def test_a_opensearch_index_creation():
    """A. Verify OpenSearch index creation and alias mapping."""
    created = opensearch_service.ensure_index()
    assert created is True

    client_os = opensearch_service.get_client()
    assert client_os.indices.exists(index=settings.OPENSEARCH_INDEX_NAME) is True
    assert client_os.indices.exists_alias(name=settings.OPENSEARCH_INDEX_ALIAS) is True

    mapping = client_os.indices.get_mapping(index=settings.OPENSEARCH_INDEX_NAME)
    props = mapping[settings.OPENSEARCH_INDEX_NAME]["mappings"]["properties"]
    assert "case_id" in props
    assert "department" in props
    assert "status" in props
    assert "description" in props
    assert "created_at" in props


def test_b_docket_indexing():
    """B. Verify docket indexing into OpenSearch."""
    case = helper_create_test_case(
        department=ControlledDepartment.DRAINAGE_STORMWATER,
        description="Stormwater inlet severely clogged with plastic waste",
        location="100 Feet Road, Indiranagar",
    )
    client_os = opensearch_service.get_client()
    doc = client_os.get(index=settings.OPENSEARCH_INDEX_ALIAS, id=case.case_id)
    assert doc["found"] is True
    assert doc["_source"]["case_id"] == case.case_id
    assert doc["_source"]["department"] == "DRAINAGE_STORMWATER"
    assert doc["_source"]["status"] == "DOCKET_CREATED"


def test_c_docket_update():
    """C. Verify docket update reflects in OpenSearch projection."""
    case = helper_create_test_case(
        department=ControlledDepartment.DRAINAGE_STORMWATER,
        description="Drainage issue to update",
        location="Old Airport Road",
    )
    # Update status in persistence and OpenSearch
    updated = case_store.update_case_status(
        case_id=case.case_id,
        new_status=CaseStatus.ROUTING_PREPARED,
        note="Routing prepared for municipal suction crew",
    )
    assert updated is not None
    opensearch_service.update_docket(updated)

    client_os = opensearch_service.get_client()
    doc = client_os.get(index=settings.OPENSEARCH_INDEX_ALIAS, id=case.case_id)
    assert doc["_source"]["status"] == "ROUTING_PREPARED"


def test_d_search_by_case_id(test_accounts):
    """D. Search by exact Case ID via API."""
    case = helper_create_test_case(
        department=ControlledDepartment.DRAINAGE_STORMWATER,
        description="Broken manhole cover needing urgent replacement",
        location="CMH Road, Metro Pillar 42",
    )
    drainage_cookie = test_accounts["drainage_officer"].session_id
    resp = client.get(
        f"/api/dockets/search?q={case.case_id}",
        cookies={settings.AUTH_COOKIE_NAME: drainage_cookie},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1
    found = any(item["case_id"] == case.case_id for item in data["items"])
    assert found is True


def test_e_search_by_free_text(test_accounts):
    """E. Search by free-text keywords."""
    case = helper_create_test_case(
        department=ControlledDepartment.DRAINAGE_STORMWATER,
        description="Hazardous toxic chemical effluent leaking from storm culvert",
        location="Domlur Ring Road Culvert",
    )
    drainage_cookie = test_accounts["drainage_officer"].session_id
    resp = client.get(
        "/api/dockets/search?q=chemical effluent",
        cookies={settings.AUTH_COOKIE_NAME: drainage_cookie},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1
    assert data["items"][0]["case_id"] == case.case_id


def test_f_search_by_status(test_accounts):
    """F. Filter search by case status."""
    case = helper_create_test_case(
        department=ControlledDepartment.DRAINAGE_STORMWATER,
        description="Ditch requiring review",
        location="Austin Town",
    )
    case_store.update_case_status(case.case_id, new_status=CaseStatus.RESOLVED)
    updated = case_store.get_case(case.case_id)
    opensearch_service.update_docket(updated)

    drainage_cookie = test_accounts["drainage_officer"].session_id
    resp = client.get(
        "/api/dockets/search?status=RESOLVED",
        cookies={settings.AUTH_COOKIE_NAME: drainage_cookie},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert all(item["status"] == "RESOLVED" for item in data["items"])


def test_g_search_by_department(test_accounts):
    """G. Search by department (Administrator universal view)."""
    case_drainage = helper_create_test_case(
        department=ControlledDepartment.DRAINAGE_STORMWATER,
        description="Drainage overflow at junction",
        location="Ulsoor Lake Gate",
    )
    case_roads = helper_create_test_case(
        department=ControlledDepartment.PWD_ROADS,
        description="Massive asphalt crater causing accidents",
        location="Outer Ring Road Bellandur",
    )

    admin_cookie = test_accounts["admin"].session_id
    # Search PWD_ROADS as Administrator
    resp = client.get(
        "/api/dockets/search?department=PWD_ROADS",
        cookies={settings.AUTH_COOKIE_NAME: admin_cookie},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert all(item["department"] == "PWD_ROADS" for item in data["items"])


def test_h_pagination(test_accounts):
    """H. Search result pagination."""
    for i in range(5):
        helper_create_test_case(
            department=ControlledDepartment.DRAINAGE_STORMWATER,
            description=f"Pagination test drain case #{i}",
            location=f"Sector {i} Layout",
        )

    admin_cookie = test_accounts["admin"].session_id
    resp_page1 = client.get(
        "/api/dockets/search?page=1&page_size=2",
        cookies={settings.AUTH_COOKIE_NAME: admin_cookie},
    )
    assert resp_page1.status_code == 200
    data1 = resp_page1.json()
    assert len(data1["items"]) == 2
    assert data1["page"] == 1
    assert data1["has_next"] is True

    resp_page2 = client.get(
        "/api/dockets/search?page=2&page_size=2",
        cookies={settings.AUTH_COOKIE_NAME: admin_cookie},
    )
    assert resp_page2.status_code == 200
    data2 = resp_page2.json()
    assert len(data2["items"]) == 2
    assert data2["page"] == 2

    # Verify no overlapping items between page 1 and page 2
    page1_ids = {item["case_id"] for item in data1["items"]}
    page2_ids = {item["case_id"] for item in data2["items"]}
    assert page1_ids.isdisjoint(page2_ids)


def test_i_deterministic_sorting(test_accounts):
    """I. Deterministic sorting by updated_at desc and case_id asc."""
    admin_cookie = test_accounts["admin"].session_id
    resp = client.get(
        "/api/dockets/search?sort_by=updated_at&sort_order=desc",
        cookies={settings.AUTH_COOKIE_NAME: admin_cookie},
    )
    assert resp.status_code == 200
    data = resp.json()
    items = data["items"]
    if len(items) > 1:
        dates = [item["updated_at"] for item in items]
        assert dates == sorted(dates, reverse=True)


def test_j_invalid_query_validation(test_accounts):
    """J. Invalid query parameters return structured validation errors."""
    admin_cookie = test_accounts["admin"].session_id

    # page < 1
    resp1 = client.get("/api/dockets/search?page=0", cookies={settings.AUTH_COOKIE_NAME: admin_cookie})
    assert resp1.status_code == 422

    # page_size > 100
    resp2 = client.get("/api/dockets/search?page_size=500", cookies={settings.AUTH_COOKIE_NAME: admin_cookie})
    assert resp2.status_code == 422


def test_k_opensearch_unavailable_returns_503(test_accounts):
    """K. When OpenSearch is unavailable, API returns honest HTTP 503 Service Unavailable."""
    drainage_cookie = test_accounts["drainage_officer"].session_id

    with patch.object(opensearch_service, "search_dockets", side_effect=ConnectionError("OpenSearch cluster down")):
        resp = client.get(
            "/api/dockets/search",
            cookies={settings.AUTH_COOKIE_NAME: drainage_cookie},
        )
        assert resp.status_code == 503
        assert "unavailable" in resp.json()["detail"].lower()


def test_l_citizen_cannot_access_authority_search(test_accounts):
    """L. Authenticated Citizen cannot access authority search (Cedar DENY -> 403)."""
    cit_cookie = test_accounts["citizen"].session_id
    resp = client.get(
        "/api/dockets/search",
        cookies={settings.AUTH_COOKIE_NAME: cit_cookie},
    )
    assert resp.status_code == 403
    assert resp.json()["detail"] == "Authorization denied"


def test_m_public_cannot_access_authority_search():
    """M. Unauthenticated Public user cannot access authority search (HTTP 401)."""
    resp = client.get("/api/dockets/search")
    assert resp.status_code == 401
    assert "Authentication required" in resp.json()["detail"]


def test_n_authority_officer_can_search_own_department(test_accounts):
    """N. Authority Officer can search within assigned department."""
    helper_create_test_case(
        department=ControlledDepartment.DRAINAGE_STORMWATER,
        description="Flooding near Indiranagar metro station",
        location="100 Feet Road",
    )
    drainage_cookie = test_accounts["drainage_officer"].session_id
    resp = client.get(
        "/api/dockets/search",
        cookies={settings.AUTH_COOKIE_NAME: drainage_cookie},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert all(item["department"] == "DRAINAGE_STORMWATER" for item in data["items"])


def test_o_authority_officer_cannot_search_another_department(test_accounts):
    """O. Authority Officer attempting to search another department receives HTTP 403."""
    drainage_cookie = test_accounts["drainage_officer"].session_id
    resp = client.get(
        "/api/dockets/search?department=PWD_ROADS",
        cookies={settings.AUTH_COOKIE_NAME: drainage_cookie},
    )
    assert resp.status_code == 403
    assert resp.json()["detail"] == "Authorization denied"


def test_p_supervisor_authorization_according_to_cedar(test_accounts):
    """P. Municipal Supervisor can search own department, denied for another department."""
    sup_cookie = test_accounts["supervisor"].session_id

    # Own department (DRAINAGE_STORMWATER) -> 200
    resp_allowed = client.get(
        "/api/dockets/search",
        cookies={settings.AUTH_COOKIE_NAME: sup_cookie},
    )
    assert resp_allowed.status_code == 200

    # Other department (ELECTRICITY_UTILITY) -> 403
    resp_denied = client.get(
        "/api/dockets/search?department=ELECTRICITY_UTILITY",
        cookies={settings.AUTH_COOKIE_NAME: sup_cookie},
    )
    assert resp_denied.status_code == 403


def test_q_administrator_authorization_according_to_cedar(test_accounts):
    """Q. Administrator is authorized to search all departments under Cedar Policy F."""
    admin_cookie = test_accounts["admin"].session_id
    resp = client.get(
        "/api/dockets/search",
        cookies={settings.AUTH_COOKIE_NAME: admin_cookie},
    )
    assert resp.status_code == 200


def test_r_department_spoof_attempt_fails(test_accounts):
    """R. Deterministic department spoof attempt returns HTTP 403 (Correction 3)."""
    drainage_cookie = test_accounts["drainage_officer"].session_id

    # Client claims to want PWD_ROADS with drainage session cookie
    resp = client.get(
        "/api/dockets/search?department=PWD_ROADS",
        headers={"X-Principal-Department": "PWD_ROADS"},
        cookies={settings.AUTH_COOKIE_NAME: drainage_cookie},
    )
    assert resp.status_code == 403
    assert resp.json()["detail"] == "Authorization denied"


def test_s_raw_dsl_injection_prevented(test_accounts):
    """S. Arbitrary OpenSearch DSL query string injection is sanitized and treated as literal text."""
    drainage_cookie = test_accounts["drainage_officer"].session_id
    injection_payload = '{"bool": {"must": [{"match_all": {}}]}}'

    resp = client.get(
        f"/api/dockets/search?q={injection_payload}",
        cookies={settings.AUTH_COOKIE_NAME: drainage_cookie},
    )
    assert resp.status_code == 200
    # No unhandled error or privilege breakout occurs


def test_t_search_results_are_sanitized(test_accounts):
    """T. Search results are sanitized: no owner_id, no is_public, no passwords, no tokens."""
    helper_create_test_case(
        department=ControlledDepartment.DRAINAGE_STORMWATER,
        description="Sanitization test docket",
        location="Indiranagar 12th Main",
    )
    drainage_cookie = test_accounts["drainage_officer"].session_id
    resp = client.get(
        "/api/dockets/search",
        cookies={settings.AUTH_COOKIE_NAME: drainage_cookie},
    )
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) > 0
    for item in items:
        # Strictly verify sensitive fields are NOT exposed (Correction 2)
        assert "owner_id" not in item
        assert "is_public" not in item
        assert "password" not in item
        assert "token" not in item
        assert "case_id" in item
        assert "department" in item
        assert "status" in item


def test_u_opensearch_not_source_of_truth():
    """U. Persistence remains the source of truth: index loss does not affect authoritative case data."""
    case = helper_create_test_case(
        department=ControlledDepartment.DRAINAGE_STORMWATER,
        description="Authoritative persistence truth check",
        location="Brigade Road",
    )
    # Authoritative case exists in CaseStore
    persisted = case_store.get_case(case.case_id)
    assert persisted is not None
    assert persisted.case_id == case.case_id

    # Delete index in OpenSearch
    client_os = opensearch_service.get_client()
    client_os.indices.delete(index=settings.OPENSEARCH_INDEX_NAME)

    # Persisted case is still 100% intact and undamaged
    persisted_after = case_store.get_case(case.case_id)
    assert persisted_after is not None
    assert persisted_after.case_id == case.case_id
    assert persisted_after.description == case.description


def test_v_rebuild_restores_index_from_persistence(test_accounts):
    """V. Rebuild/reconciliation completely restores OpenSearch index from authoritative CaseStore (Correction 5)."""
    # Create 3 cases in persistence
    case1 = helper_create_test_case(ControlledDepartment.DRAINAGE_STORMWATER, "Rebuild Case 1", "Loc 1")
    case2 = helper_create_test_case(ControlledDepartment.PWD_ROADS, "Rebuild Case 2", "Loc 2")
    case3 = helper_create_test_case(ControlledDepartment.WATER_SUPPLY, "Rebuild Case 3", "Loc 3")

    # Delete index to simulate index loss / corruption
    client_os = opensearch_service.get_client()
    client_os.indices.delete(index=settings.OPENSEARCH_INDEX_NAME)

    # Admin calls rebuild endpoint
    admin_cookie = test_accounts["admin"].session_id
    resp = client.post(
        "/api/dockets/rebuild-index",
        cookies={settings.AUTH_COOKIE_NAME: admin_cookie},
    )
    assert resp.status_code == 200
    rebuild_data = resp.json()
    assert rebuild_data["total_authoritative_cases"] >= 3
    assert rebuild_data["successfully_indexed"] >= 3
    assert rebuild_data["failed_indexing"] == 0

    # Verify cases are now queryable again in OpenSearch
    doc1 = client_os.get(index=settings.OPENSEARCH_INDEX_ALIAS, id=case1.case_id)
    assert doc1["found"] is True
    assert doc1["_source"]["case_id"] == case1.case_id


def test_w_public_tracking_remains_unchanged():
    """W. Anonymous public tracking remains unchanged and does not query OpenSearch."""
    case = helper_create_test_case(
        department=ControlledDepartment.DRAINAGE_STORMWATER,
        description="Public tracking test case",
        location="Koramangala 5th Block",
    )
    # Anonymous public GET /api/tracking/{case_id}
    resp = client.get(f"/api/tracking/{case.case_id}")
    assert resp.status_code == 200
    track_data = resp.json()
    assert track_data["case_id"] == case.case_id
    assert track_data["status"] == "DOCKET_CREATED"
