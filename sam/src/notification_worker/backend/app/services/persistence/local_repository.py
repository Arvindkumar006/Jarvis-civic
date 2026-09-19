"""In-Memory Local Fallback Repositories for JARVIS Civic.

Phase 4: Provides zero-dependency, thread-safe local implementations of
CaseRepository and EvidenceRepository for development, offline environments,
and fast unit testing.
"""

from datetime import datetime, timezone
import os
import re
import secrets
import threading
from typing import Dict, List, Optional

from fastapi import HTTPException, status
from app.config.settings import settings
from app.models.common import generate_case_id
from app.models.enums import CaseStatus, ControlledDepartment
from app.models.security import (
    CaseHistoryItem,
    CivicCaseCreateRequest,
    CivicCaseRecord,
    EvidenceMetadata,
)
from app.security.audit import AuditEvent, audit_dispatcher
from app.services.persistence.interface import (
    AuditRepository,
    CaseRepository,
    EvidenceRepository,
)


def sanitize_filename(filename: str) -> str:
    """Sanitize filename to prevent directory traversal or invalid characters across platforms."""
    normalized = filename.replace("\\", "/").rstrip("/")
    base = normalized.split("/")[-1]
    clean = re.sub(r"[^a-zA-Z0-9._-]", "_", base)
    clean = clean.lstrip(".")  # Prevent hidden files
    return clean or "evidence_file"


def validate_magic_bytes(file_bytes: bytes, ext: str) -> None:
    """Validate file signatures (magic bytes) for binary civic evidence formats."""

    if ext in [".jpg", ".jpeg"]:
        if len(file_bytes) < 3 or not file_bytes.startswith(b"\xff\xd8\xff"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File content does not match JPEG magic signature",
            )
    elif ext == ".png":
        if len(file_bytes) < 8 or not file_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File content does not match PNG magic signature",
            )
    elif ext == ".pdf":
        if len(file_bytes) < 5 or not file_bytes.startswith(b"%PDF-"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File content does not match PDF magic signature",
            )
    elif ext == ".wav":
        if len(file_bytes) < 12 or not (file_bytes.startswith(b"RIFF") and file_bytes[8:12] == b"WAVE"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File content does not match WAV magic signature",
            )
    elif ext == ".mp3":
        is_id3 = file_bytes.startswith(b"ID3")
        is_sync = len(file_bytes) >= 2 and file_bytes[0] == 0xFF and (file_bytes[1] & 0xE0) == 0xE0
        if not (is_id3 or is_sync):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File content does not match MP3 audio signature",
            )
    elif ext == ".txt":
        try:
            file_bytes[:4096].decode("utf-8")
        except UnicodeDecodeError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File content does not match valid UTF-8 text encoding",
            )


def validate_evidence_file(
    file_bytes: bytes,
    filename: str,
    content_type: str,
) -> str:
    """Validate evidence file upload against security constraints."""
    if not file_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Evidence file cannot be empty",
        )

    if len(file_bytes) > settings.MAX_EVIDENCE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"Evidence file size exceeds maximum limit of {settings.MAX_EVIDENCE_SIZE_BYTES // (1024 * 1024)} MB",
        )

    clean_name = sanitize_filename(filename)
    ext = os.path.splitext(clean_name)[1].lower()

    if ext not in settings.ALLOWED_EVIDENCE_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File extension '{ext}' is not permitted for civic evidence",
        )

    if content_type and content_type.lower() not in settings.ALLOWED_EVIDENCE_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Content-Type '{content_type}' is not permitted for civic evidence",
        )

    validate_magic_bytes(file_bytes, ext)

    return clean_name


