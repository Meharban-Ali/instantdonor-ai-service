# ai-service/core/exception_handlers.py

import logging
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════
# EXCEPTION HANDLERS SETUP
# ═══════════════════════════════════════════════════════════
#
# SOLID:
#   S → Sirf exception handling ka kaam
#   O → Naya exception = naya handler function
#
# ✅ Bug Fix 6: Production mein detail hide
#
# Logic:
#   ValidationError → 422 (request wrong format)
#   HTTPException   → proper status code
#   ValueError      → 400 (business logic error)
#   Exception       → 500 (production mein detail hide)

def setup_exception_handlers(
        app:   FastAPI,
        debug: bool = False,
) -> None:
    """
    Sab exception handlers register karo.

    SOLID S: Sirf exception handling.
    SOLID O: Naya exception = naya @app.exception_handler.

    Args:
        app:   FastAPI instance
        debug: Debug mode (True=show detail, False=hide)
    """

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
            request: Request,
            exc:     RequestValidationError,
    ) -> JSONResponse:
        """
        Pydantic validation errors → 422.

        Logic:
            Request body invalid → 422
            Detail → sab validation errors
        """
        logger.warning(
            "Validation error: path=%s, errors=%s",
            request.url.path,
            exc.errors()
        )
        return JSONResponse(
            status_code = status.HTTP_422_UNPROCESSABLE_ENTITY,
            content     = {
                "success": False,
                "error":   "Validation failed",
                "detail":  exc.errors() if debug else "Invalid request",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(
            request: Request,
            exc:     HTTPException,
    ) -> JSONResponse:
        """
        HTTP exceptions → proper status.

        Logic:
            HTTPException.status_code → return karo
            detail → error message
        """
        logger.warning(
            "HTTP error: path=%s, status=%d, detail=%s",
            request.url.path, exc.status_code, exc.detail
        )
        return JSONResponse(
            status_code = exc.status_code,
            content     = {
                "success": False,
                "error":   exc.detail,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )

    @app.exception_handler(ValueError)
    async def value_error_handler(
            request: Request,
            exc:     ValueError,
    ) -> JSONResponse:
        """
        ValueError → 400 Bad Request.

        Logic:
            Business logic errors
            Input validation failures
        """
        logger.warning(
            "Value error: path=%s, error=%s",
            request.url.path, str(exc)
        )
        return JSONResponse(
            status_code = status.HTTP_400_BAD_REQUEST,
            content     = {
                "success": False,
                "error":   str(exc) if debug else "Invalid input",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )

    @app.exception_handler(Exception)
    async def global_exception_handler(
            request: Request,
            exc:     Exception,
    ) -> JSONResponse:
        """
        ✅ Bug Fix 6: Catch-all → detail hide in production.

        Logic:
            Debug mode → full detail show
            Production → generic message (security!)
            Always → full traceback LOG mein
        """
        logger.error(
            "Unhandled error: path=%s, error=%s",
            request.url.path, str(exc),
            exc_info=True  # ✅ Full traceback log mein
        )
        return JSONResponse(
            status_code = status.HTTP_500_INTERNAL_SERVER_ERROR,
            content     = {
                "success": False,
                "error":   "AI service error",
                # ✅ Bug Fix 6: Production mein detail hide!
                "detail": str(exc) if debug else "Please try again later.",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )

    logger.info("Exception handlers configured")