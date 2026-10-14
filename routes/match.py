# ai-service/routes/match.py

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from core.config import AIWeightsConfig, get_ai_weights
from core.database import get_db
from models.request_schemas import DonorMatchRequest    # ✅ Bug Fix 6
from models.response_schemas import DonorMatchResponse  # ✅ Bug Fix 6
from services.matching_service import MatchingService

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Donor Matching"])


# ─── Service Factory ────────────────────────────────────────
#
# ✅ Bug Fix 8: Factory function — Depends inject
# SOLID D: Concrete class directly nahi
#
# Logic:
#   FastAPI Depends → MatchingService inject
#   db + weights inject karo
#   Testing mein override possible

def get_matching_service(
        db:      Session         = Depends(get_db),
        weights: AIWeightsConfig = Depends(get_ai_weights),
) -> MatchingService:
    """MatchingService factory — Depends ke liye."""
    return MatchingService(db=db, weights=weights)


# ═══════════════════════════════════════════════════════════
# POST /api/v1/match-donors
# ═══════════════════════════════════════════════════════════
#
# SOLID:
#   S → Sirf HTTP handling — service call karo
#   D → MatchingService inject
#
# ✅ Bug Fix 6: Correct imports
# ✅ Bug Fix 7: Error handling add kiya
# ✅ Bug Fix 8: Depends factory
# ✅ Bug Fix 9: Proper HTTP status
#
# Logic:
#   Request receive → validate (Pydantic auto)
#   MatchingService.find_best_donors() call karo
#   200 OK → donors list
#   400 → validation error
#   500 → unexpected error
#
# System Design:
#   Spring Boot → POST /api/v1/match-donors
#   Blood request create hone pe call hoga
#   Response → top matched donors

@router.post(
    "/match-donors",
    response_model = DonorMatchResponse,
    status_code    = status.HTTP_200_OK,
    summary        = "AI Donor Matching",
    description    = (
            "Find best matching donors using AI scoring.\n\n"
            "Scoring Formula:\n"
            "  score = 0.40×distance + 0.30×reliability "
            "+ 0.20×eligibility + 0.10×response_rate\n\n"
            "Ranking:\n"
            "  CRITICAL urgency → distance priority\n"
            "  Others → AI score priority\n"
            "  Eligible donors always first"
    ),
    responses = {
        200: {"description": "Donors matched successfully"},
        400: {"description": "Invalid request data"},
        422: {"description": "Validation error"},
        500: {"description": "Matching service error"},
    }
)
def match_donors(
        request: DonorMatchRequest,
        # ✅ Bug Fix 8: Depends inject — not direct instantiation
        matching_service: MatchingService = Depends(get_matching_service),
) -> DonorMatchResponse:
    """
    AI donor matching endpoint.

    SOLID S: Sirf HTTP handling.
    SOLID D: MatchingService injected.

    ✅ Bug Fix 6: Correct imports
    ✅ Bug Fix 7: Error handling
    ✅ Bug Fix 8: Depends factory
    ✅ Bug Fix 9: ResponseEntity equivalent

    Logic:
        1. Request validate (Pydantic auto)
        2. MatchingService.find_best_donors()
        3. DonorMatchResponse return
        4. Error → appropriate HTTP status
    """
    logger.info(
        "Match request: blood=%s, radius=%skm, "
        "urgency=%s, limit=%d",
        request.blood_group,
        request.radius_km,
        request.urgency,
        request.limit,
    )

    try:
        result = matching_service.find_best_donors(request)

        logger.info(
            "Match complete: found=%d, time=%.2fms",
            result.total_found,
            result.processing_time_ms,
        )

        # ✅ Bug Fix 9: Return typed response
        return result

    except ValueError as e:
        # Validation/business logic error → 400
        logger.warning("Match validation error: %s", str(e))
        raise HTTPException(
            status_code = status.HTTP_400_BAD_REQUEST,
            detail      = str(e),
        )

    except Exception as e:
        # Unexpected error → 500
        logger.error(
            "Match service error: %s", str(e),
            exc_info=True
        )
        raise HTTPException(
            status_code = status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail      = "Matching service error. Please try again.",
        )