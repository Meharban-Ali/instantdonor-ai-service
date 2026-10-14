# ai-service/services/matching_service.py

import logging
import time
from typing import Optional

from sqlalchemy.orm import Session

from models.enums import BloodGroup, UrgencyLevel
from models.request_schemas import DonorMatchRequest    # ✅ Bug Fix 2
from models.response_schemas import DonorMatchResponse  # ✅ Bug Fix 2
from core.config import AIWeightsConfig, get_ai_weights
from repositories.donor_repository import DonorRepository
from services.donor_scorer import DonorScoringService
from services.donor_ranker import (
    DefaultRankingStrategy,
    UrgentRankingStrategy,
    DonorRankingStrategy,
)
from services.response_mapper import DonorResponseMapper

logger = logging.getLogger(__name__)

# DB se 3x fetch → AI filter karega
FETCH_MULTIPLIER = 3


# ═══════════════════════════════════════════════════════════
# MATCHING SERVICE — Orchestrator
# ═══════════════════════════════════════════════════════════
#
# SOLID:
#   S → Sirf pipeline orchestration
#   O → Naya strategy = inject karo — service change nahi
#   D → All dependencies inject karo
#
# ✅ Bug Fix 3: BloodGroup enum use karo — dict nahi
# ✅ Bug Fix 8: %s logging — lazy evaluation
# ✅ Bug Fix 9: perf_counter — accurate timing
# ✅ Bug Fix 10: S violation fix — alag classes
#
# Logic (Pipeline):
#   1. Compatible groups → BloodGroup enum
#   2. DB fetch → DonorRepository (SQL injection safe)
#   3. AI score → DonorScoringService
#   4. Rank → DonorRankingStrategy (urgency based)
#   5. Map → DonorResponseMapper
#
# System Design:
#   FastAPI route → MatchingService → pipeline
#   Each component independently testable
#   Strategy pattern → CRITICAL different behavior

