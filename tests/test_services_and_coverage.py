# ai-service/tests/test_services_and_coverage.py

from datetime import date, timedelta, datetime
import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from main import create_app
from models.common import ScoreBreakdown
from models.enums import BloodGroup, UrgencyLevel, TrendDirection
from models.request_schemas import DonorMatchRequest, DemandPredictionRequest
from models.response_schemas import MatchedDonor
from services.donor_scorer import DonorScoringService
from services.response_mapper import DonorResponseMapper
from services.matching_service import MatchingService
from services.prediction_service import PredictionService
from services.trend_analyzer import DefaultTrendAnalyzer
from services.peak_day_analyzer import PeakDayAnalyzer
from services.recommendation_generator import RecommendationGenerator
from utils.scoring import (
    DistanceScorer,
    ReliabilityScorer,
    ResponseRateScorer,
    DonorAIScorer,
    calculate_ai_score,
)
from utils.distance import HaversineCalculator, BatchDistanceCalculator, Coordinate, is_within_radius


class TestScoringUtilsFull:
    """Test all scorers in utils/scoring.py."""

    def test_distance_scorer_edge_cases(self):
        scorer = DistanceScorer()
        assert scorer.score(0.0, 50.0) == 1.0
        assert scorer.score(-5.0, 50.0) == 1.0  # negative clamped
        assert 0.0 <= scorer.score(50.0, 50.0) <= 0.1

    def test_reliability_scorer_clamping(self):
        scorer = ReliabilityScorer()
        assert scorer.score(80.0) == 0.8
        assert scorer.score(150.0) == 1.0  # clamp upper
        assert scorer.score(-10.0) == 0.0  # clamp lower

    def test_response_rate_scorer_clamping(self):
        scorer = ResponseRateScorer()
        assert scorer.score(90.0) == 0.9
        assert scorer.score(120.0) == 1.0
        assert scorer.score(-5.0) == 0.0

    def test_donor_ai_scorer_full_calculation(self):
        scorer = DonorAIScorer()
        result = scorer.calculate(
            distance_km=5.0,
            radius_km=25.0,
            reliability_score=85.0,
            response_rate=90.0,
            last_donation_date=date.today() - timedelta(days=100),
            is_available=True,
        )
        assert 0.0 <= result.ai_score <= 1.0
        assert 0.0 <= result.ai_score_display <= 100.0
        assert isinstance(result.breakdown, ScoreBreakdown)
        assert scorer.is_eligible(last_donation_date=None, is_available=True) is True
        assert scorer.days_until_eligible(last_donation_date=None) == 0

    def test_calculate_ai_score_convenience_function(self):
        display, breakdown = calculate_ai_score(
            distance_km=5.0,
            radius_km=25.0,
            reliability_score=80.0,
            response_rate=80.0,
            last_donation_date=None,
            is_available=True,
        )
        assert 0.0 <= display <= 100.0
        assert isinstance(breakdown, ScoreBreakdown)


class TestDistanceUtilsFull:
    """Test distance utilities, batch calculator, and bearings."""

    def test_haversine_bearing_and_compass(self):
        calc = HaversineCalculator()
        p1 = Coordinate(28.6139, 77.2090)  # Delhi
        p2 = Coordinate(19.0760, 72.8777)  # Mumbai
        bearing = calc.calculate_bearing(p1, p2)
        assert 0.0 <= bearing <= 360.0
        direction = calc.get_compass_direction(bearing)
        assert direction in ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]

    def test_batch_distance_calculator(self):
        batch = BatchDistanceCalculator()
        center = Coordinate(28.6139, 77.2090)
        points = [
            Coordinate(28.6139, 77.2090),
            Coordinate(28.7041, 77.1025),
        ]
        dists = batch.calculate_batch(center, points)
        assert len(dists) == 2
        assert dists[0] == 0.0
        assert dists[1] > 0.0

        filtered = batch.filter_within_radius(center, points, radius_km=50.0)
        assert len(filtered) == 2

    def test_is_within_radius(self):
        assert is_within_radius(28.6139, 77.2090, 28.6139, 77.2090, radius_km=5.0) is True