class LocalCaseRepository(CaseRepository):
    """Thread-safe in-memory case repository implementing CaseRepository."""

    def __init__(self):
        self._cases: Dict[str, CivicCaseRecord] = {}
        self._case_history: Dict[str, List[CaseHistoryItem]] = {}
        self._lock = threading.Lock()

    def create_case(
        self,
        request: CivicCaseCreateRequest,
        owner_id: str,
        case_id: Optional[str] = None,
    ) -> CivicCaseRecord:
        with self._lock:
            cid = case_id or generate_case_id()
            now = datetime.now(timezone.utc)
            record = CivicCaseRecord(
                case_id=cid,
                owner_id=owner_id,
                department=(
                    request.department.value
                    if isinstance(request.department, ControlledDepartment)
                    else str(request.department)
                ),
                status=CaseStatus.DOCKET_CREATED,
                description=request.description,
                location=request.location,
                pincode=request.pincode,
                is_public=request.is_public,
                latitude=request.latitude,
                longitude=request.longitude,
                location_source=request.location_source,
                resolution_notes=[],
                evidence_uris=[],
                created_at=now,
                updated_at=now,
            )
            self._cases[cid] = record
            self._case_history[cid] = [
                CaseHistoryItem(
                    milestone_id=f"ms-{secrets.token_hex(6)}",
                    status=CaseStatus.DOCKET_CREATED.value,
                    label="Docket Created",
                    timestamp=now,
                    department=record.department,
                    description="Initial Civic Docket recorded in system",
                    actor_role="CITIZEN",
                    note="Initial Civic Docket Created",
                )
            ]
            return record

    def get_case(self, case_id: str) -> Optional[CivicCaseRecord]:
        with self._lock:
            return self._cases.get(case_id)

    def get_case_history(self, case_id: str) -> List[CaseHistoryItem]:
        with self._lock:
            return list(self._case_history.get(case_id, []))

    def update_case(
        self,
        case_id: str,
        description: Optional[str] = None,
        location: Optional[str] = None,
        pincode: Optional[str] = None,
    ) -> Optional[CivicCaseRecord]:
        with self._lock:
            record = self._cases.get(case_id)
            if not record:
                return None
            if description is not None:
                record.description = description
            if location is not None:
                record.location = location
            if pincode is not None:
                record.pincode = pincode
            record.updated_at = datetime.now(timezone.utc)
            return record

    def update_case_status(
        self,
        case_id: str,
        new_status: CaseStatus,
        note: Optional[str] = None,
        actor_label: Optional[str] = None,
        expected_current_status: Optional[CaseStatus] = None,
    ) -> Optional[CivicCaseRecord]:
        with self._lock:
            record = self._cases.get(case_id)
            if not record:
                return None
            if expected_current_status is not None and record.status != expected_current_status:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        f"Concurrent modification conflict: case status is currently '{record.status.value}', "
                        f"expected '{expected_current_status.value}'."
                    ),
                )
            record.status = new_status
            record.updated_at = datetime.now(timezone.utc)
            if note:
                record.resolution_notes.append(note)

            # Record in history
            if case_id not in self._case_history:
                self._case_history[case_id] = []

            status_val = new_status.value if isinstance(new_status, CaseStatus) else str(new_status)
            status_title = status_val.replace("_", " ").title()
            self._case_history[case_id].append(
                CaseHistoryItem(
                    milestone_id=f"ms-{secrets.token_hex(6)}",
                    status=status_val,
                    label=status_title,
                    timestamp=record.updated_at,
                    department=record.department,
                    description=f"Case status updated to {status_title}",
                    actor_role=actor_label or "AUTHORITY_OFFICER",
                    note=note,
                )
            )
            return record

    def add_resolution_note(
        self,
        case_id: str,
        note: str,
        actor_label: Optional[str] = None,
    ) -> Optional[CivicCaseRecord]:
        with self._lock:
            record = self._cases.get(case_id)
            if not record:
                return None
            record.resolution_notes.append(note)
            record.updated_at = datetime.now(timezone.utc)

            if case_id not in self._case_history:
                self._case_history[case_id] = []
            status_val = record.status.value if isinstance(record.status, CaseStatus) else str(record.status)
            self._case_history[case_id].append(
                CaseHistoryItem(
                    milestone_id=f"ms-{secrets.token_hex(6)}",
                    status=status_val,
                    label="Resolution Note Added",
                    timestamp=record.updated_at,
                    department=record.department,
                    description="Official workflow note appended by authority",
                    actor_role=actor_label or "AUTHORITY_OFFICER",
                    note=note,
                )
            )
            return record

    def add_evidence_uri(self, case_id: str, uri: str) -> Optional[CivicCaseRecord]:
        with self._lock:
            record = self._cases.get(case_id)
            if not record:
                return None
            if uri not in record.evidence_uris:
                record.evidence_uris.append(uri)
            record.updated_at = datetime.now(timezone.utc)
            return record

    def list_all_cases(self) -> List[CivicCaseRecord]:
        with self._lock:
            return list(self._cases.values())

    def clear(self) -> None:
        with self._lock:
            self._cases.clear()
            self._case_history.clear()


class LocalAuditRepository(AuditRepository):
    """Thread-safe in-memory audit log store implementing AuditRepository."""

    def __init__(self):
        self._events: List[AuditEvent] = []
        self._lock = threading.Lock()

    def record_event(self, event: AuditEvent) -> AuditEvent:
        with self._lock:
            self._events.append(event)
            return event

    def get_events(self, department: Optional[str] = None, limit: int = 100) -> List[AuditEvent]:
        with self._lock:
            events = self._events
            if department:
                events = [
                    e for e in events
                    if getattr(e, "principal_department", None) == department
                    or (getattr(e, "metadata", None) or {}).get("department") == department
                ]
            return list(reversed(events[-limit:]))

    def get_events_for_case(self, case_id: str) -> List[AuditEvent]:
        with self._lock:
            return [e for e in self._events if e.case_id == case_id]

    def clear(self) -> None:
        with self._lock:
            self._events.clear()


class LocalEvidenceRepository(EvidenceRepository):
    """Thread-safe in-memory evidence store implementing EvidenceRepository."""

    def __init__(self):
        self._evidence: Dict[str, bytes] = {}
        self._metadata: Dict[str, EvidenceMetadata] = {}
        self._lock = threading.Lock()

    def upload_evidence(
        self,
        case_id: str,
        file_bytes: bytes,
        filename: str,
        content_type: str,
    ) -> EvidenceMetadata:
        clean_filename = validate_evidence_file(file_bytes, filename, content_type)

        # Server-side generated evidence ID
        evidence_id = secrets.token_hex(6)
        object_key = f"cases/{case_id}/evidence/{evidence_id}/{clean_filename}"
        s3_uri = f"s3://{settings.S3_BUCKET_NAME}/{object_key}"

        meta = EvidenceMetadata(
            evidence_id=evidence_id,
            case_id=case_id,
            object_key=object_key,
            s3_uri=s3_uri,
            filename=clean_filename,
            content_type=content_type,
            size_bytes=len(file_bytes),
            uploaded_at=datetime.now(timezone.utc),
        )

        with self._lock:
            self._evidence[object_key] = file_bytes
            self._metadata[f"{case_id}:{evidence_id}"] = meta

        return meta

    def get_evidence_metadata(self, case_id: str, evidence_id: str) -> Optional[EvidenceMetadata]:
        with self._lock:
            return self._metadata.get(f"{case_id}:{evidence_id}")

    def clear(self) -> None:
        with self._lock:
            self._evidence.clear()
            self._metadata.clear()
