"""Policy Enforcement Point (PEP) for JARVIS Civic.

Phase 8.3 Security Architecture:
Delegates canonical enforcement and policy evaluation to the centralized
AuthorizationService while preserving seamless backwards compatibility for existing callers.
"""

from typing import Any, Dict, Optional, Union

from app.models.security import (
    ApplicationPrincipal,
    AuthorizationDecision,
    CivicAction,
)
from app.security.authorization_service import AuthorizationService, authorization_service


class PolicyEnforcementPoint:
    """Compatibility adapter delegating to canonical AuthorizationService."""

    def __init__(self, service: Optional[AuthorizationService] = None):
        self._service = service or authorization_service

    def enforce(
        self,
        principal: ApplicationPrincipal,
        action: Union[CivicAction, str],
        resource_id: str,
        resource_type: str = "CivicCase",
        resource_owner: Optional[str] = None,
        resource_department: Optional[str] = None,
        resource_status: Optional[str] = None,
        is_public: bool = False,
        context: Optional[Dict[str, Any]] = None,
        correlation_id: Optional[str] = None,
    ) -> AuthorizationDecision:
        """Enforce Cedar authorization policy via AuthorizationService."""
        return self._service.enforce(
            principal=principal,
            action=action,
            resource_id=resource_id,
            resource_type=resource_type,
            resource_owner=resource_owner,
            resource_department=resource_department,
            resource_status=resource_status,
            is_public=is_public,
            context=context,
            correlation_id=correlation_id,
        )


# Global singleton PEP instance
pep = PolicyEnforcementPoint()
