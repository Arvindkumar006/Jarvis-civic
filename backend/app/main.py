"""Main Application Entrypoint for JARVIS Civic Backend.

Phase 2: AWS Strands Agents & Local LLM Provider.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config.settings import settings
from app.api.health import router as health_router
from app.api.conversation import router as conversation_router

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

# Cross-Origin Resource Sharing (CORS)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(health_router)
app.include_router(conversation_router)


@app.get("/")
def get_root():
    """Root metadata endpoint."""
    return {
        "service": settings.APP_NAME,
        "tagline": settings.APP_TAGLINE,
        "version": settings.APP_VERSION,
        "phase": "Phase 2 - AWS Strands Agents & Local LLM Provider",
        "status": "operational",
        "disclaimer": settings.DISCLAIMER,
        "endpoints": {
            "health": "/api/health",
            "conversation": "/api/conversation",
            "docs": "/docs",
            "openapi": "/openapi.json",
        },
    }
