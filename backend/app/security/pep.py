"""Policy Enforcement Point (PEP) for JARVIS Civic.

Phase 3 Security Architecture:
Intercepts all protected civic operations, invokes the local Cedar Policy Decision Point (PDP),
logs the outcome to the audit stream, and halts execution with HTTP 403 Forbidden on denial.

FAIL-CLOSED INVARIANT:
If Cedar denies access, or if any policy evaluation error occurs, the PEP strictly
raises HTTP 403 Forbidden with a sanitized message: 'Authorization denied'.
Internal Cedar diagnostics are never leaked to API clients.
"""

import logging
from typing import Any, Dict, Optional
from fastapi import HTTPException, status

from app.models.security import (
    ApplicationPrincipal,
    AuthorizationDecision,
    AuthorizationRequest,
    CivicAction,
)
from app.security.audit import AuditEvent, audit_dispatcher
from app.security.cedar_service import cedar_service

logger = logging.getLogger("jarvis.security.pep")


class PolicyEnforcementPoint:
    """Centralized enforcement layer for all protected civic actions."""

    def __init__(self):
        self.cedar = cedar_service
        self.audit = audit_dispatcher

    def enforce(
        self,
        principal: ApplicationPrincipal,
        action: CivicAction,
        resource_id: str,
        resource_type: str = "CivicCase",
        resource_owner: Optional[str] = None,
        resource_department: Optional[str] = None,
        resource_status: Optional[str] = None,
        is_public: bool = False,
        context: Optional[Dict[str, Any]] = None,
        correlation_id: Optional[str] = None,
    ) -> AuthorizationDecision:
        """Enforce Cedar authorization policy for a requested operation.

        Raises HTTPException(403) if denied or if evaluation fails.
        """
        auth_req = AuthorizationRequest(
            principal=principal,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            resource_owner=resource_owner,
            resource_department=resource_department,
            resource_status=resource_status,
            is_public=is_public,
            context=context or {},
        )

        decision = self.cedar.authorize(auth_req)

        # Record application-level audit event
        audit_event = AuditEvent(
            principal_id=principal.principal_id,
            principal_role=principal.role.value,
            action=action.value if isinstance(action, CivicAction) else str(action),
            resource_id=resource_id,
            resource_type=resource_type,
            decision=decision.decision,
            reason=decision.reason,
            policy_id=decision.policy_id,
            correlation_id=correlation_id,
            department=resource_department or principal.department,
        )
        self.audit.record_event(audit_event)

        if not decision.allowed:
            logger.warning(
                "Access DENIED for principal '%s' (%s) attempting '%s' on %s '%s'. Reason: %s",
                principal.principal_id,
                principal.role.value,
                action.value if isinstance(action, CivicAction) else str(action),
                resource_type,
                resource_id,
                decision.reason,
            )
            # Fail closed with safe, sanitized error response
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Authorization denied",
            )

        logger.info(
            "Access ALLOWED for principal '%s' (%s) performing '%s' on %s '%s'. Policy: %s",
            principal.principal_id,
            principal.role.value,
            action.value if isinstance(action, CivicAction) else str(action),
            resource_type,
            resource_id,
            decision.policy_id,
        )
        return decision


# Global singleton PEP instance
pep = PolicyEnforcementPoint()
