# ai-service/tests/test_model_and_health.py

import os
import tempfile
import pytest
from unittest.mock import patch, MagicMock

from core.model_loader import MLModelManager
from services.health_service import (
    HealthService,
    MLModelHealthComponent,
    DatabaseHealthComponent,
    RedisHealthComponent,
    ComponentStatus,
)


class TestMLModelManager:
    """Test MLModelManager lifecycle and error handling."""

    def setup_method(self):
        MLModelManager.reset()

    def teardown_method(self):
        MLModelManager.reset()

    def test_load_existing_model_success(self):
        """Test loading valid pickle model."""
        with tempfile.NamedTemporaryFile(suffix=".pkl", delete=False) as f:
            import pickle
            pickle.dump({"model_name": "test_rf"}, f)
            temp_path = f.name

        try:
            with patch("core.model_loader.get_ml_config") as mock_cfg:
                mock_cfg.return_value = MagicMock(model_path=temp_path)
                manager = MLModelManager.get_instance()
                assert manager.is_loaded is False
                assert manager.load_model() is True
                assert manager.is_loaded is True
                assert manager.model == {"model_name": "test_rf"}
                assert manager.load_error is None
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def test_load_missing_model_fails(self):
        """Test handling of missing model file."""
        with patch("core.model_loader.get_ml_config") as mock_cfg:
            mock_cfg.return_value = MagicMock(model_path="/non/existent/path/model.pkl")
            manager = MLModelManager.get_instance()
            assert manager.load_model() is False
            assert manager.is_loaded is False
            assert "not found" in manager.load_error

    def test_load_corrupt_model_fails(self):
        """Test handling of corrupted model file."""
        with tempfile.NamedTemporaryFile(suffix=".pkl", delete=False) as f:
            f.write(b"this is corrupt binary junk not a pickle")
            temp_path = f.name

        try:
            with patch("core.model_loader.get_ml_config") as mock_cfg:
                mock_cfg.return_value = MagicMock(model_path=temp_path)
                manager = MLModelManager.get_instance()
                assert manager.load_model() is False
                assert manager.is_loaded is False
                assert "Corrupt or invalid" in manager.load_error
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)


class TestHealthServiceAndComponents:
    """Test HealthService and MLModelHealthComponent."""

    def test_ml_model_health_component_healthy(self):
        """When model is loaded, MLModelHealthComponent reports healthy."""
        component = MLModelHealthComponent()
        with patch("core.model_loader.MLModelManager.get_instance") as mock_mgr:
            mock_mgr.return_value = MagicMock(is_loaded=True)
            assert component.is_healthy() is True

    def test_ml_model_health_component_unhealthy(self):
        """When model fails loading, MLModelHealthComponent reports unhealthy."""
        component = MLModelHealthComponent()
        with patch("core.model_loader.MLModelManager.get_instance") as mock_mgr:
            mock_mgr.return_value = MagicMock(is_loaded=False, load_model=MagicMock(return_value=False))
            assert component.is_healthy() is False

    def test_health_service_all_healthy(self):
        """When DB, Redis, and ML Model are healthy, overall status is healthy."""
        checker_db = MagicMock(component_name="database", is_healthy=MagicMock(return_value=True))
        checker_redis = MagicMock(component_name="redis", is_healthy=MagicMock(return_value=True))
        checker_model = MagicMock(component_name="ml_model", is_healthy=MagicMock(return_value=True))

        service = HealthService(checkers=[checker_db, checker_redis, checker_model])
        res = service.check_health()
        assert res.overall_status == "healthy"
        assert res.is_healthy is True
        assert res.db_connected is True
        assert res.redis_connected is True
        assert res.model_loaded is True

    def test_health_service_model_unhealthy_makes_overall_unhealthy(self):
        """Because ml_model is a CRITICAL component, its failure results in unhealthy status."""
        checker_db = MagicMock(component_name="database", is_healthy=MagicMock(return_value=True))
        checker_redis = MagicMock(component_name="redis", is_healthy=MagicMock(return_value=True))
        checker_model = MagicMock(component_name="ml_model", is_healthy=MagicMock(return_value=False))

        service = HealthService(checkers=[checker_db, checker_redis, checker_model])
        res = service.check_health()
        assert res.overall_status == "unhealthy"
        assert res.is_healthy is False
        assert res.model_loaded is False

    def test_health_service_redis_down_is_degraded(self):
        """Redis is non-critical, so if it fails while DB and ML are OK, status is degraded."""
        checker_db = MagicMock(component_name="database", is_healthy=MagicMock(return_value=True))
        checker_redis = MagicMock(component_name="redis", is_healthy=MagicMock(return_value=False))
        checker_model = MagicMock(component_name="ml_model", is_healthy=MagicMock(return_value=True))

        service = HealthService(checkers=[checker_db, checker_redis, checker_model])
        res = service.check_health()
        assert res.overall_status == "degraded"
        assert res.is_healthy is False  # degraded is not full healthy
        assert res.redis_connected is False
