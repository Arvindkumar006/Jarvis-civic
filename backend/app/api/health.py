"""Health and Diagnostic Endpoints for JARVIS Civic."""

from fastapi import APIRouter
from app.config.settings import settings

router = APIRouter(prefix="/api", tags=["Health & Diagnostics"])


@router.get("/health")
def get_health():
    """Health check endpoint confirming service status and ethical disclaimer."""
    return {
        "status": "ok",
        "service": "jarvis-civic",
        "version": settings.APP_VERSION,
        "phase": "Phase 7 - Polish, Verification & Production Hardening",
        "disclaimer": settings.DISCLAIMER,
    }
