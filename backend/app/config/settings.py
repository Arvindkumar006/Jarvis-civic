"""Application Configuration and Settings for JARVIS Civic.

Zero-billing, local-first configuration. No AWS credentials or paid API keys required.
"""

from typing import List
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
    JARVIS_LLM_MODEL: str = "llama3.2:3b"
    LLM_TIMEOUT_SECONDS: float = 5.0
    FALLBACK_ENABLED: bool = True

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
