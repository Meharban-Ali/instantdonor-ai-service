# ai-service/routes/health.py

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse

from core.config import Settings, get_settings
from models.response_schemas import HealthResponse  # ✅ Bug Fix 1
from services.health_service import HealthService, get_health_service

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Health"])


# ═══════════════════════════════════════════════════════════
# GET /health — Main health check
# ═══════════════════════════════════════════════════════════
#
# SOLID:
#   S → Sirf HTTP handling
#   D → HealthService + Settings inject
#
# ✅ Bug Fix 1: Correct import
# ✅ Bug Fix 2: Depends — no module-level settings
# ✅ Bug Fix 3: Standard status values
# ✅ Bug Fix 4: UTC timestamp
# ✅ Bug Fix 5: 503 on unhealthy
#
# Logic:
#   HealthService → sab components check
#   healthy/degraded → 200 OK
#   unhealthy → 503 Service Unavailable
#
# System Design:
#   Kubernetes liveness probe → /health/live
#   Kubernetes readiness probe → /health/ready
#   Monitoring → /health/detailed

@router.get(
    "/health",
    response_model = HealthResponse,
    summary        = "Service health check",
    description    = (
            "Returns service health. "
            "200=healthy/degraded, 503=unhealthy. "
            "Used by Kubernetes probes."
    ),
    responses = {
        200: {"description": "Service healthy or degraded"},
        503: {"description": "Service unhealthy — DB down"},
    }
)
def health_check(
        # ✅ Bug Fix 2: Depends — not module-level
        settings:       Settings      = Depends(get_settings),
        health_service: HealthService = Depends(get_health_service),
) -> JSONResponse:
    """
    Main health check endpoint.

    SOLID S: Sirf HTTP handling — logic HealthService mein.

    ✅ Bug Fix 2: Module-level settings removed
    ✅ Bug Fix 3: Standard status values
    ✅ Bug Fix 4: UTC timezone
    ✅ Bug Fix 5: 503 on critical failure
    """
    try:
        result = health_service.check_health()

        # ✅ Bug Fix 4: UTC timestamp
        response_data = HealthResponse(
            status          = result.overall_status,  # ✅ Bug Fix 3
            service         = settings.app_name,      # ✅ Bug Fix 2
            version         = settings.app_version,
            commit          = settings.git_sha,
            db_connected    = result.db_connected,
            redis_connected = result.redis_connected,
            timestamp       = datetime.now(timezone.utc),  # ✅ Bug Fix 4
        )

        # ✅ Bug Fix 5: 503 agar critical component fail (unhealthy), 200 on healthy/degraded
        http_status = (
            status.HTTP_503_SERVICE_UNAVAILABLE
            if result.overall_status == "unhealthy"
            else status.HTTP_200_OK
        )

        logger.info(
            "Health check: status=%s, db=%s, redis=%s",
            result.overall_status,
            result.db_connected,
            result.redis_connected,
        )

        return JSONResponse(
            content     = response_data.model_dump(mode="json"),
            status_code = http_status,
        )

    except Exception as e:
        logger.error(
            "Health check crashed: %s", str(e),
            exc_info=True
        )
        return JSONResponse(
            content = {
                "status":    "unhealthy",
                "error":     "Health check failed",
                "service":   settings.app_name,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
            status_code = status.HTTP_503_SERVICE_UNAVAILABLE,
        )


# ═══════════════════════════════════════════════════════════
# GET /health/detailed — Component details
# ═══════════════════════════════════════════════════════════
#
# Logic:
#   Admin ke liye — component-wise latency
#   Monitoring tools ke liye
#   Simple /health se alag — more info

@router.get(
    "/health/detailed",
    summary     = "Detailed health with component latencies",
    description = "Admin use. Component-wise health + latency.",
)
def detailed_health_check(
        settings:       Settings      = Depends(get_settings),
        health_service: HealthService = Depends(get_health_service),
) -> JSONResponse:
    """Detailed health — latency per component."""
    result = health_service.check_health()

    content = {
        "status":    result.overall_status,
        "service":   settings.app_name,
        "version":   settings.app_version,
        "timestamp": result.timestamp.isoformat(),
        "components": [
            {
                "name":       c.name,
                "healthy":    c.healthy,
                "latency_ms": c.latency_ms,
            }
            for c in result.components
        ],
    }

    http_status = (
        status.HTTP_503_SERVICE_UNAVAILABLE
        if not result.is_healthy
        else status.HTTP_200_OK
    )

    return JSONResponse(content=content, status_code=http_status)


# ═══════════════════════════════════════════════════════════
# GET /health/live — Kubernetes Liveness Probe
# ═══════════════════════════════════════════════════════════
#
# Logic:
#   Sirf app alive hai ya nahi
#   No external dependency check
#   Fast — external checks nahi
#   200 → alive (restart mat karo)
#   500 → dead (restart karo)

@router.get(
    "/live",
    summary     = "Lightweight liveness probe",
    description = "Lightweight alive check — no database or redis check. Safe for Render health checks.",
)
@router.get(
    "/health/live",
    summary     = "Kubernetes liveness probe",
    description = "Simple alive check — no external deps.",
)
def liveness_check(
        settings: Settings = Depends(get_settings),
) -> dict:
    """App alive hai — no external checks."""
    return {
        "status":    "alive",
        "service":   settings.app_name,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ═══════════════════════════════════════════════════════════
# GET /health/ready — Kubernetes Readiness Probe
# ═══════════════════════════════════════════════════════════
#
# Logic:
#   Traffic receive karne ke liye ready?
#   DB connected hona zaroori
#   200 → ready (traffic bhejo)
#   503 → not ready (traffic mat bhejo)

@router.get(
    "/health/ready",
    summary     = "Kubernetes readiness probe",
    description = "Ready to serve traffic? DB must be connected.",
)
def readiness_check(
        settings:       Settings      = Depends(get_settings),
        health_service: HealthService = Depends(get_health_service),
) -> JSONResponse:
    """Ready to serve — DB must be UP."""
    result = health_service.check_health()

    if not result.db_connected:
        return JSONResponse(
            content = {
                "status":  "not_ready",
                "reason":  "Database unavailable",
                "service": settings.app_name,
            },
            status_code = status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    return JSONResponse(
        content = {
            "status":    "ready",
            "service":   settings.app_name,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
        status_code = status.HTTP_200_OK,
    )