"""Authorized OpenSearch Civic Docket Search API for JARVIS Civic (Phase 8.6).

Exposes authorized search and index reconciliation endpoints.

ARCHITECTURAL INVARIANTS:
1. Cedar is strictly the authoritative authorization engine.
2. OpenSearch NEVER decides authorization.
3. Level 1 Isolation: Cedar PDP rejects unauthorized department requests with HTTP 403.
4. Level 2 Isolation: Server-derived department is injected into OpenSearch boolean DSL.
5. Deterministic Department Spoof Behavior: Client department parameter differing from
   principal.department for Authority Officer / Supervisor returns HTTP 403.
6. Public tracking is completely separate and safe.
7. OpenSearch outage returns honest HTTP 503, never fake empty results.
"""

import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from opensearchpy import exceptions as os_exceptions

from app.models.account import AuthenticatedPrincipal
from app.models.enums import ControlledDepartment
from app.models.search import (
    DocketSearchItem,
    DocketSearchParams,
    DocketSearchResult,
    RebuildIndexResult,
)
from app.models.security import ApplicationRole, CivicAction
from app.security.authorization_service import authorization_service
from app.security.principals import require_authenticated_principal
from app.services.case_store import case_store
from app.services.search.opensearch_service import opensearch_service

logger = logging.getLogger("jarvis.api.search")

router = APIRouter(prefix="/api/dockets", tags=["Docket Search"])


@router.get("/search", response_model=DocketSearchResult)
def search_dockets(
    request: Request,
    q: Optional[str] = Query(default=None, max_length=200, description="Search term across title, description, location"),
    department: Optional[str] = Query(default=None, description="Department filter"),
    status_filter: Optional[str] = Query(default=None, alias="status", description="Case status filter"),
    category: Optional[str] = Query(default=None, description="Category filter"),
    page: int = Query(default=1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(default=20, ge=1, le=100, description="Page size (max 100)"),
    sort_by: str = Query(default="updated_at", description="Sort field: updated_at, created_at, status"),
    sort_order: str = Query(default="desc", description="Sort order: asc or desc"),
    principal: AuthenticatedPrincipal = Depends(require_authenticated_principal),
) -> DocketSearchResult:
    """Execute authorized docket search backed by OpenSearch.

    Enforces real Cedar authorization chain:
    Authenticated Session -> AuthenticatedPrincipal -> AuthorizationService -> Cedar -> ALLOW/DENY -> OpenSearch.
    """
    # 1. Enforce department isolation rules and target department determination
    target_dept: str
    authorized_search_scope: Optional[str]

    if principal.role in (ApplicationRole.AUTHORITY_OFFICER, ApplicationRole.MUNICIPAL_SUPERVISOR):
        # Deterministic Department Spoof Check:
        # If client explicitly specifies a department that differs from principal.department,
        # we evaluate Cedar with the client-requested department, which Cedar will DENY (Policy G & H).
        # We must NOT silently override the request.
        if department and department.strip() and department.strip() != (principal.department or ""):
            target_dept = department.strip()
        else:
            target_dept = (principal.department or "").strip()

        authorized_search_scope = principal.department
    elif principal.role == ApplicationRole.ADMINISTRATOR:
        if department and department.strip():
            target_dept = department.strip()
            authorized_search_scope = department.strip()
        else:
            target_dept = "ALL"
            authorized_search_scope = None
    else:
        # Citizen, Public, or other roles have no authority search privilege
        target_dept = department.strip() if department else "PUBLIC"
        authorized_search_scope = None

    # 2. Real Cedar Authorization Evaluation (Level 1 Isolation)
    authorization_service.enforce(
        principal=principal,
        action=CivicAction.SEARCH_DOCKETS,
        resource_id=target_dept,
        resource_type="CivicDocketSearch",
        resource_department=target_dept,
    )

    # 3. Construct structured, validated parameters
    params = DocketSearchParams(
        q=q,
        department=authorized_search_scope,
        status=status_filter,
        category=category,
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_order=sort_order,
    )

    # 4. Query OpenSearch (Level 2 Isolation applied inside search_dockets)
    try:
        results = opensearch_service.search_dockets(
            params=params,
            authorized_department=authorized_search_scope,
        )
        return results
    except (
        os_exceptions.ConnectionError,
        os_exceptions.ConnectionTimeout,
        os_exceptions.TransportError,
        ConnectionError,
        TimeoutError,
    ) as exc:
        logger.error("OpenSearch cluster unreachable or timed out during search: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OpenSearch index service is temporarily unavailable. Please try again later.",
        )
    except Exception as exc:
        logger.error("Unexpected error during docket search: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while querying docket search index.",
        )


@router.post("/rebuild-index", response_model=RebuildIndexResult)
def rebuild_docket_index(
    request: Request,
    principal: AuthenticatedPrincipal = Depends(require_authenticated_principal),
) -> RebuildIndexResult:
    """Rebuild the OpenSearch docket index from authoritative CaseStore.

    Restricted to Administrator under Cedar policy.
    """
    # Cedar Authorization
    authorization_service.enforce(
        principal=principal,
        action=CivicAction.SEARCH_DOCKETS,
        resource_id="ALL",
        resource_type="CivicDocketSearch",
        resource_department="ALL",
    )

    # Perform reconciliation
    try:
        result = opensearch_service.rebuild_docket_index(case_store)
        return result
    except (
        os_exceptions.ConnectionError,
        os_exceptions.ConnectionTimeout,
        os_exceptions.TransportError,
        ConnectionError,
        TimeoutError,
    ) as exc:
        logger.error("OpenSearch unavailable during index rebuild: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OpenSearch service is unavailable. Cannot rebuild index.",
        )
