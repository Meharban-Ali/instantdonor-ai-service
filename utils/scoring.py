# ai-service/utils/scoring.py

import math
from dataclasses import dataclass
from datetime import date
from typing import Optional, Protocol, runtime_checkable

from models.common import ScoreBreakdown
from core.config import AIWeightsConfig, get_ai_weights

# ═══════════════════════════════════════════════════════════
# CONSTANTS
# ═══════════════════════════════════════════════════════════
#
# SOLID D: Named constants — magic numbers nahi
#
# Logic:
#   ELIGIBILITY_DAYS = 90 → medical standard
#   90 din mein blood replenish ho jaata hai
#   WHO recommendation ke hisaab se
#   ✅ Bug Fix 7: Magic number 90 → named constant

ELIGIBILITY_DAYS     = 90      # Medical standard — WHO
SCORE_SCALE          = 100.0   # Display scale (0-100)
DISTANCE_DECAY_FACTOR = 0.3    # Exponential decay rate


# ═══════════════════════════════════════════════════════════
# COMPONENT SCORER PROTOCOL
# ═══════════════════════════════════════════════════════════
#
# SOLID:
#   D → High-level code is Protocol pe depend karo
#   O → Naya scorer = new class — existing change nahi
#   L → Sab scorers interchangeable
#
# Logic:
#   Har scoring component independently calculate hoga
#   Protocol → duck typing → explicit inheritance nahi
#   Testing mein mock karna easy

@runtime_checkable
class ComponentScorer(Protocol):
    """
    Individual scoring component protocol.

    SOLID D: DonorAIScorer is pe depend karta hai.
    SOLID O: Naya factor = new class implements this.
    SOLID L: Sab scorers 0.0-1.0 return karte hain.

    Returns: Always 0.0 to 1.0 range
    """

    def score(self, **kwargs) -> float:
        """Score calculate karo — 0.0 to 1.0."""
        ...


# ═══════════════════════════════════════════════════════════
# DISTANCE SCORER
# ═══════════════════════════════════════════════════════════
#
# SOLID:
#   S → Sirf distance scoring ka kaam
#
# ✅ Bug Fix 3: Exponential decay — linear nahi
#
# Logic (Why Exponential?):
#   Linear: 1km=0.98, 25km=0.50 → barely different!
#   Exponential: 1km=0.94, 25km=0.19 → big difference!
#
#   Formula: e^(-distance / (radius × decay_factor))
#   decay_factor=0.3 → at 30% radius → score ~0.72
#
#   Blood donation mein:
#   2km donor >> 20km donor
#   Emergency mein nearby STRONGLY preferred
#
# System Design:
#   matching_service.py → DonorAIScorer → DistanceScorer
#   CRITICAL urgency → distance weight already 40%

class DistanceScorer:
    """
    Exponential decay distance scoring.

    SOLID S: Sirf distance score calculate karna.

    ✅ Bug Fix 3: Exponential not linear.

    Why Exponential?
        Linear problem: 1km=0.98, 49km=0.02 (cliff at 50km!)
        Exponential: 1km=0.94, 25km=0.19, 50km=0.04 (smooth)
        Nearby donors STRONGLY preferred
        No artificial cutoff

    Formula:
        score = e^(-distance / (radius × 0.3))
    """

    def score(
            self,
            distance_km: float,
            radius_km:   float
    ) -> float:
        """
        Exponential decay distance score.

        Logic Steps:
            1. distance_km clamp → negative nahi
            2. radius_km clamp → zero division nahi
            3. Exponential formula apply
            4. Clamp to [0.0, 1.0] — safety

        Args:
            distance_km: Donor se hospital distance
            radius_km:   Search radius

        Returns:
            Score 0.0 to 1.0 (1.0=same location)

        Examples:
            score(0.0, 50.0)  → 1.0  (same location)
            score(1.0, 50.0)  → 0.94 (very close)
            score(15.0, 50.0) → 0.37 (moderate)
            score(50.0, 50.0) → 0.04 (far but non-zero)
        """
        # ✅ Bug Fix 6: Input clamp
        distance_km = max(0.0, distance_km)
        radius_km   = max(0.1, radius_km)  # Zero division prevent

        # ✅ Bug Fix 3: Exponential decay
        # e^(-d / (R × factor)) → nearby=high, far=low
        # DECAY_FACTOR=0.3 → at radius*0.3 → score≈0.72
        score = math.exp(
            -distance_km / (radius_km * DISTANCE_DECAY_FACTOR)
        )

        return round(min(1.0, max(0.0, score)), 4)


