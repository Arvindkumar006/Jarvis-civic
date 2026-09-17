"""S3 Evidence Repository for JARVIS Civic (LocalStack).

Phase 4: Manages civic evidence upload, security validation, and scoped key generation
targeting the LocalStack S3 endpoint (http://localhost:4566).
"""

from datetime import datetime, timezone
import logging
import secrets
from typing import Optional
import boto3
from botocore.exceptions import ClientError

from app.config.settings import settings
from app.models.security import EvidenceMetadata
from app.services.persistence.interface import EvidenceRepository
from app.services.persistence.local_repository import validate_evidence_file

logger = logging.getLogger("jarvis.persistence.s3")


class S3EvidenceRepository(EvidenceRepository):
    """LocalStack S3 implementation for civic evidence storage."""

    def __init__(
        self,
        endpoint_url: Optional[str] = None,
        bucket_name: Optional[str] = None,
        region_name: Optional[str] = None,
    ):
        self.endpoint_url = endpoint_url or settings.LOCALSTACK_ENDPOINT_URL
        self.bucket_name = bucket_name or settings.S3_BUCKET_NAME
        self.region_name = region_name or settings.AWS_REGION

        self.s3_client = boto3.client(
            "s3",
            endpoint_url=self.endpoint_url,
            region_name=self.region_name,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        )

    def upload_evidence(
        self,
        case_id: str,
        file_bytes: bytes,
        filename: str,
        content_type: str,
    ) -> EvidenceMetadata:
        """Validate and upload civic evidence to S3 bucket.

        SECURITY CONSTRAINTS:
        - Object key is generated server-side; client cannot choose object path.
        - File is validated for non-empty, max 10MB size, permitted extension, and MIME type.
        """
        clean_filename = validate_evidence_file(file_bytes, filename, content_type)

        # Server-generated evidence identifier
        evidence_id = secrets.token_hex(6)

        # Scoped object key: cases/{case_id}/evidence/{evidence_id}/{sanitized_filename}
        object_key = f"cases/{case_id}/evidence/{evidence_id}/{clean_filename}"
        s3_uri = f"s3://{self.bucket_name}/{object_key}"

        try:
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=object_key,
                Body=file_bytes,
                ContentType=content_type,
                Metadata={
                    "case_id": case_id,
                    "evidence_id": evidence_id,
                    "original_filename": clean_filename,
                },
            )
            logger.info("S3: Uploaded evidence '%s' for case '%s'", object_key, case_id)
        except ClientError as exc:
            logger.error("S3 upload failed for '%s': %s", object_key, exc)
            raise

        return EvidenceMetadata(
            evidence_id=evidence_id,
            case_id=case_id,
            object_key=object_key,
            s3_uri=s3_uri,
            filename=clean_filename,
            content_type=content_type,
            size_bytes=len(file_bytes),
            uploaded_at=datetime.now(timezone.utc),
        )

    def get_evidence_metadata(self, case_id: str, evidence_id: str) -> Optional[EvidenceMetadata]:
        prefix = f"cases/{case_id}/evidence/{evidence_id}/"
        try:
            response = self.s3_client.list_objects_v2(
                Bucket=self.bucket_name,
                Prefix=prefix,
                MaxKeys=1,
            )
            contents = response.get("Contents", [])
            if not contents:
                return None

            obj_key = contents[0]["Key"]
            head = self.s3_client.head_object(Bucket=self.bucket_name, Key=obj_key)
            filename = obj_key.split("/")[-1]

            return EvidenceMetadata(
                evidence_id=evidence_id,
                case_id=case_id,
                object_key=obj_key,
                s3_uri=f"s3://{self.bucket_name}/{obj_key}",
                filename=filename,
                content_type=head.get("ContentType", "application/octet-stream"),
                size_bytes=head.get("ContentLength", 0),
                uploaded_at=head.get("LastModified", datetime.now(timezone.utc)),
            )
        except ClientError as exc:
            logger.warning("Failed to fetch evidence metadata for %s: %s", prefix, exc)
            return None
