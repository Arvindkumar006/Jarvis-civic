"""Centralized Authorization Service for JARVIS Civic.

Phase 8.3 Security Architecture:
Serves as the canonical Policy Decision and Policy Enforcement abstraction layer.
Every protected operation must invoke AuthorizationService to evaluate permissions
against AWS Cedar compiled policies using the local Rust-backed cedarpy engine.

FAIL-CLOSED INVARIANTS:
1. Any error during policy evaluation, entity mapping, or engine failure strictly returns DENY.
2. If authorization is denied, enforce() raises HTTP 403 Forbidden with sanitized detail: 'Authorization denied'.
3. Passwords, password hashes, session tokens, and cookie values are strictly never included in Cedar entities or audit records.
"""

import logging
from typing import Any, Dict, Optional, Union
from fastapi import HTTPException, status

from app.models.security import (
    ApplicationPrincipal,
    ApplicationRole,
    AuthorizationDecision,
    AuthorizationRequest,
    CivicAction,
)
from app.security.audit import AuditEvent, audit_dispatcher
from app.security.cedar_service import CedarService, cedar_service

logger = logging.getLogger("jarvis.security.authorization")


class AuthorizationService:
    """Centralized authorization decision and enforcement service using AWS Cedar."""

    def __init__(self, cedar_pdp: Optional[CedarService] = None):
        self.cedar = cedar_pdp or cedar_service
        self.audit = audit_dispatcher

    def authorize(
        self,
        principal: Optional[ApplicationPrincipal],
        action: Union[CivicAction, str],
        resource_id: str,
        resource_type: str = "CivicCase",
        resource_owner: Optional[str] = None,
        resource_department: Optional[str] = None,
        resource_status: Optional[str] = None,
        is_public: bool = False,
        context: Optional[Dict[str, Any]] = None,
    ) -> AuthorizationDecision:
        """Evaluate an authorization query against the Cedar policy engine.

        Pure decision function: returns an AuthorizationDecision without raising an HTTP exception.
        Fails closed on any error, missing principal, or invalid entity.
        """
        # Fail-closed guard: missing or invalid principal
        if not principal or not getattr(principal, "principal_id", None):
            logger.warning("Authorization denied: missing or invalid principal.")
            return AuthorizationDecision(
                allowed=False,
                decision="DENY",
                reason="Missing or invalid principal (fail-closed)",
                diagnostics="Principal object is None or has empty principal_id",
            )

        # Fail-closed guard: unknown or unsupported role
        if not hasattr(principal, "role") or not isinstance(principal.role, ApplicationRole):
            try:
                # Attempt to parse role if provided as raw string
                _ = ApplicationRole(str(getattr(principal, "role", "")))
            except Exception:
                logger.warning("Authorization denied: unknown principal role '%s'.", getattr(principal, "role", None))
                return AuthorizationDecision(
                    allowed=False,
                    decision="DENY",
                    reason="Unknown or invalid principal role (fail-closed)",
                    diagnostics=f"Unrecognized role: {getattr(principal, 'role', None)}",
                )

        # Fail-closed guard: Cedar PDP initialization
        if not self.cedar or not self.cedar.is_healthy():
            logger.error("Authorization denied: Cedar PDP engine is not healthy or uninitialized.")
            return AuthorizationDecision(
                allowed=False,
                decision="DENY",
                reason="Cedar PDP engine unavailable (fail-closed)",
                diagnostics="Cedar service failed to compile or validate policies",
            )

        try:
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
            return self.cedar.authorize(auth_req)
        except Exception as exc:
            logger.error("Fail-closed exception in AuthorizationService.authorize: %s", exc, exc_info=True)
            return AuthorizationDecision(
                allowed=False,
                decision="DENY",
                reason="Internal authorization evaluation exception (fail-closed)",
                diagnostics=f"{type(exc).__name__}: {str(exc)}",
            )

    def enforce(
        self,
        principal: Optional[ApplicationPrincipal],
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
        """Enforce Cedar authorization policy for a requested operation.

        Evaluates decision via Cedar, streams decision to append-only audit trail,
        and strictly raises HTTPException(status_code=403, detail="Authorization denied")
        if access is denied.
        """
        decision = self.authorize(
            principal=principal,
            action=action,
            resource_id=resource_id,
            resource_type=resource_type,
            resource_owner=resource_owner,
            resource_department=resource_department,
            resource_status=resource_status,
            is_public=is_public,
            context=context,
        )

        # Record append-only audit event (sanitized: no credentials or secrets)
        p_id = getattr(principal, "principal_id", "unknown_principal") if principal else "missing_principal"
        p_role = getattr(principal.role, "value", str(principal.role)) if principal and hasattr(principal, "role") else "UNKNOWN"
        p_dept = getattr(principal, "department", None) if principal else None

        audit_event = AuditEvent(
            case_id=resource_id if resource_type == "CivicCase" else None,
            principal_id=p_id,
            principal_role=p_role,
            principal_department=p_dept,
            action=action.value if isinstance(action, CivicAction) else str(action),
            resource_id=resource_id,
            resource_type=resource_type,
            decision=decision.decision,
            outcome=decision.decision,
            reason=decision.reason,
            policy_id=decision.policy_id,
            correlation_id=correlation_id,
            department=resource_department or p_dept,
        )
        self.audit.record_event(audit_event)

        if not decision.allowed:
            action_str = action.value if isinstance(action, CivicAction) else str(action)
            logger.warning(
                "Access DENIED: principal '%s' (%s) attempting '%s' on %s '%s'. Reason: %s",
                p_id,
                p_role,
                action_str,
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
            "Access ALLOWED: principal '%s' (%s) performing '%s' on %s '%s'. Policy: %s",
            p_id,
            p_role,
            action.value if isinstance(action, CivicAction) else str(action),
            resource_type,
            resource_id,
            decision.policy_id,
        )
        return decision


# Global singleton authorization service
authorization_service = AuthorizationService()