# ═══════════════════════════════════════════════════════════
# RELIABILITY SCORER
# ═══════════════════════════════════════════════════════════
#
# SOLID:
#   S → Sirf reliability normalize karna
#
# ✅ Bug Fix 6: Input clamp — 0-100 enforce
#
# Logic:
#   DB mein reliability_score 0-100 scale pe hai
#   Normalize karo → 0-1 scale
#   80/100 = 0.80 → 80% weightage milega
#   Trustworthy donors prefer karo

class ReliabilityScorer:
    """
    Reliability score normalizer.

    SOLID S: Sirf DB score ko 0-1 normalize karna.

    Logic:
        DB: 0-100 scale (ReliabilityScoreService update karta)
        AI: 0-1 scale chahiye
        Simple division: 80/100 = 0.80
        Clamp: >100 ya <0 possible → clamp karo
    """

    def score(self, reliability_score: float) -> float:
        """
        Normalize reliability 0-100 → 0-1.

        ✅ Bug Fix 6: Clamp enforced.

        Logic:
            Clamp [0, 100] → edge cases
            Divide by 100 → normalize
            Round to 4 decimal places

        Args:
            reliability_score: DB se 0-100 value

        Returns:
            Normalized 0.0 to 1.0
        """
        # ✅ Bug Fix 6: Clamp — 150 ya -5 possible from DB
        clamped = max(0.0, min(SCORE_SCALE, reliability_score))
        return round(clamped / SCORE_SCALE, 4)


# ═══════════════════════════════════════════════════════════
# ELIGIBILITY SCORER
# ═══════════════════════════════════════════════════════════
#
# SOLID:
#   S → Sirf eligibility check karna
#   D → ELIGIBILITY_DAYS inject possible
#
# ✅ Bug Fix 7: Named constant ELIGIBILITY_DAYS
#
# Logic (Medical Rules):
#   Unavailable donor → 0.0 (not available)
#   Never donated     → 1.0 (fresh donor — eligible!)
#   < 90 days since   → 0.0 (body needs recovery)
#   >= 90 days since  → 1.0 (recovered, eligible)
#
# System Design:
#   DonorRequestResponse → last_donation_date
#   Spring Boot DonorProfile.isEligibleToDonate() se match

class EligibilityScorer:
    """
    Binary eligibility scorer — 0.0 or 1.0 only.

    SOLID S: Sirf 90-day eligibility rule check.
    SOLID D: eligibility_days configurable.

    Medical Logic:
        Blood donation ke baad body 90 din mein recover karta
        WHO standard: 12 weeks (84 days) minimum
        Our standard: 90 days (safer buffer)

    Binary (not continuous):
        Either eligible (1.0) or not (0.0)
        Medical rule — no partial eligibility
    """

    def __init__(
            self,
            eligibility_days: int = ELIGIBILITY_DAYS
    ):
        # ✅ D: Config se inject — hardcode nahi
        self._eligibility_days = eligibility_days

    def score(
            self,
            last_donation_date: Optional[date],
            is_available:       bool
    ) -> float:
        """
        Binary eligibility score.

        ✅ Bug Fix 7: ELIGIBILITY_DAYS constant use

        Logic (Decision Tree):
            is_available=False → 0.0 (unavailable)
            last_donation_date=None → 1.0 (never donated = eligible)
            days_since < 90 → 0.0 (too soon)
            days_since >= 90 → 1.0 (eligible)

        Args:
            last_donation_date: Last donation ya None
            is_available:       Currently available?

        Returns:
            1.0 if eligible, 0.0 if not
        """
        # Rule 1: Unavailable → immediately 0
        if not is_available:
            return 0.0

        # Rule 2: Never donated → eligible (fresh donor!)
        if last_donation_date is None:
            return 1.0

        # Rule 3: 90-day rule check
        days_since = (date.today() - last_donation_date).days
        return 1.0 if days_since >= self._eligibility_days else 0.0

    def days_until_eligible(
            self,
            last_donation_date: Optional[date]
    ) -> int:
        """
        Kitne din baad eligible hoga?

        Logic:
            None → 0 (already eligible — never donated)
            days_since >= 90 → 0 (already eligible)
            days_since < 90 → remaining days

        System Design:
            Frontend pe "Eligible in X days" show karo
            next_eligible_date calculate karne ke liye

        Returns:
            0 if already eligible, else days remaining
        """
        if last_donation_date is None:
            return 0

        days_since = (date.today() - last_donation_date).days
        remaining  = self._eligibility_days - days_since
        return max(0, remaining)


