"""Serialization and Deserialization for DynamoDB Civic Case Items.

Phase 4: Explicit, safe conversion between CivicCaseRecord and DynamoDB items.
Ensures PIN codes (e.g. '012345') remain strings, enums serialize to strings,
and UTC timestamps format deterministically.
"""

from datetime import datetime, timezone
from typing import Any, Dict
from app.models.enums import CaseStatus
from app.models.security import CivicCaseRecord


def case_record_to_dynamodb(record: CivicCaseRecord) -> Dict[str, Any]:
    """Convert a CivicCaseRecord into a DynamoDB item dict.

    CRITICAL INVARIANTS:
    - pincode MUST remain a string to preserve leading zeroes.
    - status must serialize to its enum string value.
    - timestamps must serialize to ISO-8601 UTC strings.
    - is_public must be a strict boolean.
    - resolution_notes and evidence_uris must serialize to lists of strings.
    """
    item: Dict[str, Any] = {
        "case_id": str(record.case_id),
        "owner_id": str(record.owner_id),
        "department": str(record.department),
        "status": record.status.value if isinstance(record.status, CaseStatus) else str(record.status),
        "description": str(record.description),
        "location": str(record.location),
        "is_public": bool(record.is_public),
        "resolution_notes": list(record.resolution_notes or []),
        "evidence_uris": list(record.evidence_uris or []),
        "created_at": record.created_at.isoformat(),
        "updated_at": record.updated_at.isoformat(),
    }

    # Optional attributes (only include if present to keep DynamoDB items clean)
    if record.landmark is not None:
        item["landmark"] = str(record.landmark)

    if record.pincode is not None:
        # STRICT TYPE PRESERVATION: Pin code is always string
        item["pincode"] = str(record.pincode).strip()

    if record.urgency is not None:
        item["urgency"] = str(record.urgency)

    if record.urgency_rationale is not None:
        item["urgency_rationale"] = str(record.urgency_rationale)

    if record.session_id is not None:
        item["session_id"] = str(record.session_id)

    return item


def dynamodb_to_case_record(item: Dict[str, Any]) -> CivicCaseRecord:
    """Convert a DynamoDB item dict into a canonical CivicCaseRecord."""
    # Parse status enum safely
    raw_status = item.get("status", "DOCKET_CREATED")
    try:
        status_enum = CaseStatus(raw_status)
    except ValueError:
        status_enum = CaseStatus.DOCKET_CREATED

    # Parse timestamps
    created_str = item.get("created_at")
    if created_str:
        try:
            created_at = datetime.fromisoformat(created_str)
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
        except Exception:
            created_at = datetime.now(timezone.utc)
    else:
        created_at = datetime.now(timezone.utc)

    updated_str = item.get("updated_at")
    if updated_str:
        try:
            updated_at = datetime.fromisoformat(updated_str)
            if updated_at.tzinfo is None:
                updated_at = updated_at.replace(tzinfo=timezone.utc)
        except Exception:
            updated_at = datetime.now(timezone.utc)
    else:
        updated_at = datetime.now(timezone.utc)

    # Preserve pincode as string
    pincode_val = item.get("pincode")
    pincode_str = str(pincode_val).strip() if pincode_val is not None else None

    return CivicCaseRecord(
        case_id=item["case_id"],
        owner_id=item["owner_id"],
        department=item["department"],
        status=status_enum,
        description=item["description"],
        location=item["location"],
        landmark=item.get("landmark"),
        pincode=pincode_str,
        urgency=item.get("urgency"),
        urgency_rationale=item.get("urgency_rationale"),
        session_id=item.get("session_id"),
        is_public=bool(item.get("is_public", True)),
        resolution_notes=list(item.get("resolution_notes") or []),
        evidence_uris=list(item.get("evidence_uris") or []),
        created_at=created_at,
        updated_at=updated_at,
    )
