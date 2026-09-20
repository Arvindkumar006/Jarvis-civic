"""Application Configuration and Settings for JARVIS Civic.

Zero-billing, local-first configuration. No AWS credentials or paid API keys required.
"""

from typing import List, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration loaded from environment or defaults."""

    APP_NAME: str = "JARVIS Civic"
    APP_TAGLINE: str = "Speak. Report. Resolve."
    APP_VERSION: str = "0.4.0"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    HOST: str = "127.0.0.1"
    PORT: int = 8000

    # Local LLM & Ollama Configuration (Zero-cost, local-only)
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_TEXT_MODEL: str = "llama3.2:3b"
    OLLAMA_VISION_MODEL: str = "moondream"
    JARVIS_LLM_MODEL: str = "llama3.2:3b"
    LLM_TIMEOUT_SECONDS: float = 5.0
    FALLBACK_ENABLED: bool = True

    # Authentication & Session Configuration (Phase 8.1)
    AUTH_SESSION_TTL_SECONDS: int = 86400  # 24 hours
    AUTH_COOKIE_NAME: str = "jarvis_session_id"
    AUTH_COOKIE_SECURE: bool = False  # False for local HTTP, True in production
    AUTH_COOKIE_SAMESITE: str = "lax"
    DEV_DEFAULT_PASSWORD: str = "JarvisCivic2026!"

    # Persistence & LocalStack Configuration (Local AWS-compatible, zero-cost)
    PERSISTENCE_BACKEND: str = "local"  # "local" or "localstack"
    LOCALSTACK_ENDPOINT_URL: str = "http://localhost:4566"
    DYNAMODB_TABLE_NAME: str = "JarvisCivicCases"
    DYNAMODB_AUDIT_TABLE_NAME: str = "JarvisCivicAudit"
    S3_BUCKET_NAME: str = "jarvis-civic-evidence"
    AWS_REGION: str = "us-east-1"
    AWS_ACCESS_KEY_ID: str = "test"
    AWS_SECRET_ACCESS_KEY: str = "test"
    MAX_EVIDENCE_SIZE_BYTES: int = 10 * 1024 * 1024  # 10 MB
    ALLOWED_EVIDENCE_EXTENSIONS: List[str] = [
        ".jpg", ".jpeg", ".png", ".pdf", ".mp3", ".wav", ".txt"
    ]
    ALLOWED_EVIDENCE_MIME_TYPES: List[str] = [
        "image/jpeg", "image/png", "application/pdf", "audio/mpeg", "audio/wav", "text/plain"
    ]

    # CORS origins
    ALLOWED_ORIGINS: List[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
    ]

    # Notification & SMTP Configuration (Phase 8.4)
    SMTP_HOST: str = "localhost"
    SMTP_PORT: int = 1025
    SMTP_USERNAME: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    SMTP_SENDER_EMAIL: str = "notifications@jarviscivic.local"
    SMTP_SENDER_NAME: str = "JARVIS Civic Dispatch"
    SMTP_USE_TLS: bool = False
    SMTP_TIMEOUT_SECONDS: float = 5.0
    MAILPIT_WEB_URL: str = "http://localhost:8025"
    DYNAMODB_NOTIFICATION_TABLE_NAME: str = "JarvisCivicNotifications"
    # Notification Execution Mode (Phase 8.5): "DIRECT" or "SAM_LOCAL"
    NOTIFICATION_EXECUTION_MODE: str = "DIRECT"

    # OpenSearch Configuration (Phase 8.6)
    OPENSEARCH_HOST: str = "localhost"
    OPENSEARCH_PORT: int = 9200
    OPENSEARCH_INDEX_NAME: str = "jarvis-civic-dockets-v1"
    OPENSEARCH_INDEX_ALIAS: str = "jarvis-civic-dockets"
    OPENSEARCH_USE_SSL: bool = False
    OPENSEARCH_TIMEOUT_SECONDS: int = 5
    OPENSEARCH_MAX_RETRIES: int = 3

    # Explicit Ethical & Legal Disclaimer
    DISCLAIMER: str = (
        "JARVIS Civic is an AI-assisted civic decision-support and workflow prototype. "
        "Generated records are AI-generated civic grievance records and do not represent "
        "official government petition submission, municipal department acceptance, or legal resolution."
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
