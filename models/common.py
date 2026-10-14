# ai-service/models/common.py

from pydantic import BaseModel, ConfigDict, Field

# ═══════════════════════════════════════════════════════════
# SCORE BREAKDOWN
# ═══════════════════════════════════════════════════════════
#
# SOLID:
#   S → Sirf score breakdown data hold karna
#   I → Request/Response dono use karte hain — shared
#
# ✅ Bug Fix 4: Typed class — dict nahi
#
# Logic:
#   AI scoring formula ka detailed breakdown
#   Har component separately track karo
#   Frontend pe progress bars show karne ke liye
#   Transparency — user ko pata chale score kyun aaya
#
# System Design:
#   scoring.py → ScoringResult.breakdown = ScoreBreakdown
#   response_schemas.py → MatchedDonor.score_breakdown
#   Java → ScoreBreakdown.java se match
class ScoreBreakdown(BaseModel):
    """
    AI matching score ka detailed breakdown.

    SOLID S: Sirf score data container — logic nahi.
    SOLID I: Shared between request + response schemas.

    Score Formula:
        final = (distance    × weight_distance)
              + (reliability × weight_reliability)
              + (eligibility × weight_eligibility)
              + (response    × weight_response_rate)

    Range: 0.0 to 1.0 (each component + final)
    """

    model_config = ConfigDict(
        frozen=True  # ✅ Immutable — scoring ke baad change nahi
    )

    # Distance score — 0.0 to 1.0
    # Explanation: Nearby donors → high score (exponential decay)
    distance_score: float = Field(
        ..., ge=0.0, le=1.0,
        description="Normalized distance score (1.0=same location)"
    )

    # Reliability score — 0.0 to 1.0
    # Explanation: DB 0-100 → normalize → 0-1
    reliability_score: float = Field(
        ..., ge=0.0, le=1.0,
        description="Normalized reliability score"
    )

    # Eligibility — binary 0.0 or 1.0
    # Explanation: 90-day rule — eligible=1.0, not=0.0
    eligibility_score: float = Field(
        ..., ge=0.0, le=1.0,
        description="1.0=eligible, 0.0=not eligible"
    )

    # Response rate — 0.0 to 1.0
    # Explanation: DB 0-100 → normalize → 0-1
    response_rate_score: float = Field(
        ..., ge=0.0, le=1.0,
        description="Normalized response rate"
    )

    # Final weighted score — 0.0 to 1.0
    final_score: float = Field(
        ..., ge=0.0, le=1.0,
        description="Final weighted AI score"
    )

    # Weights used — transparency ke liye
    weights_used: dict[str, float] = Field(
        default_factory=dict,
        description="Weights applied in calculation"
    )

    @property
    def final_score_percent(self) -> float:
        """Display ke liye 0-100."""
        return round(self.final_score * 100, 1)