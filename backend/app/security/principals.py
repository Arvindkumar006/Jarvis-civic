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
) -> ApplicationPrincipal:
    """Resolve the active principal from DEV/test headers.

    WARNING: This is strictly a local development/test identity mechanism.
    Production identity verification and authentication will be implemented in later phases.
    """
    # 1. No identity headers provided -> Default strictly to PUBLIC
    if not x_principal_id or not x_principal_role:
        return ApplicationPrincipal(
            principal_id="anonymous-public-user",
            role=ApplicationRole.PUBLIC,
            department=None,
        )

    # 2. Validate role
    role_str = x_principal_role.strip().upper()
    try:
        role = ApplicationRole(role_str)
    except ValueError:
        # Invalid role string -> Degrade safely to PUBLIC (never grant elevated privileges)
        return ApplicationPrincipal(
            principal_id=x_principal_id.strip(),
            role=ApplicationRole.PUBLIC,
            department=None,
        )

    # 3. Clean department if authority role
    clean_dept = x_principal_department.strip() if x_principal_department else None

    return ApplicationPrincipal(
        principal_id=x_principal_id.strip(),
        role=role,
        department=clean_dept,
    )
