# ai-service/tests/test_model_and_health.py

import pytest
from unittest.mock import patch, MagicMock

from services.health_service import (
    HealthService,
    DatabaseHealthComponent,
    RedisHealthComponent,
    ComponentStatus,
    HealthCheckResult,
)
from models.enums import BloodGroup
from utils.scoring import calculate_ai_score, DonorAIScorer
from utils.distance import haversine_distance


class TestHealthServiceAndComponents:
    """Test HealthService and infrastructure health components."""

    def test_database_health_component_healthy(self):
        """When DatabaseHealthChecker reports True, component is healthy."""
        component = DatabaseHealthComponent()
        with patch("core.database.DatabaseHealthChecker.check_connection", return_value=True):
            assert component.is_healthy() is True

    def test_database_health_component_unhealthy(self):
        """When DatabaseHealthChecker reports False, component is unhealthy."""
        component = DatabaseHealthComponent()
        with patch("core.database.DatabaseHealthChecker.check_connection", return_value=False):
            assert component.is_healthy() is False

    def test_redis_health_component_healthy(self):
        """When redis ping succeeds, Redis component is healthy."""
        component = RedisHealthComponent()
        with patch("redis.Redis") as mock_redis_cls:
            mock_client = MagicMock()
            mock_client.ping.return_value = True
            mock_redis_cls.return_value = mock_client
            assert component.is_healthy() is True

    def test_redis_health_component_unhealthy(self):
        """When redis ping raises an exception, component reports unhealthy."""
        component = RedisHealthComponent()
        with patch("redis.Redis") as mock_redis_cls:
            mock_client = MagicMock()
            mock_client.ping.side_effect = Exception("Connection refused")
            mock_redis_cls.return_value = mock_client
            assert component.is_healthy() is False

    def test_health_service_all_healthy(self):
        """When DB and Redis are healthy, overall status is healthy."""
        checker_db = MagicMock(component_name="database", is_healthy=MagicMock(return_value=True))
        checker_redis = MagicMock(component_name="redis", is_healthy=MagicMock(return_value=True))

        service = HealthService(checkers=[checker_db, checker_redis])
        res = service.check_health()
        assert res.overall_status == "healthy"
        assert res.is_healthy is True
        assert res.db_connected is True
        assert res.redis_connected is True

    def test_health_service_database_down_is_critical_unhealthy(self):
        """Database is CRITICAL component; failure causes overall status 'unhealthy'."""
        checker_db = MagicMock(component_name="database", is_healthy=MagicMock(return_value=False))
        checker_redis = MagicMock(component_name="redis", is_healthy=MagicMock(return_value=True))

        service = HealthService(checkers=[checker_db, checker_redis])
        res = service.check_health()
        assert res.overall_status == "unhealthy"
        assert res.is_healthy is False
        assert res.db_connected is False

    def test_health_service_redis_down_is_degraded(self):
        """Redis is non-critical; failure causes overall status 'degraded'."""
        checker_db = MagicMock(component_name="database", is_healthy=MagicMock(return_value=True))
        checker_redis = MagicMock(component_name="redis", is_healthy=MagicMock(return_value=False))

        service = HealthService(checkers=[checker_db, checker_redis])
        res = service.check_health()
        assert res.overall_status == "degraded"
        assert res.is_healthy is False  # degraded is not full healthy
        assert res.db_connected is True
        assert res.redis_connected is False


class TestRuleBasedScoring:
    """Verify deterministic rule-based MCDA scoring logic (no ML model file needed)."""

    def test_compatibility_matrix(self):
        """O- is universal donor, AB+ is universal recipient."""
        o_neg = BloodGroup.O_NEGATIVE
        ab_pos = BloodGroup.AB_POSITIVE
        a_pos = BloodGroup.A_POSITIVE

        # O- can donate to AB+ and A+
        assert o_neg in ab_pos.get_compatible_donors()
        assert o_neg in a_pos.get_compatible_donors()

        # AB+ can only receive, cannot donate to O-
        assert ab_pos not in o_neg.get_compatible_donors()

    def test_calculate_ai_score_deterministic(self):
        """Calculate MCDA composite score for emergency donor matching."""
        score, breakdown = calculate_ai_score(
            distance_km=5.0,
            radius_km=25.0,
            reliability_score=80.0,
            response_rate=90.0,
            last_donation_date=None,
            is_available=True,
        )
        assert 0.0 <= score <= 100.0
        assert breakdown is not None
        assert breakdown.distance_score > 0.0
        assert breakdown.reliability_score > 0.0

    def test_haversine_distance(self):
        """Haversine distance between known coordinates."""
        dist = haversine_distance(28.6139, 77.2090, 19.0760, 72.8777)
        assert 1100 <= dist <= 1200
        assert haversine_distance(28.6139, 77.2090, 28.6139, 77.2090) == 0.0
