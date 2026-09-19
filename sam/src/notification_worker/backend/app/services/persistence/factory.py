"""Persistence Repository Factory for JARVIS Civic.

Phase 4: Instantiates the active CaseRepository and EvidenceRepository based on
application configuration (settings.PERSISTENCE_BACKEND).

Supported modes:
- "local": In-memory thread-safe repositories (local fallback / tests)
- "localstack": DynamoDBCaseRepository and S3EvidenceRepository
"""

import logging
from typing import Optional, Tuple
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
_dynamo_audit_repo: Optional[DynamoDBAuditRepository] = None


def initialize_persistence_backend() -> None:
    """Initialize persistence resources and bind authoritative audit repository listener.

    Guarantees that persistent audit listeners are attached before any workflow mutations
    can generate audit events. Idempotent and thread-safe.
    """
    global _dynamo_audit_repo
    backend_mode = settings.PERSISTENCE_BACKEND.lower().strip()

    if backend_mode == "localstack":
        initialized = init_localstack_resources()
        if not initialized:
            raise ConnectionError(
                f"LocalStack persistence explicitly configured ('{backend_mode}') "
                f"but endpoint at '{settings.LOCALSTACK_ENDPOINT_URL}' is unreachable. "
                "Failing closed to prevent unpersisted data loss."
            )
        if _dynamo_audit_repo is None:
            _dynamo_audit_repo = DynamoDBAuditRepository()
        if _dynamo_audit_repo.record_event not in audit_dispatcher._listeners:
            audit_dispatcher.register_listener(_dynamo_audit_repo.record_event)
    else:
        if _local_audit_repo.record_event not in audit_dispatcher._listeners:
            audit_dispatcher.register_listener(_local_audit_repo.record_event)


# Initial default registration
initialize_persistence_backend()


def get_repositories() -> Tuple[CaseRepository, EvidenceRepository]:
    """Resolve and return active (CaseRepository, EvidenceRepository)."""
    initialize_persistence_backend()
    backend_mode = settings.PERSISTENCE_BACKEND.lower().strip()

    if backend_mode == "localstack":
        logger.info("Using LocalStack persistence backend (%s)...", settings.LOCALSTACK_ENDPOINT_URL)
        return DynamoDBCaseRepository(), S3EvidenceRepository()

    # Default to local in-memory fallback
    logger.debug("Using in-memory local persistence repository.")
    return _local_case_repo, _local_evidence_repo


def get_audit_repository() -> AuditRepository:
    """Resolve and return active AuditRepository."""
    initialize_persistence_backend()
    backend_mode = settings.PERSISTENCE_BACKEND.lower().strip()

    if backend_mode == "localstack":
        if _dynamo_audit_repo is None:
            raise RuntimeError("DynamoDB audit repository unexpectedly not initialized.")
        return _dynamo_audit_repo

    return _local_audit_repo
