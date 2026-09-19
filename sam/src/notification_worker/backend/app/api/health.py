"""Health and Diagnostic Endpoints for JARVIS Civic."""

from fastapi import APIRouter, Response, status
from app.config.settings import settings
from app.security.cedar_service import cedar_service
from app.llm.ollama_provider import OllamaProvider
from app.llm.provider import LLMStatus

router = APIRouter(tags=["Health & Diagnostics"])
_llm_provider = OllamaProvider()


@router.get("/health")
@router.get("/api/health")
@router.get("/health/live")
@router.get("/api/health/live")
def get_health_live():
    """Liveness probe confirming basic API service operability and ethical disclaimer."""
    return {
        "status": "ok",
        "service": "jarvis-civic",
        "version": settings.APP_VERSION,
        "phase": "Phase 7 - Polish, Verification & Hardening",
        "disclaimer": settings.DISCLAIMER,
    }


@router.get("/health/ready")
@router.get("/api/health/ready")
async def get_health_ready(response: Response):
    """Readiness probe truthfully reporting subsystem availability.

    Never exposes internal credentials or raw stack traces.
    """
    dependencies = {}
    is_ready = True

    # 1. Check Cedar PDP Engine
    try:
        if cedar_service is not None and cedar_service.is_healthy():
            dependencies["cedar_engine"] = "available"
        else:
            dependencies["cedar_engine"] = "unavailable"
            is_ready = False
    except Exception:
        dependencies["cedar_engine"] = "unavailable"
        is_ready = False

    # 2. Check Persistence Subsystem
    backend_mode = settings.PERSISTENCE_BACKEND.lower().strip()
    if backend_mode == "localstack":
        try:
            import httpx
            r = httpx.get(f"{settings.LOCALSTACK_ENDPOINT_URL}/_localstack/health", timeout=1.5)
            if r.status_code == 200:
                data = r.json()
                services = data.get("services", {})
                d_ok = services.get("dynamodb") in ["available", "running"]
                s_ok = services.get("s3") in ["available", "running"]
                if d_ok and s_ok:
                    dependencies["persistence"] = "localstack_healthy"
                else:
                    dependencies["persistence"] = "localstack_degraded"
                    is_ready = False
            else:
                dependencies["persistence"] = "localstack_unreachable"
                is_ready = False
        except Exception:
            dependencies["persistence"] = "localstack_unreachable"
            is_ready = False
    else:
        dependencies["persistence"] = "in_memory_ready"

    # 3. Check LLM provider
    try:
        llm_stat = await _llm_provider.check_health()
        dependencies["llm"] = "available" if llm_stat == LLMStatus.LLM_AVAILABLE else "offline_fallback"
    except Exception:
        dependencies["llm"] = "offline_fallback"

    # 4. Check OpenSearch Search Index Subsystem (Phase 8.6)
    try:
        from app.services.search.opensearch_service import opensearch_service
        os_health = opensearch_service.health_check()
        dependencies["opensearch"] = os_health.get("status", "unavailable")
    except Exception:
        dependencies["opensearch"] = "unavailable"

    overall_status = "ready" if is_ready else "not_ready"
    if not is_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return {
        "status": overall_status,
        "service": "jarvis-civic",
        "backend_mode": backend_mode,
        "dependencies": dependencies,
        "disclaimer": settings.DISCLAIMER,
    }
