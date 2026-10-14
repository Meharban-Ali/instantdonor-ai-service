# ai-service/services/prediction_service.py

import logging
from typing import Optional

from sqlalchemy.orm import Session

from models.enums import BloodGroup, TrendDirection
from models.request_schemas import DemandPredictionRequest  # ✅ Bug Fix 3
from models.response_schemas import DemandPrediction        # ✅ Bug Fix 3
from repositories.blood_request_repository import BloodRequestRepository
from services.trend_analyzer import (
    DefaultTrendAnalyzer,
    TrendAnalyzerStrategy,
    TrendResult,
)
from services.peak_day_analyzer import PeakDayAnalyzer
from services.recommendation_generator import RecommendationGenerator

logger = logging.getLogger(__name__)

# ✅ Bug Fix 10: Named constants — magic numbers nahi
LOOKBACK_DAYS   = 90    # Historical data period
MIN_CONFIDENCE  = 0.15  # No data case
MIN_PREDICTION  = 1     # Minimum predicted requests
DEFAULT_PREDICTION = 5  # No data default


# ═══════════════════════════════════════════════════════════
# PREDICTION SERVICE — Orchestrator
# ═══════════════════════════════════════════════════════════
#
# SOLID:
#   S → Sirf pipeline orchestration
#   O → Naya analyzer = inject karo — service change nahi
#   D → All dependencies inject karo
#
# ✅ Bug Fix 1: Trailing comma in _get_history → repo moved
# ✅ Bug Fix 2: SQL injection → repo layer fix
# ✅ Bug Fix 3: Correct imports
# ✅ Bug Fix 4: TrendDirection enum
# ✅ Bug Fix 5: Direct daily_avg formula
# ✅ Bug Fix 6: blood_label correct
# ✅ Bug Fix 7: None-safe → analyzer fix
# ✅ Bug Fix 8: Default peak_days → analyzer fix
# ✅ Bug Fix 9: S violation → alag classes
# ✅ Bug Fix 10: Named constants
#
# Logic (Pipeline):
#   1. DB history → BloodRequestRepository
#   2. Trend → TrendAnalyzer
#   3. Peak days → PeakDayAnalyzer
#   4. Recommendation → RecommendationGenerator
#   5. DemandPrediction response build
#
# System Design:
#   FastAPI route → PredictionService → pipeline
#   Each component independently testable