# ═══════════════════════════════════════════════════════════
# RESPONSE RATE SCORER
# ═══════════════════════════════════════════════════════════
#
# SOLID:
#   S → Sirf response rate normalize karna
#
# Logic:
#   DB mein response_rate 0-100% pe hai
#   Responsive donors prefer karo
#   High response rate = trustworthy = high score

class ResponseRateScorer:
    """
    Response rate normalizer.

    SOLID S: Sirf response rate ko 0-1 normalize karna.

    Logic:
        90% response rate → 0.90 score
        Low response → donor pe rely nahi kar sakte
        NO_RESPONSE events score kam karte hain (ReliabilityScoreService)
    """

    def score(self, response_rate: float) -> float:
        """
        Normalize response rate 0-100 → 0-1.

        Args:
            response_rate: DB se 0-100 percentage

        Returns:
            Normalized 0.0 to 1.0
        """
        # ✅ Clamp
        clamped = max(0.0, min(SCORE_SCALE, response_rate))
        return round(clamped / SCORE_SCALE, 4)


# ═══════════════════════════════════════════════════════════
# SCORING RESULT DATACLASS
# ═══════════════════════════════════════════════════════════
#
# SOLID:
#   S → Sirf result data container
#
# ✅ Bug Fix 5: ai_score (0-1) aur ai_score_display (0-100) alag
#
# Logic:
#   response_schemas.py → ai_score: float = Field(ge=0.0, le=1.0)
#   Frontend → 0-100 display chahiye
#   Dono maintain karo — alag fields mein

@dataclass(frozen=True)
class ScoringResult:
    """
    Complete AI scoring result.

    SOLID S: Sirf result data — logic nahi.

    ✅ Bug Fix 5: Scale separation.
        ai_score         → 0.0-1.0  (schema validation)
        ai_score_display → 0.0-100.0 (frontend display)
        breakdown        → typed ScoreBreakdown

    Usage:
        result = scorer.calculate(...)
        schema.ai_score = result.ai_score          # 0.0-1.0
        ui.score = result.ai_score_display         # 0.0-100.0
    """
    ai_score:         float          # 0.0 to 1.0 — schema ke liye
    ai_score_display: float          # 0.0 to 100.0 — display ke liye
    breakdown:        ScoreBreakdown # ✅ Bug Fix 4: Typed


# ═══════════════════════════════════════════════════════════
# DONOR AI SCORER — Main Orchestrator
# ═══════════════════════════════════════════════════════════
#
# SOLID:
#   S → Sirf scoring orchestration ka kaam
#   O → Naya factor = naya scorer inject karo
#   D → All scorers + weights inject karo
#
# ✅ Bug Fix 2: Module-level settings removed
# ✅ Bug Fix 4: ScoreBreakdown typed return
# ✅ Bug Fix 5: Scale separation
#
# Logic (Formula):
#   final = W_dist×dist + W_rel×rel + W_elig×elig + W_resp×resp
#   W_dist = 0.40 (40% → distance sabse important)
#   W_rel  = 0.30 (30% → trustworthy)
#   W_elig = 0.20 (20% → eligible)
#   W_resp = 0.10 (10% → responsive)
#   Sum of weights = 1.0 ✅
#
# System Design:
#   matching_service.py → DonorScoringService → DonorAIScorer
#   Inject weights from AIWeightsConfig (config.py)
#   Inject scorers for testing (mock)

