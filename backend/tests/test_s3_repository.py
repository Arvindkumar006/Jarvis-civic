"""Unit Tests for Evidence Storage Repositories and Security Validations.

Phase 4 Test Suite:
Verifies file upload security checks (file size limits, permitted extensions,
MIME types, path traversal sanitization) and server-scoped key generation.
"""

from unittest.mock import MagicMock
from fastapi import HTTPException
import pytest

from app.services.persistence.local_repository import (
    LocalEvidenceRepository,
    sanitize_filename,
    validate_evidence_file,
)
from app.services.persistence.s3_evidence_repository import S3EvidenceRepository


def test_sanitize_filename_prevents_directory_traversal():
    """Verify path traversal filenames like '../../etc/passwd.jpg' are sanitized."""
    assert sanitize_filename("../../../etc/shadow.png") == "shadow.png"
    assert sanitize_filename("..\\..\\windows\\system32.jpg") == "system32.jpg"
    assert sanitize_filename("normal_photo.jpg") == "normal_photo.jpg"
    assert sanitize_filename("!@#$unsafe%.pdf") == "____unsafe_.pdf"


def test_validate_evidence_empty_file_rejected():
    """Empty files must raise HTTP 400."""
    with pytest.raises(HTTPException) as exc_info:
        validate_evidence_file(b"", "photo.jpg", "image/jpeg")
    assert exc_info.value.status_code == 400
    assert "empty" in exc_info.value.detail.lower()


def test_validate_evidence_file_size_limit():
    """Files exceeding 10MB limit must raise HTTP 413."""
    too_large = b"0" * (10 * 1024 * 1024 + 1)
    with pytest.raises(HTTPException) as exc_info:
        validate_evidence_file(too_large, "pothole.jpg", "image/jpeg")
    assert exc_info.value.status_code == 413
    assert "exceeds" in exc_info.value.detail.lower()


def test_validate_evidence_forbidden_extension():
    """Disallowed executable or script extensions must raise HTTP 400."""
    valid_bytes = b"sample content"
    for forbidden in ["script.sh", "malware.exe", "test.py", "archive.zip"]:
        with pytest.raises(HTTPException) as exc_info:
            validate_evidence_file(valid_bytes, forbidden, "text/plain")
        assert exc_info.value.status_code == 400
        assert "not permitted" in exc_info.value.detail.lower()


def test_validate_evidence_forbidden_mime_type():
    """Disallowed MIME types must raise HTTP 400."""
    valid_bytes = b"sample content"
    with pytest.raises(HTTPException) as exc_info:
        validate_evidence_file(valid_bytes, "doc.pdf", "application/x-msdownload")
    assert exc_info.value.status_code == 400
    assert "content-type" in exc_info.value.detail.lower()


def test_local_evidence_repository_upload_and_key_structure():
    """Verify local evidence repository generates server-scoped keys."""
    repo = LocalEvidenceRepository()
    repo.clear()

    content = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00" + b"image bytes for civic defect"
    meta = repo.upload_evidence(
        case_id="NS-CHN-2026-9E4B",
        file_bytes=content,
        filename="../../road_defect.jpg",
        content_type="image/jpeg",
    )

    # Verify server-generated evidence ID and key structure
    assert meta.case_id == "NS-CHN-2026-9E4B"
    assert meta.filename == "road_defect.jpg"
    assert meta.size_bytes == len(content)
    assert meta.object_key.startswith("cases/NS-CHN-2026-9E4B/evidence/")
    assert meta.object_key.endswith("/road_defect.jpg")
    assert meta.s3_uri == f"s3://jarvis-civic-evidence/{meta.object_key}"

    # Fetch metadata
    fetched = repo.get_evidence_metadata("NS-CHN-2026-9E4B", meta.evidence_id)
    assert fetched is not None
    assert fetched.evidence_id == meta.evidence_id


def test_s3_evidence_repository_with_mocked_boto3():
    """Verify S3EvidenceRepository calls put_object with server-scoped key and metadata."""
    repo = S3EvidenceRepository()
    mock_s3 = MagicMock()
    repo.s3_client = mock_s3

    content = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR" + b"evidence image payload"
    meta = repo.upload_evidence(
        case_id="NS-MUM-2026-3C4D",
        file_bytes=content,
        filename="drainage_clog.png",
        content_type="image/png",
    )

    assert meta.case_id == "NS-MUM-2026-3C4D"
    assert meta.filename == "drainage_clog.png"
    assert mock_s3.put_object.called

    call_kwargs = mock_s3.put_object.call_args[1]
    assert call_kwargs["Bucket"] == "jarvis-civic-evidence"
    assert call_kwargs["Key"] == meta.object_key
    assert call_kwargs["Body"] == content
    assert call_kwargs["ContentType"] == "image/png"
    assert call_kwargs["Metadata"]["case_id"] == "NS-MUM-2026-3C4D"
