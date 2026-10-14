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
    
    If the configured api_key is empty or None, we allow requests
    but print a warning.
    """
    security_config = get_security_config()
    
    if not security_config.api_key:
        logger.warning("API_KEY is empty in configuration! Permitting unauthenticated access.")
        return ""
        
    # Use constant-time comparison to prevent timing attacks
    if not api_key or not secrets.compare_digest(api_key, security_config.api_key):
        logger.warning("Access denied: Invalid or missing API Key")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API Key"
        )
    return api_key