class DonorAIScorer:
    """
    Core AI scoring engine — orchestrator.

    SOLID S: Orchestration only — components inject.
    SOLID O: Naya factor = new scorer inject karo.
    SOLID D: All dependencies injectable.

    Formula:
        score = Σ(weight_i × component_score_i)
              = 0.40×dist + 0.30×rel + 0.20×elig + 0.10×resp

    Usage:
        scorer = DonorAIScorer()
        result = scorer.calculate(
            distance_km=5.0,
            radius_km=25.0,
            reliability_score=80.0,
            response_rate=90.0,
            last_donation_date=None,
            is_available=True
        )
        print(result.ai_score)         # 0.85
        print(result.ai_score_display) # 85.0
    """

    def __init__(
            self,
            weights:            Optional[AIWeightsConfig]   = None,
            distance_scorer:    Optional[DistanceScorer]    = None,
            reliability_scorer: Optional[ReliabilityScorer] = None,
            eligibility_scorer: Optional[EligibilityScorer] = None,
            response_scorer:    Optional[ResponseRateScorer] = None,
    ):
        # ✅ Bug Fix 2: weights inject — module level nahi
        # ✅ D: All dependencies injectable — testing ke liye
        self._weights = weights or get_ai_weights()

        # Default scorers — override for testing
        self._dist_scorer  = distance_scorer    or DistanceScorer()
        self._rel_scorer   = reliability_scorer or ReliabilityScorer()
        self._elig_scorer  = eligibility_scorer or EligibilityScorer()
        self._resp_scorer  = response_scorer    or ResponseRateScorer()

    def calculate(
            self,
            distance_km:        float,
            radius_km:          float,
            reliability_score:  float,
            response_rate:      float,
            last_donation_date: Optional[date],
            is_available:       bool,
    ) -> ScoringResult:
        """
        Complete AI score calculate karo.

        ✅ Bug Fix 2: No module-level settings
        ✅ Bug Fix 3: Exponential distance decay
        ✅ Bug Fix 4: ScoreBreakdown typed
        ✅ Bug Fix 5: Both scales maintained
        ✅ Bug Fix 6: Input validation

        Logic Steps:
            1. Input clamp — invalid values safe karo
            2. Component scores calculate (0-1 each)
            3. Weighted sum = final score (0-1)
            4. Clamp final [0, 1] — floating point safety
            5. ScoreBreakdown build (typed)
            6. ScoringResult return (both scales)

        Args:
            distance_km:        Donor se hospital distance
            radius_km:          Search radius
            reliability_score:  DB se 0-100
            response_rate:      DB se 0-100
            last_donation_date: Last donation ya None
            is_available:       Currently available?

        Returns:
            ScoringResult with ai_score (0-1), display (0-100),
            and typed ScoreBreakdown
        """
        # ─── Step 1: Input validation ──────────────────────
        # ✅ Bug Fix 6: Clamp all inputs
        distance_km       = max(0.0, distance_km)
        radius_km         = max(0.1, radius_km)
        reliability_score = max(0.0, min(SCORE_SCALE, reliability_score))
        response_rate     = max(0.0, min(SCORE_SCALE, response_rate))

        # ─── Step 2: Component scores ──────────────────────
        dist_score = self._dist_scorer.score(
            distance_km, radius_km
        )
        rel_score = self._rel_scorer.score(reliability_score)
        elig_score = self._elig_scorer.score(
            last_donation_date, is_available
        )
        resp_score = self._resp_scorer.score(response_rate)

        # ─── Step 3: Weighted sum ───────────────────────────
        # Logic:
        #   Sab weights milake 1.0 honi chahiye
        #   AIWeightsConfig.validate_weights_sum() verify karta
        #   final = Σ(weight_i × score_i)
        final_score = (
                self._weights.weight_distance      * dist_score
                + self._weights.weight_reliability * rel_score
                + self._weights.weight_eligibility * elig_score
                + self._weights.weight_response_rate * resp_score
        )

        # ─── Step 4: Clamp final ────────────────────────────
        # Floating point operations se 1.0000001 possible
        final_score = round(min(1.0, max(0.0, final_score)), 4)

        # ─── Step 5: ScoreBreakdown ─────────────────────────
        # ✅ Bug Fix 4: Typed ScoreBreakdown — dict nahi
        breakdown = ScoreBreakdown(
            distance_score      = dist_score,
            reliability_score   = rel_score,
            eligibility_score   = elig_score,
            response_rate_score = resp_score,
            final_score         = final_score,
            weights_used        = {
                "distance":      self._weights.weight_distance,
                "reliability":   self._weights.weight_reliability,
                "eligibility":   self._weights.weight_eligibility,
                "response_rate": self._weights.weight_response_rate,
            }
        )

        # ─── Step 6: ScoringResult ──────────────────────────
        # ✅ Bug Fix 5: Dono scales maintain karo
        return ScoringResult(
            ai_score         = final_score,                          # 0.0-1.0
            ai_score_display = round(final_score * SCORE_SCALE, 2), # 0.0-100.0
            breakdown        = breakdown,
        )

    def is_eligible(
            self,
            last_donation_date: Optional[date],
            is_available:       bool
    ) -> bool:
        """Quick eligibility check — full score nahi."""
        return self._elig_scorer.score(
            last_donation_date, is_available
        ) == 1.0

    def days_until_eligible(
            self,
            last_donation_date: Optional[date]
    ) -> int:
        """Frontend display ke liye — kitne din baad eligible."""
        return self._elig_scorer.days_until_eligible(
            last_donation_date
        )


