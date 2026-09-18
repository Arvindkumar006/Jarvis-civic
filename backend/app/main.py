import logging
from http import HTTPStatus
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config.settings import settings
from app.api.health import router as health_router
from app.api.conversation import router as conversation_router
from app.api.cases import router as cases_router
from app.api.tracking import router as tracking_router
from app.api.audit import router as audit_router

logger = logging.getLogger("jarvis.main")

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


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Fail-safe handler for unhandled internal exceptions, preventing stack trace leaks."""
    logger.error("Unhandled internal exception on %s %s: %s", request.method, request.url.path, exc, exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "An internal server error occurred while processing the request. Please retry."},
    )


# Register routers
app.include_router(health_router)
app.include_router(conversation_router)
app.include_router(cases_router)
app.include_router(tracking_router)
app.include_router(audit_router)


@app.get("/")
def get_root():
    """Root metadata endpoint."""
    return {
        "service": settings.APP_NAME,
        "tagline": settings.APP_TAGLINE,
        "version": settings.APP_VERSION,
        "phase": "Phase 7 - Polish, Verification & Production Hardening",
        "status": "operational",
        "disclaimer": settings.DISCLAIMER,
        "endpoints": {
            "health": "/api/health",
            "conversation": "/api/conversation",
            "cases": "/api/cases",
            "tracking": "/api/tracking",
            "audit": "/api/audit/logs",
            "docs": "/docs",
            "openapi": "/openapi.json",
        },
    }

