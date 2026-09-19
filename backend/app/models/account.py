"""User Account and Authentication Models for JARVIS Civic.

Phase 8.1: Backend-Owned Authentication Foundation.
Defines canonical user account records, authenticated principal representation,
login request contracts, and safe user account responses.

SECURITY INVARIANTS:
1. Role and department are strictly backend-owned properties.
2. Plaintext passwords and password hashes are NEVER exposed in API responses or logs.
3. AuthenticatedPrincipal is resolved server-side from active sessions.
"""

from datetime import datetime, timezone
import re
from typing import Optional
from pydantic import BaseModel, Field, field_validator

from app.models.security import ApplicationPrincipal, ApplicationRole


class UserAccount(BaseModel):
    """Canonical backend-owned user account record.

    Contains sensitive security credentials (password_hash) stored strictly server-side.
    NEVER return this model directly from API endpoints.
    """

    principal_id: str = Field(..., description="Unique principal ID (e.g. citizen-01, officer-01)")
    email: str = Field(..., description="Unique normalized email address")
    password_hash: str = Field(..., description="Argon2id password hash")
    display_name: str = Field(..., description="User's human-readable display name")
    role: ApplicationRole = Field(..., description="Authoritative backend-assigned role")
    department: Optional[str] = Field(default=None, description="Department scope for authority roles")
    is_active: bool = Field(default=True, description="Account active status")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AuthenticatedPrincipal(ApplicationPrincipal):
    """Authoritative principal resolved from an active backend session.

    Consumed by downstream request handlers, Cedar authorization, and audit logging.
    Inherits from ApplicationPrincipal for full compatibility with existing security layers.
    """

    email: str = Field(..., description="Authenticated user email")
    display_name: str = Field(..., description="Display name")
    session_id: Optional[str] = Field(default=None, description="Active session ID")
    authenticated_at: Optional[datetime] = Field(default=None, description="Timestamp when authenticated")
    is_authenticated: bool = Field(default=True, description="True for verified server-side session")


class UserAccountResponse(BaseModel):
    """Safe projection of user account for client consumption.

    Strictly excludes password_hash, passwords, and server secrets.
    """

    principal_id: str
    email: str
    display_name: str
    role: ApplicationRole
    department: Optional[str] = None
    is_active: bool
    created_at: datetime


class LoginRequest(BaseModel):
    """Client payload for authentication login."""

    email: str = Field(..., min_length=3, max_length=255, description="Account email address")
    password: str = Field(..., min_length=1, max_length=256, description="Account password")

    @field_validator("email", mode="after")
    @classmethod
    def validate_email(cls, v: str) -> str:
        normalized = v.strip().lower()
        if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", normalized):
            raise ValueError("Invalid email format")
        return normalized

    @field_validator("password", mode="after")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Password cannot be empty")
        return v
