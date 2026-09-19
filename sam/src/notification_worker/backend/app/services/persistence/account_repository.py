"""Account Repository for JARVIS Civic.

Phase 8.1: Backend-Owned Account Directory.
Manages user accounts with deterministic development seed data for all canonical roles.

SECURITY INVARIANTS:
1. Account role and department are strictly backend-owned.
2. Passwords are never persisted or returned plaintext; only Argon2id hashes are stored.
3. Authenticated PUBLIC account (public@jarviscivic.local) is distinct from anonymous requests.
"""

from abc import ABC, abstractmethod
from datetime import datetime, timezone
import logging
import threading
from typing import Dict, List, Optional

from app.config.settings import settings
from app.models.account import UserAccount
from app.models.enums import ControlledDepartment
from app.models.security import ApplicationRole
from app.security.hasher import password_hasher

logger = logging.getLogger("jarvis.persistence.account")


class AccountRepository(ABC):
    """Abstract interface for user account persistence."""

    @abstractmethod
    def get_by_email(self, email: str) -> Optional[UserAccount]:
        """Retrieve user account by normalized email address."""
        pass

    @abstractmethod
    def get_by_principal_id(self, principal_id: str) -> Optional[UserAccount]:
        """Retrieve user account by unique principal ID."""
        pass

    @abstractmethod
    def list_accounts(self) -> List[UserAccount]:
        """List all registered user accounts (internal administrative use only)."""
        pass

    @abstractmethod
    def save_account(self, account: UserAccount) -> UserAccount:
        """Persist or update a user account."""
        pass

    @abstractmethod
    def reset_seed_data(self) -> None:
        """Reset accounts to initial seeded state (primarily for test isolation)."""
        pass


class LocalAccountRepository(AccountRepository):
    """Thread-safe in-memory repository seeded with deterministic accounts for each role."""

    def __init__(self):
        self._accounts_by_email: Dict[str, UserAccount] = {}
        self._accounts_by_id: Dict[str, UserAccount] = {}
        self._lock = threading.Lock()
        self._seed_accounts()

    def _seed_accounts(self) -> None:
        """Seed deterministic development accounts using Argon2id hashes.

        Passwords are read dynamically from development configuration and securely hashed.
        """
        initial_password = settings.DEV_DEFAULT_PASSWORD
        default_hash = password_hasher.hash_password(initial_password)
        now = datetime.now(timezone.utc)

        seed_definitions = [
            # 1. Citizen
            UserAccount(
                principal_id="citizen-01",
                email="citizen@jarviscivic.local",
                password_hash=default_hash,
                display_name="Citizen User",
                role=ApplicationRole.CITIZEN,
                department=None,
                is_active=True,
                created_at=now,
                updated_at=now,
            ),
            # 2. Authority Officer — Drainage & Stormwater
            UserAccount(
                principal_id="authority-officer-01",
                email="officer@jarviscivic.local",
                password_hash=default_hash,
                display_name="Drainage Officer",
                role=ApplicationRole.AUTHORITY_OFFICER,
                department=ControlledDepartment.DRAINAGE_STORMWATER.value,
                is_active=True,
                created_at=now,
                updated_at=now,
            ),
            # 3. Authority Officer — Roads (Same role, different department scope)
            UserAccount(
                principal_id="authority-officer-roads-01",
                email="roads.officer@jarviscivic.local",
                password_hash=default_hash,
                display_name="Roads Officer",
                role=ApplicationRole.AUTHORITY_OFFICER,
                department=ControlledDepartment.PWD_ROADS.value,
                is_active=True,
                created_at=now,
                updated_at=now,
            ),
            # 4. Municipal Supervisor
            UserAccount(
                principal_id="supervisor-01",
                email="supervisor@jarviscivic.local",
                password_hash=default_hash,
                display_name="Drainage Supervisor",
                role=ApplicationRole.MUNICIPAL_SUPERVISOR,
                department=ControlledDepartment.DRAINAGE_STORMWATER.value,
                is_active=True,
                created_at=now,
                updated_at=now,
            ),
            # 5. Administrator
            UserAccount(
                principal_id="admin-01",
                email="admin@jarviscivic.local",
                password_hash=default_hash,
                display_name="System Administrator",
                role=ApplicationRole.ADMINISTRATOR,
                department=None,
                is_active=True,
                created_at=now,
                updated_at=now,
            ),
            # 6. Authenticated Public Account (Note: distinctly authenticated from anonymous access)
            UserAccount(
                principal_id="public-01",
                email="public@jarviscivic.local",
                password_hash=default_hash,
                display_name="Public Observer",
                role=ApplicationRole.PUBLIC,
                department=None,
                is_active=True,
                created_at=now,
                updated_at=now,
            ),
            # 7. Disabled Test Account
            UserAccount(
                principal_id="disabled-01",
                email="disabled@jarviscivic.local",
                password_hash=default_hash,
                display_name="Disabled Account",
                role=ApplicationRole.CITIZEN,
                department=None,
                is_active=False,
                created_at=now,
                updated_at=now,
            ),
        ]

        with self._lock:
            self._accounts_by_email.clear()
            self._accounts_by_id.clear()
            for acc in seed_definitions:
                self._accounts_by_email[acc.email.lower()] = acc
                self._accounts_by_id[acc.principal_id] = acc

        logger.info("LocalAccountRepository: Seeded %d development accounts successfully.", len(seed_definitions))

    def get_by_email(self, email: str) -> Optional[UserAccount]:
        if not email or not isinstance(email, str):
            return None
        normalized = email.strip().lower()
        with self._lock:
            return self._accounts_by_email.get(normalized)

    def get_by_principal_id(self, principal_id: str) -> Optional[UserAccount]:
        if not principal_id or not isinstance(principal_id, str):
            return None
        with self._lock:
            return self._accounts_by_id.get(principal_id)

    def list_accounts(self) -> List[UserAccount]:
        with self._lock:
            return list(self._accounts_by_email.values())

    def save_account(self, account: UserAccount) -> UserAccount:
        with self._lock:
            self._accounts_by_email[account.email.lower()] = account
            self._accounts_by_id[account.principal_id] = account
            return account

    def reset_seed_data(self) -> None:
        self._seed_accounts()


# Global default singleton instance
account_repository = LocalAccountRepository()
