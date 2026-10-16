# ai-service/core/middleware.py

import logging
import time
import uuid
from typing import Callable

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════
# REQUEST LOGGING MIDDLEWARE
# ═══════════════════════════════════════════════════════════
#
# SOLID:
#   S → Sirf request/response logging
#   O → Naya middleware = new class — setup_middlewares change nahi
#
# Logic:
#   Har request ko unique ID do → distributed tracing
#   Response time measure karo → performance monitoring
#   Status code log karo → error detection

class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Request/Response logging middleware.

    SOLID S: Sirf request logging.

    Logic:
        UUID → unique request ID
        perf_counter → accurate timing
        Response headers → X-Request-ID inject
    """

    async def dispatch(
            self,
            request:   Request,
            call_next: Callable
    ) -> Response:
        """
        Request intercept karo → log karo → forward karo.

        Logic:
            1. Unique request ID generate
            2. Request log karo
            3. Handler call karo
            4. Response log karo (time + status)
            5. Headers mein ID inject karo
        """
        request_id = str(uuid.uuid4())[:8]
        start_time = time.perf_counter()

        # ✅ Request ID context mein store
        request.state.request_id = request_id

        logger.info(
            "Request: id=%s, method=%s, path=%s",
            request_id,
            request.method,
            request.url.path,
        )

        try:
            response = await call_next(request)
            elapsed_ms = round(
                (time.perf_counter() - start_time) * 1000, 2
            )

            logger.info(
                "Response: id=%s, status=%d, time=%.2fms",
                request_id,
                response.status_code,
                elapsed_ms,
            )

            # ✅ Response headers mein inject
            response.headers["X-Request-ID"]    = request_id
            response.headers["X-Response-Time"] = f"{elapsed_ms}ms"

            # ✅ Slow request warning
            if elapsed_ms > 5000:
                logger.warning(
                    "Slow request: id=%s, path=%s, time=%.2fms",
                    request_id,
                    request.url.path,
                    elapsed_ms,
                )

            return response

        except Exception as e:
            elapsed_ms = round(
                (time.perf_counter() - start_time) * 1000, 2
            )
            logger.error(
                "Request failed: id=%s, path=%s, "
                "time=%.2fms, error=%s",
                request_id,
                request.url.path,
                elapsed_ms,
                str(e),
                exc_info=True,
            )
            raise


# ═══════════════════════════════════════════════════════════
# MIDDLEWARE SETUP
# ═══════════════════════════════════════════════════════════
#
# SOLID:
#   S → Sirf middleware registration
#   O → Naya middleware = yahan add karo
#
# Logic:
#   Middleware order MATTERS — LIFO execution
#   GZip → outermost (compress everything)
#   CORS → cross-origin
#   RequestLogging → request tracking
#
# Execution Order:
#   Request:  RequestLogging → CORS → GZip → Handler
#   Response: Handler → GZip → CORS → RequestLogging

def setup_middlewares(
        app:          FastAPI,
        cors_origins: list[str],
) -> None:
    """
    Sab middlewares register karo.

    SOLID S: Sirf middleware setup.
    SOLID O: Naya middleware = yahan add karo.

    Args:
        app:          FastAPI instance
        cors_origins: Allowed CORS origins from config
    """
    # ✅ Bug Fix 8: GZip compression
    # Logic: 1KB+ responses compress karo → bandwidth save
    app.add_middleware(
        GZipMiddleware,
        minimum_size=1000  # 1KB se bada compress karo
    )

    # ✅ CORS — config se (sirf tab add karo agar origins defined hon, backend-to-backend me empty)
    if cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins     = cors_origins,
            allow_credentials = True,
            allow_methods     = ["GET", "POST"],
            allow_headers     = ["*"],
            expose_headers    = ["X-Request-ID", "X-Response-Time"],
        )

    # ✅ Bug Fix 9: Request logging
    app.add_middleware(RequestLoggingMiddleware)

    logger.info(
        "Middlewares configured: GZip, CORS (%d origins), "
        "RequestLogging",
        len(cors_origins),
    )