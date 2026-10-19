# ai-service/tests/test_api_endpoints.py

import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from main import create_app
from services.health_service import HealthCheckResult, ComponentStatus
from models.response_schemas import DonorMatchResponse, DemandPrediction
from core.database import get_db
from models.enums import BloodGroup, UrgencyLevel, TrendDirection


@pytest.fixture
def client():
    """Create test client with mocked security and dependencies."""
    app = create_app()
    app.dependency_overrides[get_db] = lambda: MagicMock()
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


class TestApiEndpoints:
    """Integration and contract tests for FastAPI endpoints."""

    def test_root_endpoint_returns_200(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        data = resp.json()
        assert "service" in data
        assert "version" in data
        assert "endpoints" in data

    def test_live_endpoint_returns_200_without_db(self, client):
        """GET /live should return 200 immediately without touching database."""
        resp = client.get("/live")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "live"
        assert "timestamp" in data
        assert "service" in data

    def test_health_endpoint_healthy_returns_200(self, client):
        """When components are healthy, GET /health returns 200."""
        mock_result = HealthCheckResult(
            overall_status="healthy",
            components=[
                ComponentStatus(name="database", healthy=True),
                ComponentStatus(name="redis", healthy=True),
            ]
        )
        with patch("services.health_service.HealthService.check_health", return_value=mock_result):
            resp = client.get("/health")
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "healthy"
            assert data["db_connected"] is True
            assert data["redis_connected"] is True

    def test_health_endpoint_unhealthy_returns_503(self, client):
        """When critical component fails, GET /health returns 503."""
        mock_result = HealthCheckResult(
            overall_status="unhealthy",
            components=[
                ComponentStatus(name="database", healthy=False),
                ComponentStatus(name="redis", healthy=True),
            ]
        )
        with patch("services.health_service.HealthService.check_health", return_value=mock_result):
            resp = client.get("/health")
            assert resp.status_code == 503
            data = resp.json()
            assert data["status"] == "unhealthy"

    def test_match_donors_without_api_key_returns_401(self, client):
        """Calling match-donors without X-API-KEY header must return 401."""
        body = {
            "blood_group": "A+",
            "latitude": 28.6139,
            "longitude": 77.2090,
            "radius_km": 25.0,
            "urgency": "NORMAL",
        }
        resp = client.post("/api/v1/match-donors", json=body)
        assert resp.status_code == 401
        data = resp.json()
        assert "Invalid or missing API Key" in data.get("error", "")

    def test_match_donors_with_invalid_api_key_returns_401(self, client):
        """Calling match-donors with bad key returns 401."""
        body = {
            "blood_group": "A+",
            "latitude": 28.6139,
            "longitude": 77.2090,
        }
        resp = client.post("/api/v1/match-donors", json=body, headers={"X-API-KEY": "wrong-key"})
        assert resp.status_code == 401

    def test_match_donors_validation_error_returns_422(self, client):
        """Invalid blood group returns 422 Unprocessable Entity."""
        body = {
            "blood_group": "INVALID_GROUP",
            "latitude": 28.6139,
            "longitude": 77.2090,
        }
        # Provide valid API key from config
        with patch("core.security.get_security_config") as mock_sec:
            mock_sec.return_value = MagicMock(api_key="test-key")
            resp = client.post("/api/v1/match-donors", json=body, headers={"X-API-KEY": "test-key"})
            assert resp.status_code == 422

    def test_match_donors_success_contract(self, client):
        """Valid match request returns 200 with contract compliant response."""
        body = {
            "blood_group": "O+",
            "latitude": 28.6139,
            "longitude": 77.2090,
            "radius_km": 25.0,
            "urgency": "NORMAL",
            "limit": 5,
        }
        mock_response = DonorMatchResponse(
            blood_group=BloodGroup.O_POSITIVE,
            urgency=UrgencyLevel.NORMAL,
            total_found=0,
            donors=[],
            compatible_groups_searched=["O_POSITIVE", "O_NEGATIVE"],
            search_radius_km=25.0,
            processing_time_ms=12.5,
        )

        with patch("core.security.get_security_config") as mock_sec, \
             patch("services.matching_service.MatchingService.find_best_donors", return_value=mock_response):
            mock_sec.return_value = MagicMock(api_key="test-key")
            resp = client.post("/api/v1/match-donors", json=body, headers={"X-API-KEY": "test-key"})
            assert resp.status_code == 200
            data = resp.json()
            assert data["blood_group"] == "O+"
            assert data["urgency"] == "NORMAL"
            assert data["total_found"] == 0
            assert "processing_time_ms" in data

    def test_predict_demand_success_contract(self, client):
        """Valid predict request returns 200 with DemandPrediction schema."""
        body = {
            "city": "Delhi",
            "blood_group": "A+",
            "days_ahead": 30
        }
        mock_pred = DemandPrediction(
            city="Delhi",
            blood_group=BloodGroup.A_POSITIVE,
            period_days=30,
            predicted_requests=45,
            confidence=0.75,
            trend=TrendDirection.STABLE,
            peak_days=["Monday", "Wednesday"],
            recommendation="Maintain standard donor inventory for Delhi."
        )

        with patch("core.security.get_security_config") as mock_sec, \
             patch("services.prediction_service.PredictionService.predict_demand", return_value=mock_pred):
            mock_sec.return_value = MagicMock(api_key="test-key")
            resp = client.post("/api/v1/predict-demand", json=body, headers={"X-API-KEY": "test-key"})
            assert resp.status_code == 200
            data = resp.json()
            assert data["city"] == "Delhi"
            assert data["predicted_requests"] == 45
            assert data["confidence"] == 0.75
            assert data["trend"] == "stable"