# ═══════════════════════════════════════════════════════════
# MODULE-LEVEL SINGLETON
# ═══════════════════════════════════════════════════════════
#
# Logic:
#   Default scorer — baar baar instantiate mat karo
#   Testing mein override possible
#   DonorScoringService yahan se import karega

_scorer = DonorAIScorer()


# ═══════════════════════════════════════════════════════════
# CONVENIENCE FUNCTIONS — Public API + Backward Compat
# ═══════════════════════════════════════════════════════════

def calculate_ai_score(
        distance_km:        float,
        radius_km:          float,
        reliability_score:  float,
        response_rate:      float,
        last_donation_date: Optional[date],
        is_available:       bool,
        weights:            Optional[AIWeightsConfig] = None,
) -> tuple[float, ScoreBreakdown]:
    """
    AI score calculate karo — convenience function.

    ✅ Bug Fix 1: Trailing comma removed
    ✅ Bug Fix 2: Module-level settings removed
    ✅ Bug Fix 4: ScoreBreakdown typed return

    Returns:
        Tuple of (ai_score_display 0-100, ScoreBreakdown)

    Example:
        score, breakdown = calculate_ai_score(
            distance_km=5.0, radius_km=25.0,
            reliability_score=80.0, response_rate=90.0,
            last_donation_date=None, is_available=True
        )
        print(score)  # 85.4
    """
    scorer = DonorAIScorer(weights=weights) if weights else _scorer
    result = scorer.calculate(
        distance_km, radius_km,
        reliability_score, response_rate,
        last_donation_date, is_available
    )
    # ✅ Bug Fix 1: No trailing comma!
    return result.ai_score_display, result.breakdown


def calculate_eligibility_score(
        last_donation_date: Optional[date],
        is_available:       bool
) -> float:
    """
    Eligibility score — backward compatible.

    Rules:
        Unavailable      → 0.0
        Never donated    → 1.0
        < 90 days        → 0.0
        >= 90 days       → 1.0

    Returns:
        1.0 if eligible, 0.0 if not
    """
    scorer = EligibilityScorer()
    return scorer.score(last_donation_date, is_available)