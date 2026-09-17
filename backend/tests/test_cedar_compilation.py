"""Verification of Cedar Schema and Policy Compilation.

Phase 3 Test Suite:
Validates that schema.cedarschema and policies.cedar compile cleanly
with the local cedarpy engine, with zero syntax errors.
"""

from pathlib import Path
import cedarpy
import pytest

from app.security.cedar_service import cedar_service


def test_cedar_schema_and_policies_file_existence():
    """Verify Cedar schema and policy files exist on disk."""
    assert cedar_service.schema_path.exists(), f"Missing schema at {cedar_service.schema_path}"
    assert cedar_service.policies_path.exists(), f"Missing policies at {cedar_service.policies_path}"


def test_cedar_service_initialization_health():
    """Verify CedarService initializes successfully and reports healthy."""
    assert cedar_service.is_healthy() is True


def test_cedar_schema_validation_passes():
    """Verify cedarpy.validate_policies compiles policies against the schema with 0 errors."""
    schema_text = cedar_service.schema_path.read_text(encoding="utf-8")
    policies_text = cedar_service.policies_path.read_text(encoding="utf-8")

    result = cedarpy.validate_policies(policies_text, schema_text)
    assert result.validation_passed is True, f"Policy validation failed: {getattr(result, 'errors', [])}"
    assert len(result.errors) == 0


def test_cedar_real_evaluation_not_mocked():
    """Verify Cedar engine actually evaluates an authorization request locally."""
    schema_text = cedar_service.schema_path.read_text(encoding="utf-8")
    policies_text = cedar_service.policies_path.read_text(encoding="utf-8")

    entities = [
        {
            "uid": {"type": "JarvisCivic::Citizen", "id": "test_citizen"},
            "attrs": {},
            "parents": [],
        },
        {
            "uid": {"type": "JarvisCivic::CivicCase", "id": "test_case"},
            "attrs": {
                "owner": {"__entity": {"type": "JarvisCivic::Citizen", "id": "test_citizen"}},
                "department": "DRAINAGE_STORMWATER",
                "status": "DOCKET_CREATED",
                "is_public": True,
            },
            "parents": [],
        },
    ]

    req = {
        "principal": {"type": "JarvisCivic::Citizen", "id": "test_citizen"},
        "action": {"type": "JarvisCivic::Action", "id": "read_own_case"},
        "resource": {"type": "JarvisCivic::CivicCase", "id": "test_case"},
        "context": {},
    }

    eval_result = cedarpy.is_authorized(req, policies_text, entities, schema=schema_text)
    assert eval_result.allowed is True
    assert eval_result.decision == cedarpy.Decision.Allow
