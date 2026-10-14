# ai-service/services/recommendation_generator.py

from models.enums import TrendDirection


# ═══════════════════════════════════════════════════════════
# RECOMMENDATION GENERATOR
# ═══════════════════════════════════════════════════════════
#
# SOLID:
#   S → Sirf recommendation message generate karna
#   O → Naya trend = template dict mein add karo
#
# ✅ Bug Fix 4: TrendDirection enum use karo
# ✅ Bug Fix 6: blood_label correct format
#
# Logic:
#   Trend + city + blood_label → human_ readable message
#   Dict-based templates → O principle follow
#   Naya trend = dict mein add karo — code change nahi

class RecommendationGenerator:
    """
    Trend-based recommendation generator.

    SOLID S: Sirf message generation.
    SOLID O: Naya trend = dict extend karo.

    ✅ Bug Fix 4: TrendDirection enum.
    ✅ Bug Fix 6: blood_label direct use.

    Usage:
        gen = RecommendationGenerator()
        msg = gen.generate(
            trend=TrendDirection.INCREASING,
            city="Delhi",
            blood_label="A+",
            predicted=40,
            days=30
        )
    """

    # ✅ O: Dict-based — naya trend = yahan add karo
    _TEMPLATES = {
        TrendDirection.INCREASING: (
            "{blood_label} demand in {city} is INCREASING. "
            "Predicted {predicted} requests in {days} days. "
            "Run a donor drive campaign urgently!"
        ),
        TrendDirection.DECREASING: (
            "{blood_label} demand in {city} is DECREASING. "
            "Predicted {predicted} requests in {days} days. "
            "Build your donor database now for future needs."
        ),
        TrendDirection.STABLE: (
            "{blood_label} demand in {city} is STABLE. "
            "Predicted {predicted} requests in {days} days. "
            "Maintain current donor pool."
        ),
    }

    _DEFAULT_TEMPLATE = (
        "Predicted {predicted} requests for "
        "{blood_label} in {city} over {days} days."
    )

    def generate(
            self,
            trend:       TrendDirection,
            city:        str,
            blood_label: str,
            predicted:   int,
            days:        int,
    ) -> str:
        """
        Recommendation message generate karo.

        ✅ Bug Fix 4: TrendDirection enum
        ✅ Bug Fix 6: blood_label direct (already "A+")

        Args:
            trend:       TrendDirection enum
            city:        City name
            blood_label: Human readable blood group
            predicted:   Predicted request count
            days:        Prediction period

        Returns:
            Human readable recommendation
        """
        template = self._TEMPLATES.get(
            trend, self._DEFAULT_TEMPLATE
        )
        return template.format(
            blood_label = blood_label,
            city        = city,
            predicted   = predicted,
            days        = days,
        )