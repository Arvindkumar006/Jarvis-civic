"""Development and Test Principal Resolver for JARVIS Civic.

Phase 3 Security Component:
Extracts application principal identity from incoming request headers
for local development and testing.

SECURITY INVARIANT:
Unauthenticated requests NEVER default to Citizen.
Requests lacking identity headers default strictly to PUBLIC.
Invalid roles or unauthorized parameters safely degrade to PUBLIC or fail closed.
"""

from typing import Optional
from fastapi import Header, Request
from app.models.security import ApplicationPrincipal, ApplicationRole


def get_current_principal(
    request: Request,
    x_principal_id: Optional[str] = Header(default=None, alias="X-Principal-Id"),
    x_principal_role: Optional[str] = Header(default=None, alias="X-Principal-Role"),
    x_principal_department: Optional[str] = Header(default=None, alias="X-Principal-Department"),
    x_simulated_id: Optional[str] = Header(default=None, alias="X-Simulated-Principal-Id"),
    x_simulated_role: Optional[str] = Header(default=None, alias="X-Simulated-Role"),
    x_simulated_department: Optional[str] = Header(default=None, alias="X-Simulated-Department"),
) -> ApplicationPrincipal:
    """Resolve the active principal from DEV/test/simulation headers.

    WARNING: This is strictly a local development/test identity mechanism.
    Production identity verification and authentication will be implemented in later phases.
    """
    raw_id = (x_principal_id or x_simulated_id or "").strip()
    raw_role = (x_principal_role or x_simulated_role or "").strip()
    raw_dept = (x_principal_department or x_simulated_department or "").strip()

    # 1. No identity headers or empty strings provided -> Default strictly to PUBLIC
    if not raw_id or not raw_role:
        return ApplicationPrincipal(
            principal_id="anonymous-public-user",
            role=ApplicationRole.PUBLIC,
            department=None,
        )

    # 2. Validate role safely
    role_str = raw_role.upper()
    try:
        role = ApplicationRole(role_str)
    except ValueError:
        # Invalid or unmapped role string -> Degrade safely to PUBLIC (never grant elevated privileges)
        return ApplicationPrincipal(
            principal_id=raw_id[:64] if raw_id else "anonymous-public-user",
            role=ApplicationRole.PUBLIC,
            department=None,
        )

    # 3. Department isolation: Citizen and Public cannot possess an authority department scope
    if role in (ApplicationRole.PUBLIC, ApplicationRole.CITIZEN):
        clean_dept = None
    else:
        clean_dept = raw_dept[:128] if raw_dept else None

    return ApplicationPrincipal(
        principal_id=raw_id[:64],
        role=role,
        department=clean_dept,
    )
