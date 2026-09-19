"""Notification Recipient Resolver for JARVIS Civic.

Phase 8.4: Backend-Authoritative Recipient Routing.
Adheres strictly to Correction 1:
1. Citizen resolved directly from case.owner_id in AccountRepository.
2. Authority resolved from AUTHORITY_OFFICER in matching department.
3. Fallback to MUNICIPAL_SUPERVISOR in matching department.
4. If neither exists, returns None (unroutable/fails closed; never invents fake officers).
"""

import logging
from typing import Optional
from pydantic import BaseModel

from app.models.security import ApplicationRole, CivicCaseRecord
from app.services.persistence.account_repository import account_repository

logger = logging.getLogger("jarvis.notifications.resolver")


class ResolvedRecipient(BaseModel):
    """Structured recipient descriptor derived strictly from server-side directory."""

    email: str
    display_name: str
    role: ApplicationRole
    principal_id: str
    is_specific_officer: bool = False


class NotificationRecipientResolver:
    """Resolves verified recipient accounts from backend directory."""

    def resolve_citizen_recipient(self, case: CivicCaseRecord) -> Optional[ResolvedRecipient]:
        """Resolve citizen account that created and owns the case."""
        if not case.owner_id:
            logger.warning("Case %s has no owner_id, citizen recipient unroutable", case.case_id)
            return None

        account = account_repository.get_by_principal_id(case.owner_id)
        if not account or not account.is_active or not account.email:
            logger.warning("Case %s owner_id '%s' not found or inactive in account directory", case.case_id, case.owner_id)
            return None

        return ResolvedRecipient(
            email=account.email,
            display_name=account.display_name or "Citizen User",
            role=account.role,
            principal_id=account.principal_id,
            is_specific_officer=False,
        )

    def resolve_authority_recipient(self, case: CivicCaseRecord) -> Optional[ResolvedRecipient]:
        """Resolve responsible authority recipient for the case department.

        Strict hierarchy:
        1. Active AUTHORITY_OFFICER with matching department
        2. Active MUNICIPAL_SUPERVISOR with matching department
        3. None (Fails closed as unroutable. Never invents fake officers or addresses).
        """
        department = case.department
        if not department:
            logger.warning("Case %s has no department, authority recipient unroutable", case.case_id)
            return None

        accounts = account_repository.list_accounts()

        # Tier 1: Look for active Authority Officer with matching department
        officer = next(
            (
                acc for acc in accounts
                if acc.is_active
                and acc.role == ApplicationRole.AUTHORITY_OFFICER
                and acc.department == department
            ),
            None,
        )
        if officer and officer.email:
            logger.debug("Resolved authority officer %s for department %s", officer.email, department)
            return ResolvedRecipient(
                email=officer.email,
                display_name=officer.display_name or f"{department} Officer",
                role=officer.role,
                principal_id=officer.principal_id,
                is_specific_officer=True,
            )

        # Tier 2: Look for active Municipal Supervisor with matching department
        supervisor = next(
            (
                acc for acc in accounts
                if acc.is_active
                and acc.role == ApplicationRole.MUNICIPAL_SUPERVISOR
                and acc.department == department
            ),
            None,
        )
        if supervisor and supervisor.email:
            logger.info("No officer found for %s; resolved supervisor %s", department, supervisor.email)
            return ResolvedRecipient(
                email=supervisor.email,
                display_name=supervisor.display_name or f"{department} Supervisor",
                role=supervisor.role,
                principal_id=supervisor.principal_id,
                is_specific_officer=False,
            )

        # Tier 3: Unroutable (fail closed)
        logger.warning("No active authority officer or supervisor found for department %s; case %s notification unroutable", department, case.case_id)
        return None


# Global singleton instance
recipient_resolver = NotificationRecipientResolver()
