# ai-service/models/response_schemas.py

from datetime import date, datetime, timezone
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from models.common import ScoreBreakdown
from models.enums import BloodGroup, TrendDirection, UrgencyLevel


# ═══════════════════════════════════════════════════════════
# MATCHED DONOR
# ═══════════════════════════════════════════════════════════
#
# SOLID:
#   S → Sirf matched donor response data
#   I → Response alag file — request se separate
#
# ✅ Bug Fix 3: phone_masked — privacy
# ✅ Bug Fix 4: ScoreBreakdown typed
#
# Logic:
#   AI scored donor ka complete data
#   rank → 1 = best match
#   ai_score → 0.0-1.0 (weighted formula result)
#   phone_masked → privacy — full number sirf acceptance pe
#
# System Design:
#   DonorResponseMapper.py → dict → MatchedDonor
#   Frontend → rank, ai_score, score_breakdown display
class MatchedDonor(BaseModel):
    """
    AI matched donor — complete details.

    SOLID S: Sirf matched donor response data.
    Privacy: phone_masked — full number protected.

    Fields:
        rank=1 → best match
        ai_score=0.0-1.0 → higher is better
        phone_masked → "98****3210" format
    """

    model_config = ConfigDict(
        populate_by_name = True,
        use_enum_values  = True,
    )

    # Identification
    donor_id: int = Field(..., gt=0)
    user_id:  int = Field(..., gt=0)
    rank:     int = Field(..., ge=1, description="1=best match")

    # User info
    name: str = Field(..., min_length=1)

    # ✅ Bug Fix 3: Privacy — masked phone
    # Logic:
    #   "9876543210" → "98****3210"
    #   Full number sirf after acceptance share karo
    #   GDPR/Privacy compliance
    phone_masked: Optional[str] = Field(
        default=None,
        description="Masked phone (98****3210) — privacy"
    )

    # Blood info
    blood_group:         str = Field(..., description="e.g. A+")
    blood_group_display: str = Field(..., description="Display: A+")

    # Location
    city:      str   = Field(...)
    latitude:  float = Field(..., ge=-90,  le=90)
    longitude: float = Field(..., ge=-180, le=180)

    # Distance
    distance_km: float = Field(
        ..., ge=0,
        description="Distance from hospital"
    )

    # Donor statistics
    reliability_score: float = Field(..., ge=0, le=100)
    response_rate:     float = Field(..., ge=0, le=100)
    total_donations:   int   = Field(..., ge=0)

    # Status
    is_available: bool
    is_eligible:  bool

    # Dates
    last_donation_date: Optional[date] = None
    next_eligible_date: Optional[date] = None

    # AI Scoring
    ai_score: float = Field(
        ..., ge=0.0, le=1.0,
        description="AI score 0.0-1.0"
    )

    # ✅ Bug Fix 4: Typed ScoreBreakdown — dict nahi
    score_breakdown: ScoreBreakdown = Field(
        ...,
        description="Detailed score components"
    )

    # ✅ Phone masking utility
    @staticmethod
    def mask_phone(phone: Optional[str]) -> Optional[str]:
        """
        Phone number mask karo — privacy.

        Logic:
            "9876543210" → "98****3210"
            Short numbers → "****"
            None → None

        System Design:
            DonorResponseMapper use karega
            GDPR compliance ke liye
        """
        if not phone:
            return None
        phone = phone.strip()
        if len(phone) < 6:
            return "****"
        visible_start = 2
        visible_end   = 4
        masked_count  = len(phone) - visible_start - visible_end
        return (
                phone[:visible_start]
                + "*" * masked_count
                + phone[-visible_end:]
        )

    @property
    def ai_score_display(self) -> float:
        """Display ke liye 0-100 scale."""
        return round(self.ai_score * 100, 1)

    @property
    def is_top_match(self) -> bool:
        """Top 3 mein hai?"""
        return self.rank <= 3


# ═══════════════════════════════════════════════════════════
# DONOR MATCH RESPONSE
# ═══════════════════════════════════════════════════════════
#
# SOLID:
#   S → Sirf match endpoint response
#
# ✅ Bug Fix 5: BloodGroup, UrgencyLevel enum types
#
# Logic:
#   Matched donors list + search metadata
#   processing_time_ms → performance monitoring
#   cached → Redis hit ya DB hit?
class DonorMatchResponse(BaseModel):
    """
    AI donor matching endpoint response.

    SOLID S: Match response only — prediction nahi.

    ✅ Bug Fix 5: blood_group = BloodGroup enum
    ✅ Bug Fix 5: urgency = UrgencyLevel enum
    """

    model_config = ConfigDict(use_enum_values=True)

    # Request tracking
    request_id: Optional[int] = Field(
        default=None,
        description="Spring Boot BloodRequest ID"
    )

    # ✅ Bug Fix 5: Enum types
    blood_group: BloodGroup   = Field(..., description="Requested blood group")
    urgency:     UrgencyLevel = Field(..., description="Request urgency")

    # Results
    total_found: int = Field(..., ge=0)
    donors: list[MatchedDonor] = Field(
        default_factory=list,
        description="Ranked matched donors (rank=1 is best)"
    )

    # Metadata
    compatible_groups_searched: list[str] = Field(
        default_factory=list,
        description="All blood groups searched"
    )
    search_radius_km:   float = Field(..., gt=0)
    processing_time_ms: float = Field(..., ge=0)

    # Extra info
    algorithm_version: str  = Field(default="2.0.0")
    cached:            bool = Field(
        default=False,
        description="Result from Redis cache?"
    )

    # Utility methods
    def has_results(self) -> bool:
        """Koi donors mile?"""
        return self.total_found > 0

    def get_top_donor(self) -> Optional[MatchedDonor]:
        """Best match return karo."""
        return self.donors[0] if self.donors else None

    def get_eligible_count(self) -> int:
        """Eligible donors count."""
        return sum(1 for d in self.donors if d.is_eligible)


