"""Authentication API Endpoints for JARVIS Civic.

Phase 8.1: Backend-Owned Authentication API.
Implements secure login, session verification (/me), and logout with HttpOnly cookies.

SECURITY INVARIANTS:
1. Passwords and password hashes are NEVER returned in responses or logged.
2. The client cannot choose or override its role, principal_id, or department.
3. HttpOnly cookie (jarvis_session_id) is the canonical authentication transport.
4. Anonymous visitor is never converted into authenticated PUBLIC account.
"""

import logging
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from app.config.settings import settings
from app.models.account import LoginRequest, UserAccountResponse
from app.security.hasher import password_hasher
from app.security.session import session_store
from app.services.persistence.account_repository import account_repository

logger = logging.getLogger("jarvis.api.auth")

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


@router.post(
    "/login",
    response_model=UserAccountResponse,
    summary="Authenticate user credentials and establish server session",
    status_code=status.HTTP_200_OK,
)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
) -> UserAccountResponse:
    """Authenticate account credentials server-side and issue an HttpOnly session cookie.

    SECURITY GUARANTEES:
    - Verifies password with Argon2id constant-time verification.
    - Resolves role and department authoritatively from backend account storage.
    - Ignores any client-supplied role, principal ID, or department headers/fields.
    - Sets secure HttpOnly cookie `jarvis_session_id`.
    - Never returns password_hash or sensitive internal credentials.
    """
    normalized_email = payload.email.strip().lower()

    # Locate account by normalized email
    account = account_repository.get_by_email(normalized_email)
    if not account:
        logger.warning("Failed login attempt for unknown email: %s", normalized_email)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )

    # Check active status
    if not account.is_active:
        logger.warning("Failed login attempt for disabled account: %s", normalized_email)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account is disabled. Please contact an administrator.",
        )

    # Verify password against stored Argon2id hash
    if not password_hasher.verify_password(payload.password, account.password_hash):
        logger.warning("Failed login attempt: incorrect password for email: %s", normalized_email)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )

    # Create server-side session
    session = session_store.create_session(account)

    # Set secure HttpOnly cookie
    response.set_cookie(
        key=settings.AUTH_COOKIE_NAME,
        value=session.session_id,
        httponly=True,
        secure=settings.AUTH_COOKIE_SECURE,
        samesite=settings.AUTH_COOKIE_SAMESITE,
        max_age=settings.AUTH_SESSION_TTL_SECONDS,
        path="/",
    )

    logger.info(
        "Successful login for principal '%s' (role: %s, dept: %s)",
        account.principal_id,
        account.role.value,
        account.department or "None",
    )

    return UserAccountResponse(
        principal_id=account.principal_id,
        email=account.email,
        display_name=account.display_name,
        role=account.role,
        department=account.department,
        is_active=account.is_active,
        created_at=account.created_at,
    )


@router.get(
    "/me",
    response_model=UserAccountResponse,
    summary="Get current authenticated account from session",
    status_code=status.HTTP_200_OK,
)
def get_current_user(request: Request) -> UserAccountResponse:
    """Resolve currently authenticated backend identity from the HttpOnly session cookie.

    SECURITY GUARANTEES:
    - Returns 401 if unauthenticated, missing cookie, or expired session.
    - NEVER automatically promotes an anonymous visitor to authenticated PUBLIC account.
    - Returns strictly safe account projection.
    """
    session_id = request.cookies.get(settings.AUTH_COOKIE_NAME)
    if not session_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated. Please log in.",
        )

    session = session_store.get_session(session_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session has expired or is invalid. Please log in again.",
        )

    account = account_repository.get_by_principal_id(session.principal_id)
    if not account or not account.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account is inactive or no longer exists.",
        )

    return UserAccountResponse(
        principal_id=account.principal_id,
        email=account.email,
        display_name=account.display_name,
        role=account.role,
        department=account.department,
        is_active=account.is_active,
        created_at=account.created_at,
    )


@router.post(
    "/logout",
    summary="Revoke session and clear session cookie",
    status_code=status.HTTP_200_OK,
)
def logout(request: Request, response: Response) -> dict:
    """Invalidate active server session and delete the HttpOnly session cookie.

    Safe to invoke idempotently even if no session currently exists.
    """
    session_id = request.cookies.get(settings.AUTH_COOKIE_NAME)
    if session_id:
        session_store.invalidate_session(session_id)

    response.delete_cookie(
        key=settings.AUTH_COOKIE_NAME,
        path="/",
        httponly=True,
        samesite=settings.AUTH_COOKIE_SAMESITE,
    )

    return {"detail": "Logged out successfully."}
