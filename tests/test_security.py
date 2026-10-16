# ai-service/tests/test_security.py

import pytest
from fastapi import HTTPException, status
from unittest.mock import patch, MagicMock

from core.security import verify_api_key


class TestSecurityApiKey:
    """Test API key authentication security rules."""

    def test_missing_api_key_raises_401(self):
        """When incoming api_key is None or empty, raise 401."""
        with patch("core.security.get_security_config") as mock_cfg:
            mock_cfg.return_value = MagicMock(api_key="dummy_mock_test_key_not_a_real_secret")
            with pytest.raises(HTTPException) as exc_info:
                verify_api_key(api_key=None)
            assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
            assert "Invalid or missing API Key" in exc_info.value.detail

    def test_empty_string_api_key_raises_401(self):
        """Empty string api_key raises 401."""
        with patch("core.security.get_security_config") as mock_cfg:
            mock_cfg.return_value = MagicMock(api_key="dummy_mock_test_key_not_a_real_secret")
            with pytest.raises(HTTPException) as exc_info:
                verify_api_key(api_key="")
            assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED

    def test_invalid_api_key_raises_401(self):
        """Mismatched api_key raises 401."""
        with patch("core.security.get_security_config") as mock_cfg:
            mock_cfg.return_value = MagicMock(api_key="dummy_mock_test_key_not_a_real_secret")
            with pytest.raises(HTTPException) as exc_info:
                verify_api_key(api_key="wrong-key")
            assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
            assert "Invalid or missing API Key" in exc_info.value.detail

    def test_valid_api_key_succeeds(self):
        """Matching api_key succeeds and returns the key."""
        with patch("core.security.get_security_config") as mock_cfg:
            mock_cfg.return_value = MagicMock(api_key="dummy_mock_test_key_not_a_real_secret")
            result = verify_api_key(api_key="dummy_mock_test_key_not_a_real_secret")
            assert result == "dummy_mock_test_key_not_a_real_secret"

    def test_server_unconfigured_api_key_denies_access(self):
        """
        CRITICAL VULNERABILITY PREVENTION:
        If server has empty/None API_KEY, it must NOT allow unauthenticated access.
        """
        with patch("core.security.get_security_config") as mock_cfg:
            mock_cfg.return_value = MagicMock(api_key="")
            with pytest.raises(HTTPException) as exc_info:
                verify_api_key(api_key="any-key")
            assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
            assert "API key authentication required" in exc_info.value.detail
