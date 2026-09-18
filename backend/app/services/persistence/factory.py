"""Persistence Repository Factory for JARVIS Civic.

Phase 4: Instantiates the active CaseRepository and EvidenceRepository based on
application configuration (settings.PERSISTENCE_BACKEND).

Supported modes:
- "local": In-memory thread-safe repositories (local fallback / tests)
- "localstack": DynamoDBCaseRepository and S3EvidenceRepository
"""

import logging
from typing import Tuple
from app.config.settings import settings
from app.security.audit import audit_dispatcher
from app.services.persistence.interface import (
    AuditRepository,
    CaseRepository,
    EvidenceRepository,
)
from app.services.persistence.local_repository import (
    LocalAuditRepository,
    LocalCaseRepository,
    LocalEvidenceRepository,
)
from app.services.persistence.dynamodb_repository import (
    DynamoDBAuditRepository,
    DynamoDBCaseRepository,
)
from app.services.persistence.s3_evidence_repository import S3EvidenceRepository
from app.services.persistence.localstack_init import init_localstack_resources

logger = logging.getLogger("jarvis.persistence.factory")

# Global singleton fallback instances
_local_case_repo = LocalCaseRepository()
_local_evidence_repo = LocalEvidenceRepository()
_local_audit_repo = LocalAuditRepository()

# Wire local audit repo to audit dispatcher listener
audit_dispatcher.register_listener(_local_audit_repo.record_event)


def get_repositories() -> Tuple[CaseRepository, EvidenceRepository]:
    """Resolve and return active (CaseRepository, EvidenceRepository)."""
    backend_mode = settings.PERSISTENCE_BACKEND.lower().strip()

    if backend_mode == "localstack":
        logger.info("Initializing LocalStack persistence backend (%s)...", settings.LOCALSTACK_ENDPOINT_URL)
        # Verify LocalStack is reachable and resources initialized
        initialized = init_localstack_resources()
        if not initialized:
            raise ConnectionError(
                f"LocalStack persistence explicitly configured ('{backend_mode}') "
                f"but endpoint at '{settings.LOCALSTACK_ENDPOINT_URL}' is unreachable. "
                "Failing closed to prevent unpersisted data loss."
            )
        return DynamoDBCaseRepository(), S3EvidenceRepository()

    # Default to local in-memory fallback
    logger.debug("Using in-memory local persistence repository.")
    return _local_case_repo, _local_evidence_repo


def get_audit_repository() -> AuditRepository:
    """Resolve and return active AuditRepository."""
    backend_mode = settings.PERSISTENCE_BACKEND.lower().strip()

    if backend_mode == "localstack":
        initialized = init_localstack_resources()
        if not initialized:
            raise ConnectionError(
                f"LocalStack persistence explicitly configured ('{backend_mode}') "
                f"but endpoint at '{settings.LOCALSTACK_ENDPOINT_URL}' is unreachable."
            )
        repo = DynamoDBAuditRepository()
        audit_dispatcher.register_listener(repo.record_event)
        return repo

    return _local_audit_repo
