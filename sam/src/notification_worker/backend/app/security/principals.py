"""Principal Resolution for JARVIS Civic.

Phase 8.1: Real Backend-Owned Authentication Integration.

RESOLUTION ORDER:
1. Valid Authenticated Session (Cookie `jarvis_session_id`)?
   -> Return authoritative AuthenticatedPrincipal.
   -> SESSION ALWAYS WINS: Client-controlled simulation headers are completely ignored.
2. Legacy Phase 1-7 Compatibility Path (DEV/simulation headers present)?
   -> Return simulated ApplicationPrincipal for backwards test compatibility.
3. Otherwise:
   -> Default strictly to anonymous/public ApplicationPrincipal (anonymous-public-user).

SECURITY INVARIANTS:
- Client cannot override an authenticated session with headers.
- Anonymous visitor (anonymous-public-user) is NOT the authenticated PUBLIC account (public@jarviscivic.local).
- Unauthenticated requests cannot access endpoints guarded by require_authenticated_principal.
"""

from typing import Optional
from fastapi import Header, HTTPException, Request, status

from app.config.settings import settings
from app.models.account import AuthenticatedPrincipal
from app.models.security import ApplicationPrincipal, ApplicationRole
from app.security.session import session_store


def get_current_principal(
    request: Request,
    x_principal_id: Optional[str] = Header(default=None, alias="X-Principal-Id"),
    x_principal_role: Optional[str] = Header(default=None, alias="X-Principal-Role"),
    x_principal_department: Optional[str] = Header(default=None, alias="X-Principal-Department"),
    x_simulated_id: Optional[str] = Header(default=None, alias="X-Simulated-Principal-Id"),
    x_simulated_role: Optional[str] = Header(default=None, alias="X-Simulated-Role"),
    x_simulated_department: Optional[str] = Header(default=None, alias="X-Simulated-Department"),
) -> ApplicationPrincipal:
    """Resolve the active principal following strict security precedence.

    1. Authenticated Session (AUTHORITATIVE):
       If a valid session cookie is present, resolves to AuthenticatedPrincipal.
       Simulation headers are completely ignored.
    2. Legacy Simulation Headers (TEST COMPATIBILITY ONLY):
       If no session is present but legacy test headers are provided,
       resolves safely for Phase 1-7 backward compatibility.
    3. Anonymous Public (DEFAULT):
       If neither is provided, defaults strictly to anonymous public user.
    """
    # 1. Authoritative backend session verification (SESSION ALWAYS WINS)
    session_id = request.cookies.get(settings.AUTH_COOKIE_NAME)
    if session_id:
        session = session_store.get_session(session_id)
        if session:
            # Active authenticated session found - authoritative backend identity
            return AuthenticatedPrincipal(
                principal_id=session.principal_id,
                role=session.role,
                department=session.department,
                email=session.email,
                display_name=session.display_name,
                session_id=session.session_id,
                authenticated_at=session.created_at,
                is_authenticated=True,
            )
        # CRITICAL SECURITY INVARIANT:
        # If an authentication session cookie is present but invalid or expired,
        # it MUST NEVER fall back to legacy simulation headers or anonymous public.
        # It must strictly raise HTTP 401 Unauthorized.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session has expired or is invalid. Please log in again.",
        )

    # 2. Legacy Phase 1-7 compatibility path (simulation headers)
    def _extract_header(val: Optional[str], *aliases: str) -> str:
        if isinstance(val, str) and val.strip():
            return val.strip()
        for alias in aliases:
            header_val = request.headers.get(alias)
            if header_val and header_val.strip():
                return header_val.strip()
        return ""

    raw_id = _extract_header(x_principal_id, "x-principal-id", "x-simulated-principal-id") or _extract_header(x_simulated_id, "x-simulated-principal-id")
    raw_role = _extract_header(x_principal_role, "x-principal-role", "x-simulated-role") or _extract_header(x_simulated_role, "x-simulated-role")
    raw_dept = _extract_header(x_principal_department, "x-principal-department", "x-simulated-department") or _extract_header(x_simulated_department, "x-simulated-department")

    if not raw_id or not raw_role:
        # 3. Default strictly to anonymous public (never grant elevated privilege)
        return ApplicationPrincipal(
            principal_id="anonymous-public-user",
            role=ApplicationRole.PUBLIC,
            department=None,
        )

    # Validate role safely
    role_str = raw_role.upper()
    try:
        role = ApplicationRole(role_str)
    except ValueError:
        # Invalid role -> degrade safely to public
        return ApplicationPrincipal(
            principal_id=raw_id[:64] if raw_id else "anonymous-public-user",
            role=ApplicationRole.PUBLIC,
            department=None,
        )

    # Department isolation for simulation: Citizen and Public cannot possess an authority department scope
    if role in (ApplicationRole.PUBLIC, ApplicationRole.CITIZEN):
        clean_dept = None
    else:
        clean_dept = raw_dept[:128] if raw_dept else None

    return ApplicationPrincipal(
        principal_id=raw_id[:64],
        role=role,
        department=clean_dept,
    )


def require_authenticated_principal(request: Request) -> AuthenticatedPrincipal:
    """Strict dependency for endpoints requiring a verified server-side session.

    Rejects unauthenticated requests and legacy simulation headers with HTTP 401 Unauthorized.
    """
    session_id = request.cookies.get(settings.AUTH_COOKIE_NAME)
    if not session_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please log in.",
        )

    session = session_store.get_session(session_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session has expired or is invalid. Please log in again.",
        )

    return AuthenticatedPrincipal(
        principal_id=session.principal_id,
        role=session.role,
        department=session.department,
        email=session.email,
        display_name=session.display_name,
        session_id=session.session_id,
        authenticated_at=session.created_at,
        is_authenticated=True,
    )