class TestDonorScoringService:
    """Test DonorScoringService batch and single scoring."""

    def test_score_donor_and_batch(self):
        service = DonorScoringService()
        raw_donor = {
            "id": 1,
            "user_id": 101,
            "name": "Aman Sharma",
            "phone": "9876543210",
            "blood_group": "A_POSITIVE",
            "city": "Delhi",
            "latitude": 28.62,
            "longitude": 77.21,
            "reliability_score": 80.0,
            "response_rate": 85.0,
            "total_donations": 3,
            "is_available": 1,
            "last_donation_date": date.today() - timedelta(days=120),
        }
        scored = service.score_donor(raw_donor, req_lat=28.6139, req_lng=77.2090, radius_km=25.0)
        assert "distance_km" in scored
        assert "ai_score" in scored
        assert scored["is_eligible"] is True

        batch = service.score_donors_batch([raw_donor], req_lat=28.6139, req_lng=77.2090, radius_km=25.0)
        assert len(batch) == 1

        # Test error skipping in batch
        bad_donor = {"id": 99, "latitude": "invalid_lat"}
        batch_with_err = service.score_donors_batch([bad_donor, raw_donor], req_lat=28.6139, req_lng=77.2090, radius_km=25.0)
        assert len(batch_with_err) == 1


class TestResponseMapper:
    """Test response mapper and PII phone masking."""

    def test_mask_phone_scenarios(self):
        assert MatchedDonor.mask_phone("9876543210") == "98****3210"
        assert MatchedDonor.mask_phone("12345") == "****"
        assert MatchedDonor.mask_phone(None) is None
        assert MatchedDonor.mask_phone("") is None

    def test_to_matched_donor_and_batch(self):
        breakdown = ScoreBreakdown(
            distance_score=0.9,
            reliability_score=0.8,
            eligibility_score=1.0,
            response_rate_score=0.8,
            final_score=0.88,
            weights_used={"distance": 0.4, "reliability": 0.3, "eligibility": 0.2, "response_rate": 0.1}
        )
        donor_dict = {
            "id": 1,
            "user_id": 101,
            "name": "Jane Doe",
            "phone": "9876543210",
            "blood_group": "A_POSITIVE",
            "city": "Delhi",
            "latitude": 28.62,
            "longitude": 77.21,
            "distance_km": 3.5,
            "reliability_score": 80.0,
            "response_rate": 85.0,
            "total_donations": 2,
            "is_available": True,
            "is_eligible": True,
            "last_donation_date": date(2025, 1, 1),
            "next_eligible_date": date(2025, 4, 1),
            "ai_score": 0.88,
            "score_breakdown": breakdown,
        }
        matched = DonorResponseMapper.to_matched_donor(donor_dict, rank=1)
        assert matched.rank == 1
        assert matched.phone_masked == "98****3210"
        assert matched.blood_group == "A+"
        assert matched.blood_group_display == "A+"
        assert matched.is_top_match is True

        batch = DonorResponseMapper.to_matched_donors([donor_dict])
        assert len(batch) == 1


class TestMatchingServicePipeline:
    """Test MatchingService pipeline with mocked repository."""

    def test_find_best_donors_empty_db(self):
        mock_db = MagicMock()
        service = MatchingService(db=mock_db)
        with patch.object(service._repository, "find_nearby_donors", return_value=[]):
            req = DonorMatchRequest(
                blood_group="A+",
                latitude=28.6139,
                longitude=77.2090,
                radius_km=25.0,
                urgency="NORMAL",
                limit=10
            )
            resp = service.find_best_donors(req)
            assert resp.total_found == 0
            assert resp.donors == []

    def test_find_best_donors_critical_urgency(self):
        mock_db = MagicMock()
        service = MatchingService(db=mock_db)
        raw_donor = {
            "id": 1,
            "user_id": 101,
            "name": "Aman",
            "phone": "9876543210",
            "blood_group": "A_POSITIVE",
            "city": "Delhi",
            "latitude": 28.62,
            "longitude": 77.21,
            "reliability_score": 80.0,
            "response_rate": 85.0,
            "total_donations": 3,
            "is_available": 1,
            "last_donation_date": None,
        }
        with patch.object(service._repository, "find_nearby_donors", return_value=[raw_donor]):
            req = DonorMatchRequest(
                blood_group="A+",
                latitude=28.6139,
                longitude=77.2090,
                radius_km=25.0,
                urgency="CRITICAL",
                limit=10
            )
            resp = service.find_best_donors(req)
            assert resp.total_found == 1
            assert resp.urgency == UrgencyLevel.CRITICAL
            assert resp.donors[0].name == "Aman"