class MatchingService:
    """
    AI donor matching orchestrator.

    SOLID S: Pipeline orchestration only.
    SOLID O: Ranking strategy injectable.
    SOLID D: All dependencies injectable.

    Pipeline:
        Request → Compatible Groups → DB Fetch →
        AI Score → Rank → Map → Response

    Usage:
        service = MatchingService(db=db)
        response = service.find_best_donors(request)
    """

    def __init__(
            self,
            db:       Session,
            weights:  Optional[AIWeightsConfig]   = None,
            strategy: Optional[DonorRankingStrategy] = None,
    ):
        # ✅ D: All dependencies inject
        self._repository = DonorRepository(db)
        self._scorer     = DonorScoringService(
            weights=weights or get_ai_weights()
        )
        self._mapper     = DonorResponseMapper()

        # ✅ O: Strategy inject — CRITICAL different
        self._default_strategy = strategy or DefaultRankingStrategy()
        self._urgent_strategy  = UrgentRankingStrategy()

    def find_best_donors(
            self,
            request: DonorMatchRequest
    ) -> DonorMatchResponse:
        """
        Main matching pipeline.

        ✅ Bug Fix 2: Correct imports
        ✅ Bug Fix 3: BloodGroup enum — dict nahi
        ✅ Bug Fix 8: %s logging
        ✅ Bug Fix 9: perf_counter

        Logic Steps:
            1. Compatible groups → BloodGroup.get_compatible_donors()
            2. DB fetch → 3x limit (AI will filter)
            3. Score each donor → ScoringResult
            4. Rank → urgency-based strategy
            5. Map → MatchedDonor response objects

        Args:
            request: Validated DonorMatchRequest

        Returns:
            DonorMatchResponse with ranked donors
        """
        start_time = time.perf_counter()  # ✅ Bug Fix 9

        # ─── Step 1: Compatible blood groups ───────────────
        # ✅ Bug Fix 3: BloodGroup enum — dict nahi
        # Logic:
        #   BloodGroup("A+").get_compatible_donors()
        #   → [A+, A-, O+, O-] donor blood groups
        #   → String values for SQL IN clause
        blood_group = BloodGroup(request.blood_group)
        compatible_groups = blood_group.get_compatible_donors()
        compatible_values = [g.name for g in compatible_groups]

        logger.info(  # ✅ Bug Fix 8: %s logging
            "Matching: blood=%s, radius=%skm, urgency=%s, "
            "compatible=%s",
            request.blood_group,
            request.radius_km,
            request.urgency,
            compatible_values,
        )

        # ─── Step 2: DB fetch ───────────────────────────────
        # Logic:
        #   3x limit → AI filter karega
        #   DonorRepository → SQL injection safe query
        raw_donors = self._repository.find_nearby_donors(
            lat          = request.latitude,
            lng          = request.longitude,
            radius_km    = request.radius_km,
            blood_groups = compatible_values,
            limit        = request.limit * FETCH_MULTIPLIER,
        )

        # No donors found → empty response
        if not raw_donors:
            logger.info(
                "No donors found: blood=%s, radius=%skm",
                request.blood_group, request.radius_km
            )
            return self._empty_response(
                request, compatible_values
            )

        # ─── Step 3: AI Score ───────────────────────────────
        # Logic:
        #   Har donor ka score calculate karo
        #   distance + reliability + eligibility + response_rate
        #   Failed donors skip — log karo
        scored_donors = self._scorer.score_donors_batch(
            donors    = raw_donors,
            req_lat   = request.latitude,
            req_lng   = request.longitude,
            radius_km = request.radius_km,
        )

        # ─── Step 4: Rank ───────────────────────────────────
        # Logic:
        #   CRITICAL → UrgentRankingStrategy (distance first)
        #   Others   → DefaultRankingStrategy (AI score first)
        strategy = self._get_strategy(request.urgency)
        ranked_donors = strategy.rank(
            donors = scored_donors,
            limit  = request.limit,
        )

        # ─── Step 5: Map to Response ────────────────────────
        # Logic:
        #   dict → MatchedDonor Pydantic model
        #   phone masked, ai_score = 0-1, breakdown typed
        matched = self._mapper.to_matched_donors(ranked_donors)

        # Timing
        elapsed_ms = round(
            (time.perf_counter() - start_time) * 1000, 2
        )

        logger.info(  # ✅ Bug Fix 8: %s logging
            "Matching complete: found=%d, time=%.2fms, "
            "blood=%s, urgency=%s",
            len(matched),
            elapsed_ms,
            request.blood_group,
            request.urgency,
        )

        return DonorMatchResponse(
            request_id                 = request.request_id,
            blood_group                = blood_group,        # ✅ Enum
            urgency                    = UrgencyLevel(request.urgency),
            total_found                = len(matched),
            donors                     = matched,
            compatible_groups_searched = compatible_values,
            search_radius_km           = request.radius_km,
            processing_time_ms         = elapsed_ms,
            algorithm_version          = "2.0.0",
            cached                     = False,
        )

    def _get_strategy(
            self,
            urgency: UrgencyLevel
    ) -> DonorRankingStrategy:
        """
        Urgency se strategy select karo.

        Logic:
            CRITICAL → distance priority (life or death!)
            Others   → AI score priority (balanced)
        """
        if urgency == UrgencyLevel.CRITICAL:
            return self._urgent_strategy
        return self._default_strategy

    def _empty_response(
            self,
            request:          DonorMatchRequest,
            compatible_values: list[str]
    ) -> DonorMatchResponse:
        """No donors found → empty response."""
        return DonorMatchResponse(
            request_id                 = request.request_id,
            blood_group                = BloodGroup(request.blood_group),
            urgency                    = UrgencyLevel(request.urgency),
            total_found                = 0,
            donors                     = [],
            compatible_groups_searched = compatible_values,
            search_radius_km           = request.radius_km,
            processing_time_ms         = 0.0,
        )