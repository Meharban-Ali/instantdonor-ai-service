# ai-service/main.py

import logging
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends

from core.config import get_security_config, get_settings
from core.database import DatabaseHealthChecker
from core.exception_handlers import setup_exception_handlers
from core.logging_config import setup_logging
from core.middleware import setup_middlewares
from routes import health, match, predict

# ✅ Bug Fix 4: Logging PEHLE setup karo
# Logic: Module import se pehle logging ready honi chahiye
setup_logging(debug=False)  # Temporary — lifespan mein proper setup
logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════
# LIFESPAN — Startup + Shutdown
# ═══════════════════════════════════════════════════════════
#
# SOLID:
#   S → Sirf lifecycle management
#
# ✅ Bug Fix 2: Module-level settings removed
# ✅ Bug Fix 4: %s logging
#
# Logic:
#   Startup: logging setup → DB check → ready
#   Shutdown: graceful cleanup
#
# System Design:
#   FastAPI lifespan → Spring Boot @PostConstruct/@PreDestroy
#   DB check → warning only (non-blocking)
#   Resources → properly dispose karo

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifecycle manager.

    SOLID S: Sirf startup/shutdown.

    ✅ Bug Fix 2: settings lifespan mein load
    ✅ Bug Fix 4: %s logging — no f-string

    Startup:
        1. Proper logging setup
        2. DB connection check (warning, not blocking)
        3. App ready

    Shutdown:
        1. Resources cleanup
        2. Graceful exit
    """
    # ─── Startup ───────────────────────────────────────────
    settings = get_settings()  # ✅ Bug Fix 2: Lifespan mein

    # ✅ Proper logging — settings se debug mode
    setup_logging(debug=settings.debug)

    logger.info(  # ✅ Bug Fix 4: %s logging
        "Starting %s v%s in %s mode...",
        settings.app_name,
        settings.app_version,
        settings.environment,
    )

    # DB check — warning only, not blocking
    # Logic:
    #   DB down pe app start nahi hogi toh deadlock possible
    #   Warning log karo → health endpoint pe visible hoga
    try:
        if DatabaseHealthChecker.check_connection():
            logger.info("Database connected successfully")
        else:
            logger.warning(
                "Database NOT connected on startup! "
                "DB-dependent features will fail."
            )
    except Exception as e:
        logger.warning(
            "DB check failed on startup: %s", str(e)
        )

    logger.info(
        "%s started. Docs: http://%s:%d/docs",
        settings.app_name,
        settings.host,
        settings.port,
    )

    yield  # ← App running

    # ─── Shutdown ──────────────────────────────────────────
    logger.info(  # ✅ Bug Fix 4: %s logging
        "%s shutting down gracefully...",
        settings.app_name,
    )


# ═══════════════════════════════════════════════════════════
# APP FACTORY
# ═══════════════════════════════════════════════════════════
#
# SOLID:
#   S → Sirf app creation + configuration
#   O → Naya config = factory update — app change nahi
#   D → Settings inject — hardcode nahi
#
# ✅ Bug Fix 2: Module-level settings removed
# ✅ Bug Fix 5: CORS from config
# ✅ Bug Fix 7: Tags — route files mein
# ✅ Bug Fix 8: GZip middleware
# ✅ Bug Fix 9: Request logging
# ✅ Bug Fix 10: S violation fix
#
# Logic:
#   App factory → testing mein alag config possible
#   Middlewares → setup_middlewares() alag module
#   Exception handlers → setup_exception_handlers() alag
#   Routes → prefix + router register

def create_app() -> FastAPI:
    """
    FastAPI application factory.

    SOLID S: App creation + configuration only.
    SOLID O: Config change = factory update.
    SOLID D: Settings injected.

    ✅ Bug Fix 2: No module-level settings
    ✅ Bug Fix 5: CORS from SecurityConfig
    ✅ Bug Fix 7: No duplicate tags
    ✅ Bug Fix 8: GZip middleware
    ✅ Bug Fix 9: Request logging
    ✅ Bug Fix 10: Concerns separated

    Returns:
        Configured FastAPI instance

    Testing:
        app = create_app()
        client = TestClient(app)
    """
    settings        = get_settings()         # ✅ Bug Fix 2
    security_config = get_security_config()  # ✅ Bug Fix 5

    # ✅ Production Security Hardening: Prevent default keys in production
    if settings.is_production:
        if security_config.jwt_secret == "BloodDonorNetworkSecretKey2024ForLocalDevOnly123456":
            logger.error("PRODUCTION SECURITY ERROR: Default JWT_SECRET is configured in production!")
            raise ValueError("Default JWT_SECRET cannot be used in production mode!")
        if security_config.api_key == "local-dev-api-key-change-in-production":
            logger.error("PRODUCTION SECURITY ERROR: Default API_KEY is configured in production!")
            raise ValueError("Default API_KEY cannot be used in production mode!")

    # ✅ FIX: Always enable docs in development, even if debug=False

    # Production mein docs disable karne ke liye environment check karo
    enable_docs = settings.is_development or settings.is_staging

    # ✅ FastAPI instance
    app = FastAPI(
        title       = settings.app_name,
        description = (
            "AI-powered Blood Donor Matching + "
            "Demand Prediction Service"
        ),
        version  = settings.app_version,
        lifespan = lifespan,

        # ✅ FIX: Docs always enabled in development/staging
        docs_url  = "/docs"  if enable_docs else None,
        redoc_url = "/redoc" if enable_docs else None,
        openapi_url = "/openapi.json" if enable_docs else None,
    )

    # ✅ Bug Fix 5+8+9: Middlewares — config se
    setup_middlewares(
        app          = app,
        cors_origins = security_config.cors_origins,  # ✅ Config se
    )

    # ✅ Bug Fix 6+10: Exception handlers — alag module
    setup_exception_handlers(app, debug=settings.debug)

    # ✅ Route authentication dependency
    from core.security import verify_api_key

    # ✅ Bug Fix 7: Routes register — tags route files mein hain
    app.include_router(
        health.router,
        # tags already in route file
    )
    app.include_router(
        match.router,
        prefix="/api/v1",   # /api/v1/match-donors
        dependencies=[Depends(verify_api_key)]
    )
    app.include_router(
        predict.router,
        prefix="/api/v1",   # /api/v1/predict-demand
        dependencies=[Depends(verify_api_key)]
    )

    # ✅ Additional root endpoint for quick testing
    @app.get("/", tags=["root"])
    async def root():
        """Root endpoint - API information."""
        return {
            "service": settings.app_name,
            "version": settings.app_version,
            "environment": settings.environment,
            "docs_url": app.docs_url,
            "endpoints": {
                "health": "/health",
                "api": "/api/v1",
                "docs": app.docs_url,
                "openapi": app.openapi_url,
            }
        }

    logger.info(
        "App created: routes=%d, docs_enabled=%s",
        len(app.routes),
        enable_docs,
    )

    return app


# ═══════════════════════════════════════════════════════════
# APP INSTANCE
# ═══════════════════════════════════════════════════════════
#
# Logic:
#   Module level pe banao — uvicorn import karega
#   "main:app" → uvicorn.run() reference

app = create_app()


# ═══════════════════════════════════════════════════════════
# DEVELOPMENT SERVER
# ═══════════════════════════════════════════════════════════
#
# ✅ Bug Fix 1: Trailing comma removed
# ✅ Bug Fix 3: reload=settings.debug
#
# Logic:
#   Production mein gunicorn use karo — multiple workers
#   Development mein uvicorn — reload support
#   reload=debug → production pe reload nahi!

if __name__ == "__main__":
    import uvicorn

    settings = get_settings()

    # ✅ Windows-specific socket fix
    is_windows = sys.platform == "win32"

    if is_windows:
        # Windows: Single worker, disable reload to avoid socket issues
        logger.info("Running on Windows - using single worker mode")
        uvicorn.run(
            "main:app",
            host=settings.host,
            port=settings.port,
            reload=False,  # Disable reload on Windows to avoid OSError
            workers=1,     # Force single worker
            log_level="debug" if settings.debug else "info",
        )
    else:
        # Linux/Mac: Full features
        uvicorn.run(
            "main:app",
            host=settings.host,
            port=settings.port,
            reload=settings.debug,
            workers=1 if settings.debug else 4,
            log_level="debug" if settings.debug else "info",
        )