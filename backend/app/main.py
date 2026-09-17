"""Main Application Entrypoint for JARVIS Civic Backend.

Phase 1: Canonical Data Contracts & API Scaffolding.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config.settings import settings
from app.api.health import router as health_router

app = FastAPI(
    title=settings.APP_NAME,
    description=(
        "JARVIS Civic — An AI-assisted civic decision-support and workflow prototype. "
        "Positioning: 'Speak. Report. Resolve.' "
        "Note: Generates AI-generated civic grievance records; not an official government system."
    ),
    version=settings.APP_VERSION,
    debug=settings.DEBUG,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)


@app.get("/")
def get_root():
    """Root metadata endpoint."""
    return {
        "service": settings.APP_NAME,
        "tagline": settings.APP_TAGLINE,
        "version": settings.APP_VERSION,
        "phase": "Phase 1 - Canonical Data Contracts & API Scaffolding",
        "status": "operational",
        "disclaimer": settings.DISCLAIMER,
        "endpoints": {
            "health": "/api/health",
            "docs": "/docs",
            "openapi": "/openapi.json",
        },
    }
