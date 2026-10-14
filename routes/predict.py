# ai-service/routes/predict.py

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from core.database import get_db
from models.request_schemas import DemandPredictionRequest  # ✅ Fix
from models.response_schemas import DemandPrediction        # ✅ Fix
from services.prediction_service import PredictionService

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Demand Prediction"])


# ─── Service Factory ────────────────────────────────────────

def get_prediction_service(
        db: Session = Depends(get_db),
) -> PredictionService:
    """PredictionService factory — Depends ke liye."""
    return PredictionService(db=db)


# ═══════════════════════════════════════════════════════════
# POST /api/v1/predict-demand
# ═══════════════════════════════════════════════════════════
#
# SOLID:
#   S → Sirf HTTP handling
#   D → PredictionService inject
#
# Logic:
#   City + blood_group + days → forecast
#   Historical 90-day data → trend → prediction
#   Admin/Hospital access → demand plan karo

@router.post(
    "/predict-demand",
    response_model = DemandPrediction,
    status_code    = status.HTTP_200_OK,
    summary        = "Blood Demand Prediction",
    description    = (
            "Predict future blood demand for a city.\n\n"
            "Algorithm:\n"
            "  Uses 90-day historical data\n"
            "  Trend: recent_30 vs previous_30 comparison\n"
            "  Prediction: daily_avg × days_ahead\n\n"
            "Confidence:\n"
            "  0.75 = STABLE (most reliable)\n"
            "  0.72 = INCREASING\n"
            "  0.68 = DECREASING\n"
            "  0.50 = No previous period data\n"
            "  0.15 = Insufficient data"
    ),
    responses = {
        200: {"description": "Prediction successful"},
        400: {"description": "Invalid city or parameters"},
        422: {"description": "Validation error"},
        500: {"description": "Prediction service error"},
    }
)
def predict_demand(
        request:            DemandPredictionRequest,
        prediction_service: PredictionService = Depends(get_prediction_service),
) -> DemandPrediction:
    """
    Blood demand prediction endpoint.

    SOLID S: Sirf HTTP handling.
    SOLID D: PredictionService injected.

    Logic:
        1. Request validate (Pydantic auto)
        2. PredictionService.predict_demand()
        3. DemandPrediction return
    """
    logger.info(
        "Prediction request: city=%s, blood=%s, days=%d",
        request.city,
        request.blood_group,
        request.days_ahead,
    )

    try:
        result = prediction_service.predict_demand(request)

        logger.info(
            "Prediction done: city=%s, predicted=%d, "
            "confidence=%.2f, trend=%s",
            request.city,
            result.predicted_requests,
            result.confidence,
            result.trend,
        )

        return result

    except ValueError as e:
        logger.warning("Prediction validation error: %s", str(e))
        raise HTTPException(
            status_code = status.HTTP_400_BAD_REQUEST,
            detail      = str(e),
        )

    except Exception as e:
        logger.error(
            "Prediction service error: %s", str(e),
            exc_info=True
        )
        raise HTTPException(
            status_code = status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail      = "Prediction service error. Please try again.",
        )