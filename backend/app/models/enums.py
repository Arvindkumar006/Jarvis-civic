"""Controlled Enums for JARVIS Civic.

These enums establish the canonical data contracts for civic intake,
department routing recommendations, urgency levels, case lifecycle stages,
and evidence categorization.
"""

from enum import Enum


class CivicIntent(str, Enum):
    """Controlled taxonomy of recognized civic complaints."""

    WATERLOGGING = "WATERLOGGING"
    ROAD_POTHOLE = "ROAD_POTHOLE"
    STREETLIGHT_OUTAGE = "STREETLIGHT_OUTAGE"
    GARBAGE_ACCUMULATION = "GARBAGE_ACCUMULATION"
    DRAINAGE_BLOCKAGE = "DRAINAGE_BLOCKAGE"
    WATER_SUPPLY_ISSUE = "WATER_SUPPLY_ISSUE"
    ELECTRICITY_OUTAGE = "ELECTRICITY_OUTAGE"
    PUBLIC_INFRASTRUCTURE_DAMAGE = "PUBLIC_INFRASTRUCTURE_DAMAGE"
    OTHER_CIVIC_ISSUE = "OTHER_CIVIC_ISSUE"


class ControlledDepartment(str, Enum):
    """Controlled Recommended Departments for civic defect routing.

    NOTE: These are AI-recommended jurisdictions for triage assistance.
    They do NOT represent official governmental assignments or petition acceptance.
    """

    MUNICIPAL_CORPORATION = "MUNICIPAL_CORPORATION"
    PWD_ROADS = "PWD_ROADS"
    WATER_SUPPLY = "WATER_SUPPLY"
    ELECTRICITY_UTILITY = "ELECTRICITY_UTILITY"
    WASTE_MANAGEMENT = "WASTE_MANAGEMENT"
    DRAINAGE_STORMWATER = "DRAINAGE_STORMWATER"
    OTHER_MANUAL_REVIEW = "OTHER_MANUAL_REVIEW"


class UrgencyLevel(str, Enum):
    """Objective urgency classification for civic risk assessment."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class CaseStatus(str, Enum):
    """Lifecycle states of an AI-generated civic grievance record."""

    DRAFT = "DRAFT"
    DOCKET_CREATED = "DOCKET_CREATED"
    ROUTING_PREPARED = "ROUTING_PREPARED"
    SUBMISSION_READY = "SUBMISSION_READY"
    UNDER_REVIEW = "UNDER_REVIEW"
    RESOLVED = "RESOLVED"


# Centralized canonical lifecycle transition rules (single-step forward progression only)
VALID_STATUS_TRANSITIONS: dict[CaseStatus, list[CaseStatus]] = {
    CaseStatus.DRAFT: [CaseStatus.DOCKET_CREATED],
    CaseStatus.DOCKET_CREATED: [CaseStatus.ROUTING_PREPARED],
    CaseStatus.ROUTING_PREPARED: [CaseStatus.SUBMISSION_READY],
    CaseStatus.SUBMISSION_READY: [CaseStatus.UNDER_REVIEW],
    CaseStatus.UNDER_REVIEW: [CaseStatus.RESOLVED],
    CaseStatus.RESOLVED: [],
}


def validate_status_transition(current_status: CaseStatus, new_status: CaseStatus) -> None:
    """Validate that status transition follows canonical single-step forward progression.

    Enforces strict forward lifecycle stages:
    01 DOCKET_CREATED -> 02 ROUTING_PREPARED -> 03 SUBMISSION_READY -> 04 UNDER_REVIEW -> 05 RESOLVED.
    Rejects skipped stages, backwards transitions, same-status loops, and arbitrary assignment with HTTP 409 Conflict.
    """
    from fastapi import HTTPException, status

    allowed_targets = VALID_STATUS_TRANSITIONS.get(current_status, [])
    if new_status not in allowed_targets:
        expected = allowed_targets[0].value if allowed_targets else "None (terminal state)"
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Invalid status transition: cannot transition from '{current_status.value}' "
                f"to '{new_status.value}'. Expected next stage: '{expected}'."
            ),
        )


class EvidenceType(str, Enum):
    """Supported evidence types for civic complaints."""

    TEXT = "TEXT"
    IMAGE = "IMAGE"
    AUDIO = "AUDIO"
    DOCUMENT = "DOCUMENT"
