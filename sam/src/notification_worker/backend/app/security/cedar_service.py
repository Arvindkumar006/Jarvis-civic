"""Local AWS Cedar Authorization Service (Policy Decision Point) for JARVIS Civic.

Evaluates application-level authorization requests against Cedar policies
compiled with the official local cedarpy engine.

Fails closed on any error, syntax fault, or missing entity context.
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
import cedarpy

from app.models.security import (
    ApplicationPrincipal,
    ApplicationRole,
    AuthorizationDecision,
    AuthorizationRequest,
    CivicAction,
)

logger = logging.getLogger("jarvis.security.cedar")


class CedarService:
    """Cedar Policy Decision Point (PDP) using local Rust-backed cedarpy."""

    def __init__(
        self,
        schema_path: Optional[Path] = None,
        policies_path: Optional[Path] = None,
    ):
        base_dir = Path(__file__).resolve().parent / "policies"
        self.schema_path = schema_path or (base_dir / "schema.cedarschema")
        self.policies_path = policies_path or (base_dir / "policies.cedar")

        self.schema_str: str = ""
        self.policies_str: str = ""
        self._initialized: bool = False

        self._load_and_validate()

    def _load_and_validate(self) -> None:
        """Load schema and policies from disk and validate them."""
        try:
            if not self.schema_path.exists():
                raise FileNotFoundError(f"Cedar schema file not found at: {self.schema_path}")
            if not self.policies_path.exists():
                raise FileNotFoundError(f"Cedar policies file not found at: {self.policies_path}")

            self.schema_str = self.schema_path.read_text(encoding="utf-8")
            self.policies_str = self.policies_path.read_text(encoding="utf-8")

            validation_result = cedarpy.validate_policies(self.policies_str, self.schema_str)
            if not validation_result.validation_passed:
                errors = [getattr(e, "error", str(e)) for e in getattr(validation_result, "errors", [])]
                raise ValueError(f"Cedar policy validation failed: {'; '.join(errors)}")

            self._initialized = True
            logger.info("Cedar PDP initialized and policies successfully validated.")
        except Exception as exc:
            self._initialized = False
            logger.error("Failed to initialize Cedar PDP: %s", exc, exc_info=True)

    def is_healthy(self) -> bool:
        """Check if Cedar PDP is loaded and valid."""
        return self._initialized

    def _build_entities(self, auth_req: AuthorizationRequest) -> List[Dict[str, Any]]:
        """Construct Cedar entity graph adhering to JarvisCivic schema.

        CRITICAL SECURITY INVARIANT:
        If an authority principal or resource lacks a department, assign disjoint sentinel values
        ('__PRINCIPAL_NO_DEPT__' vs '__RESOURCE_NO_DEPT__') so empty strings can NEVER match.
        """
        principal = auth_req.principal
        entities: List[Dict[str, Any]] = []

        # 1. Principal Entity
        entity_type = principal.cedar_entity_type
        principal_type = f"JarvisCivic::{entity_type}"
        principal_attrs: Dict[str, Any] = {}
        if principal.role in (ApplicationRole.AUTHORITY_OFFICER, ApplicationRole.MUNICIPAL_SUPERVISOR):
            principal_attrs["department"] = (principal.department or "").strip() or "__PRINCIPAL_NO_DEPT__"

        entities.append({
            "uid": {"type": principal_type, "id": principal.principal_id or "unknown_principal"},
            "attrs": principal_attrs,
            "parents": [],
        })

        # 2. Resource Entity & Associated Entities
        if auth_req.resource_type == "CivicCase":
            owner_id = auth_req.resource_owner or "unknown_owner"
            # If owner is not already the principal, include owner entity in graph
            if owner_id != principal.principal_id:
                entities.append({
                    "uid": {"type": "JarvisCivic::Citizen", "id": owner_id},
                    "attrs": {},
                    "parents": [],
                })

            case_dept = (auth_req.resource_department or "").strip() or "__RESOURCE_NO_DEPT__"
            case_attrs: Dict[str, Any] = {
                "owner": {"__entity": {"type": "JarvisCivic::Citizen", "id": owner_id}},
                "department": case_dept,
                "status": auth_req.resource_status or "DRAFT",
                "is_public": bool(auth_req.is_public),
            }

            entities.append({
                "uid": {"type": "JarvisCivic::CivicCase", "id": auth_req.resource_id or "unknown_case"},
                "attrs": case_attrs,
                "parents": [],
            })

        elif auth_req.resource_type == "AuditRecord":
            audit_dept = (auth_req.resource_department or "").strip() or "__RESOURCE_NO_DEPT__"
            entities.append({
                "uid": {"type": "JarvisCivic::AuditRecord", "id": auth_req.resource_id or "unknown_audit"},
                "attrs": {
                    "department": audit_dept,
                },
                "parents": [],
            })
        elif auth_req.resource_type == "CivicDocketSearch":
            search_dept = (auth_req.resource_department or "").strip() or "__RESOURCE_NO_DEPT__"
            entities.append({
                "uid": {"type": "JarvisCivic::CivicDocketSearch", "id": auth_req.resource_id or search_dept},
                "attrs": {
                    "department": search_dept,
                },
                "parents": [],
            })
        else:
            raise ValueError(f"Unknown Cedar resource type: '{auth_req.resource_type}'")

        return entities

    def authorize(self, auth_req: AuthorizationRequest) -> AuthorizationDecision:
        """Evaluate an authorization request against loaded Cedar policies.

        Fails closed on any error or if the engine is uninitialized.
        """
        if not self._initialized:
            logger.error("Cedar PDP not initialized. Failing closed with DENY.")
            return AuthorizationDecision(
                allowed=False,
                decision="DENY",
                reason="Cedar PDP uninitialized or policy compilation failed",
                diagnostics="Service not initialized",
            )

        try:
            # Build entities
            entities = self._build_entities(auth_req)

            # Build Cedar request
            action_id = auth_req.action.value if isinstance(auth_req.action, CivicAction) else str(auth_req.action)
            request = {
                "principal": {
                    "type": f"JarvisCivic::{auth_req.principal.cedar_entity_type}",
                    "id": auth_req.principal.principal_id,
                },
                "action": {
                    "type": "JarvisCivic::Action",
                    "id": action_id,
                },
                "resource": {
                    "type": f"JarvisCivic::{auth_req.resource_type}",
                    "id": auth_req.resource_id,
                },
                "context": auth_req.context or {},
            }

            # Evaluate with local cedarpy
            result = cedarpy.is_authorized(
                request=request,
                policies=self.policies_str,
                entities=entities,
                schema=self.schema_str,
            )

            is_allowed = bool(result.allowed)
            decision_str = "ALLOW" if is_allowed else "DENY"

            matched_reasons = []
            if hasattr(result.diagnostics, "reasons"):
                matched_reasons = list(result.diagnostics.reasons)

            policy_id = matched_reasons[0] if matched_reasons else None
            reason_msg = f"Matched policy: {policy_id}" if is_allowed else "No permit policy satisfied (default deny)"

            return AuthorizationDecision(
                allowed=is_allowed,
                decision=decision_str,
                reason=reason_msg,
                policy_id=policy_id,
                diagnostics=f"Reasons: {matched_reasons}",
            )

        except Exception as exc:
            # FAIL CLOSED: Any evaluation or syntax exception results in DENY
            logger.error("Exception during Cedar authorization evaluation: %s", exc, exc_info=True)
            return AuthorizationDecision(
                allowed=False,
                decision="DENY",
                reason="Authorization evaluation error (fail-closed)",
                diagnostics=f"{type(exc).__name__}: {str(exc)}",
            )


# Global singleton instance
cedar_service = CedarService()
