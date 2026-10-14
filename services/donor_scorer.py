# ai-service/services/donor_scorer.py

import logging
from datetime import date
from typing import Optional

from utils.distance import haversine_distance, Coordinate
from utils.scoring import DonorAIScorer, EligibilityScorer, ScoringResult
from core.config import AIWeightsConfig, get_ai_weights

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════
# DONOR SCORING SERVICE
# ═══════════════════════════════════════════════════════════
#
# SOLID:
#   S → Sirf scoring orchestration
#   D → DonorAIScorer inject
#
# ✅ Bug Fix 6: ScoringResult use karo — scale confusion fix
# ✅ Bug Fix 7: EligibilityScorer use karo — no duplicate
#
# Logic:
#   Raw donor dict → scored donor dict
#   Distance calculate → AI score → eligibility check
#   Failed donors skip — log karo

class DonorScoringService:
    """
    Score individual donors.

    SOLID S: Sirf scoring orchestration.
    SOLID D: DonorAIScorer injected.

    ✅ Bug Fix 6: ScoringResult → proper scale
    ✅ Bug Fix 7: EligibilityScorer → no duplication

    Usage:
        service = DonorScoringService()
        scored = service.score_donors_batch(
            donors, hospital_lat, hospital_lng, radius_km
        )
    """

    def __init__(
            self,
            weights: Optional[AIWeightsConfig] = None
    ):
        # ✅ D: Inject → default config se
        self._scorer       = DonorAIScorer(weights=weights or get_ai_weights())
        self._elig_scorer  = EligibilityScorer()

    def score_donor(
            self,
            donor:       dict,
            req_lat:     float,
            req_lng:     float,
            radius_km:   float,
    ) -> dict:
        """
        Single donor score karo.

        ✅ Bug Fix 6: ai_score = 0-1, ai_score_display = 0-100
        ✅ Bug Fix 7: EligibilityScorer use karo

        Logic:
            1. Distance calculate karo
            2. ScoringResult get karo
            3. Eligibility check karo
            4. Dict mein add karo

        Returns:
            Donor dict with distance_km, ai_score,
            ai_score_display, score_breakdown, is_eligible
        """
        # Distance calculate
        distance_km = haversine_distance(
            lat1=req_lat, lon1=req_lng,
            lat2=float(donor["latitude"]),
            lon2=float(donor["longitude"])
        )

        # ✅ Bug Fix 7: EligibilityScorer — duplicate logic nahi
        last_donation_date: Optional[date] = donor.get("last_donation_date")
        is_available: bool = bool(donor.get("is_available", False))

        is_eligible = self._elig_scorer.score(
            last_donation_date, is_available
        ) == 1.0

        # ✅ Bug Fix 6: ScoringResult — proper scale separation
        result: ScoringResult = self._scorer.calculate(
            distance_km       = distance_km,
            radius_km         = radius_km,
            reliability_score = float(donor.get("reliability_score") or 50.0),
            response_rate     = float(donor.get("response_rate") or 0.0),
            last_donation_date = last_donation_date,
            is_available       = is_available,
        )

        return {
            **donor,
            "distance_km":       distance_km,
            "ai_score":          result.ai_score,          # ✅ 0-1
            "ai_score_display":  result.ai_score_display,  # ✅ 0-100
            "score_breakdown":   result.breakdown,          # ✅ Typed
            "is_eligible":       is_eligible,
        }

    def score_donors_batch(
            self,
            donors:    list[dict],
            req_lat:   float,
            req_lng:   float,
            radius_km: float,
    ) -> list[dict]:
        """
        Multiple donors batch score karo.

        Logic:
            Individual calls — ek ek donor
            Failed donors skip — log karo
            Errors ek donor ko skip kare — sab fail nahi

        Returns:
            Scored donors list (failed donors excluded)
        """
        scored = []
        for donor in donors:
            try:
                scored.append(
                    self.score_donor(donor, req_lat, req_lng, radius_km)
                )
            except Exception as e:
                logger.warning(
                    "Failed to score donor id=%s: %s",
                    donor.get("id"), str(e)
                )
        return scored