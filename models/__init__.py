# ai-service/models/__init__.py
#
# Clean exports — callers ko full path yaad nahi rakhna
# SOLID I: Clients sirf jo chahiye import karein

from models.enums import BloodGroup, UrgencyLevel, TrendDirection
from models.common import ScoreBreakdown
from models.request_schemas import DonorMatchRequest, DemandPredictionRequest
from models.response_schemas import (
    MatchedDonor,
    DonorMatchResponse,
    DemandPrediction,
    HealthResponse,
    ErrorResponse,
)

__all__ = [
    # Enums
    "BloodGroup", "UrgencyLevel", "TrendDirection",
    # Common
    "ScoreBreakdown",
    # Requests
    "DonorMatchRequest", "DemandPredictionRequest",
    # Responses
    "MatchedDonor", "DonorMatchResponse",
    "DemandPrediction", "HealthResponse", "ErrorResponse",
]