# ═══════════════════════════════════════════════════════════
# DEMAND PREDICTION
# ═══════════════════════════════════════════════════════════
#
# SOLID:
#   S → Sirf prediction response
#
# ✅ Bug Fix 6: TrendDirection enum
# ✅ Bug Fix 7: confidence range 0-1
#
# Logic:
#   Historical 90-day data → trend → forecast
#   confidence → kitna accurate prediction hai
#   peak_days → high demand days
class DemandPrediction(BaseModel):
    """
    Blood demand prediction response.

    ✅ Bug Fix 6: trend = TrendDirection enum
    ✅ Bug Fix 7: confidence = 0.0-1.0 validated

    Logic:
        predicted_requests → daily_avg × days_ahead
        confidence → data quality se derive
        peak_days → weekday distribution se
    """

    model_config = ConfigDict(use_enum_values=True)

    # Request echo
    city:        str                  = Field(...)
    blood_group: Optional[BloodGroup] = Field(default=None)
    period_days: int                  = Field(..., ge=1, le=90)

    # Prediction
    predicted_requests: int = Field(..., ge=0)

    # ✅ Bug Fix 7: confidence 0-1 range enforce
    confidence: float = Field(
        ..., ge=0.0, le=1.0,
        description="Confidence 0.0-1.0 (0.7+ = high confidence)"
    )

    # ✅ Bug Fix 6: TrendDirection enum — String nahi
    trend: TrendDirection = Field(
        ...,
        description="Demand trend direction"
    )

    # Peak days
    peak_days: list[str] = Field(
        default_factory=list,
        description="High demand days of week"
    )

    # Human readable recommendation
    recommendation: str = Field(
        ..., max_length=500,
        description="Action recommendation"
    )

    # Additional stats
    historical_avg: Optional[float] = Field(
        default=None,
        description="Historical daily average"
    )
    predicted_peak: Optional[int] = Field(
        default=None,
        description="Expected peak demand"
    )

    @property
    def confidence_percent(self) -> int:
        """Display ke liye percentage."""
        return round(self.confidence * 100)

    @property
    def is_high_confidence(self) -> bool:
        """70%+ confidence = high."""
        return self.confidence >= 0.70

    @property
    def needs_action(self) -> bool:
        """Immediate action needed?"""
        return (
                self.trend == TrendDirection.INCREASING
                and self.is_high_confidence
        )


# ═══════════════════════════════════════════════════════════
# HEALTH RESPONSE
# ═══════════════════════════════════════════════════════════
#
# SOLID:
#   S → Sirf health check response
#
# ✅ Bug Fix 1: Trailing comma removed
# ✅ Bug Fix 9: Redis + Model status added
#
# Logic:
#   status → healthy/degraded/unhealthy
#   db_connected → MySQL alive?
#   redis_connected → Cache alive?
#   model_loaded → ML model ready?
#   timestamp → UTC time
class HealthResponse(BaseModel):
    """
    Service health check response.

    ✅ Bug Fix 1: Trailing comma removed
    ✅ Bug Fix 9: Redis + Model status added

    Status Values:
        healthy   → sab components OK
        degraded  → non-critical fail (Redis down)
        unhealthy → critical fail (DB down)

    Kubernetes:
        200 → healthy/degraded → traffic route karo
        503 → unhealthy → traffic route mat karo
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "status":          "healthy",
                "service":         "Blood Donor AI Service",
                "version":         "1.0.0",
                "db_connected":    True,
                "redis_connected": True,
                "model_loaded":    True,
                "timestamp":       "2024-03-27T10:00:00Z"
            }
        }
    )

    # Status
    status:  str = Field(..., description="healthy|degraded|unhealthy")
    service: str = Field(..., description="Service name")
    version: str = Field(..., description="Service version")

    # Component health
    db_connected: bool = Field(..., description="MySQL connected?")

    # ✅ Bug Fix 9: Missing components added
    redis_connected: bool = Field(
        default=False,
        description="Redis cache connected?"
    )
    model_loaded: bool = Field(
        default=False,
        description="ML model loaded?"
    )

    # ✅ Bug Fix 1: No trailing comma!
    # UTC timestamp — always timezone aware
    timestamp: datetime = Field(  # ← COMMA NAHI!
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp"
    )

    @property
    def is_healthy(self) -> bool:
        """Fully healthy?"""
        return self.status == "healthy"

    @property
    def is_fully_operational(self) -> bool:
        """Sab components OK?"""
        return (
                self.db_connected
                and self.redis_connected
                and self.model_loaded
        )


# ═══════════════════════════════════════════════════════════
# ERROR RESPONSE
# ═══════════════════════════════════════════════════════════
#
# SOLID:
#   S → Sirf error response schema
#
# Logic:
#   GlobalExceptionHandler se match karo
#   Production mein detail hide karo
#   Debug mein detail show karo
class ErrorResponse(BaseModel):
    """Standard error response — all endpoints pe consistent."""

    success:   bool         = False
    error:     str          = Field(..., description="User-friendly message")
    detail:    Optional[str] = Field(
        default=None,
        description="Debug detail (hidden in production)"
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )