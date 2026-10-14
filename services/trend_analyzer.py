# ai-service/services/trend_analyzer.py

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from models.enums import TrendDirection


# ═══════════════════════════════════════════════════════════
# TREND RESULT
# ═══════════════════════════════════════════════════════════
#
# SOLID:
#   S → Sirf result data container
#
# Logic:
#   Trend analysis ka complete result
#   frozen=True → immutable → thread-safe
#   daily_average → prediction formula mein use

@dataclass(frozen=True)
class TrendResult:
    """
    Trend analysis ka typed result.

    SOLID S: Sirf data container — logic nahi.

    Attributes:
        direction:     TrendDirection enum
        confidence:    0.0-1.0 (kitna accurate)
        recent_count:  Last 30 days count
        previous_count: 31-60 days count
        daily_average: Average daily requests
    """
    direction:      TrendDirection
    confidence:     float
    recent_count:   int
    previous_count: int
    daily_average:  float


# ═══════════════════════════════════════════════════════════
# TREND ANALYZER PROTOCOL
# ═══════════════════════════════════════════════════════════
#
# SOLID:
#   D → PredictionService is pe depend karo
#   O → Naya algorithm = new class — existing change nahi

@runtime_checkable
class TrendAnalyzerStrategy(Protocol):
    """
    Trend analyzer protocol.

    SOLID D: PredictionService depend karta hai.
    SOLID O: Naya algorithm = new class.
    """
    def analyze(
            self,
            past_data:     list[dict],
            lookback_days: int
    ) -> TrendResult:
        """Trend analyze karo."""
        ...


# ═══════════════════════════════════════════════════════════
# DEFAULT TREND ANALYZER
# ═══════════════════════════════════════════════════════════
#
# SOLID:
#   S → Sirf trend analysis ka kaam
#
# ✅ Bug Fix 4: TrendDirection enum — string nahi
# ✅ Bug Fix 7: None-safe comparison
# ✅ Bug Fix 10: Named constants
#
# Logic:
#   recent_30 vs previous_30 compare karo
#   20% increase → INCREASING (confidence=0.72)
#   20% decrease → DECREASING (confidence=0.68)
#   Range mein → STABLE (confidence=0.75)
#   No previous data → STABLE (confidence=0.50)
#
# Why different confidence values?
#   INCREASING: 0.72 → bata sakte hain demand badh rahi
#   DECREASING: 0.68 → thoda less confident (outliers possible)
#   STABLE: 0.75 → most predictable state
#   No prev: 0.50 → uncertain — sirf recent data

class DefaultTrendAnalyzer:
    """
    Moving average trend analyzer.

    SOLID S: Sirf trend calculation.
    SOLID O: Replace with ML-based analyzer karo.

    ✅ Bug Fix 4: TrendDirection enum
    ✅ Bug Fix 7: None-safe comparison

    Algorithm:
        recent_30   = requests in last 30 days
        previous_30 = requests in 31-60 days
        Compare ratio → trend determine

    Thresholds:
        > 1.20 → INCREASING (20% increase)
        < 0.80 → DECREASING (20% decrease)
        else   → STABLE
    """

    # Threshold constants
    INCREASE_THRESHOLD = 1.20  # 20% increase
    DECREASE_THRESHOLD = 0.80  # 20% decrease

    # Confidence values
    CONFIDENCE_INCREASING = 0.72
    CONFIDENCE_DECREASING = 0.68
    CONFIDENCE_STABLE     = 0.75
    CONFIDENCE_NO_PREV    = 0.50

    def analyze(
            self,
            past_data:     list[dict],
            lookback_days: int = 90
    ) -> TrendResult:
        """
        Trend analyze karo — moving average.

        ✅ Bug Fix 4: TrendDirection enum return
        ✅ Bug Fix 7: None-safe days_ago comparison

        Logic:
            1. daily_average = total / lookback_days
            2. recent_30 + previous_30 count karo
            3. Ratio compare → trend determine
            4. TrendDirection + confidence return

        Args:
            past_data:     DB se historical records
            lookback_days: Total lookback period

        Returns:
            TrendResult with direction + confidence
        """
        total     = len(past_data)
        daily_avg = round(total / max(1, lookback_days), 3)

        # ✅ Bug Fix 7: None-safe comparison
        recent_30 = sum(
            1 for d in past_data
            if d.get("days_ago") is not None
            and int(d["days_ago"]) <= 30
        )
        previous_30 = sum(
            1 for d in past_data
            if d.get("days_ago") is not None
            and 30 < int(d["days_ago"]) <= 60
        )

        # ✅ Bug Fix 4: TrendDirection enum
        if previous_30 == 0:
            # Previous period data nahi → uncertain
            direction  = TrendDirection.STABLE
            confidence = self.CONFIDENCE_NO_PREV

        elif recent_30 > previous_30 * self.INCREASE_THRESHOLD:
            # 20%+ increase → INCREASING
            direction  = TrendDirection.INCREASING
            confidence = self.CONFIDENCE_INCREASING

        elif recent_30 < previous_30 * self.DECREASE_THRESHOLD:
            # 20%+ decrease → DECREASING
            direction  = TrendDirection.DECREASING
            confidence = self.CONFIDENCE_DECREASING

        else:
            # Within range → STABLE
            direction  = TrendDirection.STABLE
            confidence = self.CONFIDENCE_STABLE

        return TrendResult(
            direction      = direction,
            confidence     = round(confidence, 2),
            recent_count   = recent_30,
            previous_count = previous_30,
            daily_average  = daily_avg,
        )