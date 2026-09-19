"""Deterministic File Validation for JARVIS Civic Evidence.

Phase 8.7: Implements robust, deterministic pre-validation of uploaded evidence
before persistence or AI analysis. Enforces size boundaries, path traversal
neutralization, MIME matching, binary magic byte verification, and SHA-256 calculation.
"""

import hashlib
import os
import re
from typing import Tuple

from app.config.settings import settings
from app.models.evidence import (
    DeterministicValidationResult,
    DeterministicValidationStatus,
)


def sanitize_filename(filename: str) -> str:
    """Sanitize filename to prevent directory traversal or invalid characters.

    Strips directory separators, relative path markers (../, ..\\), control chars,
    and leading hidden file dots.
    """
    if not filename:
        return "evidence_file.bin"
    # Replace backslashes with slashes
    normalized = filename.replace("\\", "/").rstrip("/")
    # Take only the base component
    base = normalized.split("/")[-1]
    # Remove all dangerous characters except alphanumeric, dot, underscore, dash
    clean = re.sub(r"[^a-zA-Z0-9._-]", "_", base)
    # Strip leading dots to prevent hidden/system files
    clean = clean.lstrip(".")
    return clean or "evidence_file.bin"


def detect_magic_signature(file_bytes: bytes) -> Tuple[DeterministicValidationStatus, str]:
    """Inspect binary header to detect actual file type."""
    if not file_bytes:
        return DeterministicValidationStatus.EMPTY_FILE, "application/octet-stream"

    length = len(file_bytes)

    # JPEG: starts with \xff\xd8\xff
    if length >= 3 and file_bytes.startswith(b"\xff\xd8\xff"):
        return DeterministicValidationStatus.VALID, "image/jpeg"

    # PNG: starts with \x89PNG\r\n\x1a\n
    if length >= 8 and file_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return DeterministicValidationStatus.VALID, "image/png"

    # WebP: RIFF....WEBP
    if length >= 12 and file_bytes.startswith(b"RIFF") and file_bytes[8:12] == b"WEBP":
        return DeterministicValidationStatus.VALID, "image/webp"

    # PDF: starts with %PDF-
    if length >= 5 and file_bytes.startswith(b"%PDF-"):
        return DeterministicValidationStatus.VALID, "application/pdf"

    # WAV: RIFF....WAVE
    if length >= 12 and file_bytes.startswith(b"RIFF") and file_bytes[8:12] == b"WAVE":
        return DeterministicValidationStatus.VALID, "audio/wav"

    # MP3: ID3 or sync frame
    if length >= 3 and file_bytes.startswith(b"ID3"):
        return DeterministicValidationStatus.VALID, "audio/mpeg"
    if length >= 2 and file_bytes[0] == 0xFF and (file_bytes[1] & 0xE0) == 0xE0:
        return DeterministicValidationStatus.VALID, "audio/mpeg"

    # Plain text: valid UTF-8
    try:
        sample = file_bytes[:4096]
        # Check for null bytes which indicate binary executable / binary file
        if b"\x00" in sample:
            return DeterministicValidationStatus.CORRUPT_FILE, "application/octet-stream"
        sample.decode("utf-8")
        return DeterministicValidationStatus.VALID, "text/plain"
    except UnicodeDecodeError:
        pass

    return DeterministicValidationStatus.MAGIC_BYTES_MISMATCH, "application/octet-stream"