class PredictionService:
    """
    Blood demand prediction orchestrator.

    SOLID S: Pipeline orchestration only.
    SOLID O: TrendAnalyzer injectable.
    SOLID D: All dependencies injectable.

    Pipeline:
        Request → DB History → Trend →
        Peak Days → Recommendation → Response

    Usage:
        service = PredictionService(db=db)
        result = service.predict_demand(request)
    """

    def __init__(
            self,
            db:             Session,
            trend_analyzer: Optional[TrendAnalyzerStrategy] = None,
            peak_analyzer:  Optional[PeakDayAnalyzer]       = None,
            recommender:    Optional[RecommendationGenerator] = None,
    ):
        # ✅ D: All dependencies inject
        self._repository    = BloodRequestRepository(db)
        self._trend_analyzer = trend_analyzer or DefaultTrendAnalyzer()
        self._peak_analyzer  = peak_analyzer  or PeakDayAnalyzer()
        self._recommender    = recommender    or RecommendationGenerator()

    def predict_demand(
            self,
            req: DemandPredictionRequest
    ) -> DemandPrediction:
        """
        Blood demand prediction pipeline.

        ✅ Bug Fix 1: Repository use — trailing comma fix
        ✅ Bug Fix 3: Correct imports
        ✅ Bug Fix 4: TrendDirection enum
        ✅ Bug Fix 5: Direct daily_avg formula

        Logic Steps:
            1. City normalize karo
            2. Blood group value extract karo
            3. Historical data fetch karo
            4. No data → fallback response
            5. Trend analyze karo
            6. Prediction calculate karo
            7. Peak days find karo
            8. Recommendation generate karo
            9. DemandPrediction return karo

        Args:
            req: Validated DemandPredictionRequest

        Returns:
            DemandPrediction with forecast + confidence
        """
        # ─── Step 1: Input normalize ────────────────────────
        city             = req.city.strip()
        blood_group      = req.blood_group

        # ✅ Database enum name (O_POSITIVE) for SQL queries
        blood_group_val  = blood_group.name if blood_group else None
        # Keep human-readable display (O+) for logs/labels
        blood_label      = blood_group.value if blood_group else "All blood groups"

        logger.info(
            "Predicting: city=%s, blood=%s, days=%d",
            city, blood_group_val, req.days_ahead
        )

        # ─── Step 2: Historical data ─────────────────────────
        past_data = self._repository.get_request_history(
            city        = city,
            blood_group = blood_group_val,
            days        = LOOKBACK_DAYS
        )

        # ─── Step 3: No data fallback ────────────────────────
        if not past_data:
            logger.warning(
                "No historical data: city=%s, blood=%s",
                city, blood_group_val
            )
            return self._no_data_response(
                req, blood_group, blood_label
            )

        # ─── Step 4: Trend analysis ──────────────────────────
        # Logic:
        #   DefaultTrendAnalyzer → recent vs previous 30 days
        #   TrendResult → direction + confidence + daily_avg
        trend_result: TrendResult = self._trend_analyzer.analyze(
            past_data     = past_data,
            lookback_days = LOOKBACK_DAYS,
        )

        # ─── Step 5: Prediction ──────────────────────────────
        # ✅ Bug Fix 5: Direct formula — no double division
        # Logic:
        #   daily_avg = total / 90 days
        #   predicted = daily_avg × forecast_days
        predicted = max(
            MIN_PREDICTION,
            round(trend_result.daily_average * req.days_ahead)
        )

        # ─── Step 6: Peak days ───────────────────────────────
        peak_result = self._peak_analyzer.analyze(past_data)

        # ─── Step 7: Recommendation ──────────────────────────
        recommendation = self._recommender.generate(
            trend       = trend_result.direction,
            city        = city,
            blood_label = blood_label,
            predicted   = predicted,
            days        = req.days_ahead,
        )

        logger.info(
            "Prediction done: city=%s, trend=%s, "
            "predicted=%d, confidence=%.2f",
            city,
            trend_result.direction,
            predicted,
            trend_result.confidence,
        )

        return DemandPrediction(
            city               = city,
            blood_group        = blood_group,      # ✅ Enum
            period_days        = req.days_ahead,
            predicted_requests = predicted,
            confidence         = trend_result.confidence,
            trend              = trend_result.direction,  # ✅ Enum
            peak_days          = peak_result.peak_days,
            recommendation     = recommendation,
            historical_avg     = trend_result.daily_average,
            predicted_peak     = round(predicted * 1.3),
        )

    def _no_data_response(
            self,
            req:         DemandPredictionRequest,
            blood_group: Optional[BloodGroup],
            blood_label: str,
    ) -> DemandPrediction:
        """
        ✅ Bug Fix 10: No data → named constants.

        Logic:
            Historical data nahi → approximate prediction
            MIN_CONFIDENCE = 0.15 (low confidence)
            DEFAULT_PREDICTION = 5 (conservative)
            Clear recommendation — data insufficient
        """
        recommendation = (
            f"Insufficient historical data for {blood_label} "
            f"in {req.city}. "
            f"Prediction is approximate (confidence: 15%). "
            f"Collect more data for accurate forecasts."
        )

        return DemandPrediction(
            city               = req.city,
            blood_group        = blood_group,
            period_days        = req.days_ahead,
            predicted_requests = DEFAULT_PREDICTION,  # ✅ Named constant
            confidence         = MIN_CONFIDENCE,       # ✅ Named constant
            trend              = TrendDirection.STABLE,
            peak_days          = PeakDayAnalyzer.DEFAULT_PEAK_DAYS,
            recommendation     = recommendation,
            historical_avg     = 0.0,
            predicted_peak     = DEFAULT_PREDICTION,
        )