# ai-service/core/security.py

import logging
import secrets
from fastapi import HTTPException, Security, status
from fastapi.security.api_key import APIKeyHeader
from core.config import get_security_config

logger = logging.getLogger(__name__)

# Define the API Key header scheme
API_KEY_HEADER = APIKeyHeader(name="X-API-KEY", auto_error=False)


def verify_api_key(api_key: str = Security(API_KEY_HEADER)) -> str:
    """
    Validate the X-API-KEY header against the configured api_key.

    Strictly enforces API key authentication using constant-time comparison.
    If the configured api_key is missing, or if the incoming key does not match,
    HTTP 401 Unauthorized is raised.
    """
    security_config = get_security_config()

    if not security_config.api_key:
        logger.error("Access denied: API_KEY is not configured on the server")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key authentication required"
        )

    # Use constant-time comparison to prevent timing attacks
    if not api_key or not secrets.compare_digest(api_key, security_config.api_key):
        logger.warning("Access denied: Invalid or missing API Key")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API Key"
        )
    return api_key