def validate_evidence_file_deterministic(
    file_bytes: bytes,
    filename: str,
    declared_content_type: str,
) -> DeterministicValidationResult:
    """Execute complete deterministic validation pipeline.

    Order:
    1. Non-empty check
    2. Size boundary check
    3. Filename sanitization & extension extraction
    4. Allowed extension check
    5. Allowed MIME check
    6. Magic byte inspection
    7. Extension vs Magic Bytes consistency check
    8. SHA-256 digest computation
    """
    clean_name = sanitize_filename(filename)
    declared_mime = (declared_content_type or "application/octet-stream").lower().strip()
    size_bytes = len(file_bytes)
    sha256_hash = hashlib.sha256(file_bytes).hexdigest()

    # 1. Non-empty check
    if size_bytes == 0:
        return DeterministicValidationResult(
            status=DeterministicValidationStatus.EMPTY_FILE,
            is_valid=False,
            sha256=sha256_hash,
            size_bytes=0,
            sanitized_filename=clean_name,
            declared_content_type=declared_mime,
            detected_content_type="application/octet-stream",
            error_message="Evidence file cannot be empty (0 bytes).",
        )

    # 2. Maximum file size check
    max_bytes = settings.MAX_EVIDENCE_SIZE_BYTES
    if size_bytes > max_bytes:
        return DeterministicValidationResult(
            status=DeterministicValidationStatus.FILE_TOO_LARGE,
            is_valid=False,
            sha256=sha256_hash,
            size_bytes=size_bytes,
            sanitized_filename=clean_name,
            declared_content_type=declared_mime,
            detected_content_type="application/octet-stream",
            error_message=f"File size ({size_bytes} bytes) exceeds limit of {max_bytes} bytes ({max_bytes // (1024*1024)}MB).",
        )

    # 3. Extension check
    ext = os.path.splitext(clean_name)[1].lower()
    if not ext or ext not in settings.ALLOWED_EVIDENCE_EXTENSIONS:
        return DeterministicValidationResult(
            status=DeterministicValidationStatus.UNSUPPORTED_FORMAT,
            is_valid=False,
            sha256=sha256_hash,
            size_bytes=size_bytes,
            sanitized_filename=clean_name,
            declared_content_type=declared_mime,
            detected_content_type="application/octet-stream",
            error_message=f"File extension '{ext}' is not supported.",
        )

    # 4. Declared MIME check
    if declared_mime not in settings.ALLOWED_EVIDENCE_MIME_TYPES:
        return DeterministicValidationResult(
            status=DeterministicValidationStatus.INVALID_TYPE,
            is_valid=False,
            sha256=sha256_hash,
            size_bytes=size_bytes,
            sanitized_filename=clean_name,
            declared_content_type=declared_mime,
            detected_content_type="application/octet-stream",
            error_message=f"Declared Content-Type '{declared_mime}' is not permitted.",
        )

    # 5. Magic signature inspection
    sig_status, detected_mime = detect_magic_signature(file_bytes)
    if sig_status != DeterministicValidationStatus.VALID:
        return DeterministicValidationResult(
            status=sig_status,
            is_valid=False,
            sha256=sha256_hash,
            size_bytes=size_bytes,
            sanitized_filename=clean_name,
            declared_content_type=declared_mime,
            detected_content_type=detected_mime,
            error_message=f"File content does not match magic signature ({sig_status.value}).",
        )

    # 6. Check extension vs detected MIME consistency
    ext_mime_map = {
        ".jpg": ["image/jpeg"],
        ".jpeg": ["image/jpeg"],
        ".png": ["image/png"],
        ".webp": ["image/webp"],
        ".pdf": ["application/pdf"],
        ".wav": ["audio/wav"],
        ".mp3": ["audio/mpeg"],
        ".txt": ["text/plain"],
    }
    allowed_mimes_for_ext = ext_mime_map.get(ext, [])
    if detected_mime not in allowed_mimes_for_ext:
        return DeterministicValidationResult(
            status=DeterministicValidationStatus.MIME_MISMATCH,
            is_valid=False,
            sha256=sha256_hash,
            size_bytes=size_bytes,
            sanitized_filename=clean_name,
            declared_content_type=declared_mime,
            detected_content_type=detected_mime,
            error_message=f"File content does not match magic signature: extension '{ext}' does not match detected format '{detected_mime}'.",
        )

    return DeterministicValidationResult(
        status=DeterministicValidationStatus.VALID,
        is_valid=True,
        sha256=sha256_hash,
        size_bytes=size_bytes,
        sanitized_filename=clean_name,
        declared_content_type=declared_mime,
        detected_content_type=detected_mime,
        error_message=None,
    )