class TestPredictionServices:
    """Test demand prediction components."""

    def test_default_trend_analyzer_scenarios(self):
        analyzer = DefaultTrendAnalyzer()
        # Increasing trend: recent > 1.2 * previous
        past_data_inc = [{"days_ago": 10}] * 20 + [{"days_ago": 40}] * 10
        res_inc = analyzer.analyze(past_data=past_data_inc, lookback_days=90)
        assert res_inc.direction == TrendDirection.INCREASING

        # Decreasing trend: recent < 0.8 * previous
        past_data_dec = [{"days_ago": 10}] * 10 + [{"days_ago": 40}] * 20
        res_dec = analyzer.analyze(past_data=past_data_dec, lookback_days=90)
        assert res_dec.direction == TrendDirection.DECREASING

        # Stable trend
        past_data_stab = [{"days_ago": 10}] * 10 + [{"days_ago": 40}] * 10
        res_stab = analyzer.analyze(past_data=past_data_stab, lookback_days=90)
        assert res_stab.direction == TrendDirection.STABLE

    def test_peak_day_analyzer(self):
        analyzer = PeakDayAnalyzer()
        past_data = [{"weekday": "Monday"}] * 5 + [{"weekday": "Friday"}] * 3
        result = analyzer.analyze(past_data)
        assert "Monday" in result.peak_days

    def test_recommendation_generator(self):
        gen = RecommendationGenerator()
        rec_inc = gen.generate(
            trend=TrendDirection.INCREASING,
            city="Delhi",
            blood_label="A+",
            predicted=40,
            days=30
        )
        assert "Delhi" in rec_inc
        assert "A+" in rec_inc

    def test_prediction_service_pipeline(self):
        mock_db = MagicMock()
        service = PredictionService(db=mock_db)
        with patch.object(service._repository, "get_request_history", return_value=[{"days_ago": 10, "weekday": "Monday"}] * 15):
            req = DemandPredictionRequest(city="Delhi", blood_group="A+", days_ahead=30)
            pred = service.predict_demand(req)
            assert pred.city == "Delhi"
            assert pred.predicted_requests >= 0


class TestAdditionalHealthEndpoints:
    """Test /health/detailed, /health/live, /health/ready endpoints."""

    def test_health_detailed_endpoint(self):
        from services.health_service import ComponentStatus
        client = TestClient(create_app(), raise_server_exceptions=False)
        with patch("services.health_service.HealthService.check_health") as mock_check:
            mock_check.return_value = MagicMock(
                overall_status="healthy",
                is_healthy=True,
                timestamp=datetime.now(),
                components=[ComponentStatus(name="database", healthy=True, latency_ms=1.5)]
            )
            resp = client.get("/health/detailed")
            assert resp.status_code == 200

    def test_health_live_endpoint(self):
        client = TestClient(create_app(), raise_server_exceptions=False)
        resp = client.get("/health/live")
        assert resp.status_code == 200
        assert resp.json()["status"] == "alive"

    def test_health_ready_endpoint(self):
        client = TestClient(create_app(), raise_server_exceptions=False)
        with patch("services.health_service.HealthService.check_health") as mock_check:
            mock_check.return_value = MagicMock(db_connected=True)
            resp = client.get("/health/ready")
            assert resp.status_code == 200
            assert resp.json()["status"] == "ready"

            mock_check.return_value = MagicMock(db_connected=False)
            resp = client.get("/health/ready")
            assert resp.status_code == 503
