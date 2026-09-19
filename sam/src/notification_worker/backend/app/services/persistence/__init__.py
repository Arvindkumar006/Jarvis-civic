"""Persistence package for JARVIS Civic (Phase 4)."""

from app.services.persistence.interface import CaseRepository, EvidenceRepository
from app.services.persistence.local_repository import (
    LocalCaseRepository,
    LocalEvidenceRepository,
)
from app.services.persistence.dynamodb_repository import DynamoDBCaseRepository
from app.services.persistence.s3_evidence_repository import S3EvidenceRepository
from app.services.persistence.factory import get_repositories
from app.services.persistence.localstack_init import init_localstack_resources
from app.services.persistence.serialization import (
    case_record_to_dynamodb,
    dynamodb_to_case_record,
)

__all__ = [
    "CaseRepository",
    "EvidenceRepository",
    "LocalCaseRepository",
    "LocalEvidenceRepository",
    "DynamoDBCaseRepository",
    "S3EvidenceRepository",
    "get_repositories",
    "init_localstack_resources",
    "case_record_to_dynamodb",
    "dynamodb_to_case_record",
]
