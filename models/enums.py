# ai-service/models/enums.py

from enum import Enum
from typing import Optional

# ═══════════════════════════════════════════════════════════
# BLOOD GROUP ENUM
# ═══════════════════════════════════════════════════════════
#
# SOLID:
#   S → Sirf blood group enum define karna
#   O → Naya group = value add karo — schemas change nahi
#   D → Spring Boot @JsonValue se match — coupling avoid
#
# Logic:
#   str mixin → JSON serialize automatically
#   Spring Boot BloodGroup.java mein @JsonValue "A+" return karta hai
#   Python mein same values → JSON compatible
#
# System Design:
#   Spring Boot → Python: "A+" JSON mein aata hai
#   Python BloodGroup.A_POSITIVE = "A+" → match!
#   Bina yeh match ke → donor matching fail hoga
class BloodGroup(str, Enum):
    """
    Blood group enum — Spring Boot @JsonValue compatible.

    SOLID O:
        Naya blood group = bas yahan add karo.
        Request/Response schemas change nahi hote.

    Spring Boot Compatibility:
        Java: BloodGroup.A_POSITIVE → @JsonValue → "A+"
        Python: BloodGroup.A_POSITIVE = "A+"
        Match ✅ → JSON serialization correct

    Medical Compatibility Rules:
        get_compatible_donors() → donor search mein use
        AB+ → universal recipient (sab se le sakta hai)
        O- → universal donor (sab ko de sakta hai)
    """
    A_POSITIVE  = "A+"
    A_NEGATIVE  = "A-"
    B_POSITIVE  = "B+"
    B_NEGATIVE  = "B-"
    AB_POSITIVE = "AB+"
    AB_NEGATIVE = "AB-"
    O_POSITIVE  = "O+"
    O_NEGATIVE  = "O-"

    @classmethod
    def from_string(cls, value: str) -> Optional['BloodGroup']:
        """
        String → BloodGroup parse karo.

        Logic:
            "A+" → BloodGroup.A_POSITIVE (direct match)
            "A_POSITIVE" → BloodGroup.A_POSITIVE (name match)
            "a+" → BloodGroup.A_POSITIVE (case insensitive)
            Unknown → None (crash nahi)

        Args:
            value: Blood group string any format mein

        Returns:
            BloodGroup enum ya None if invalid
        """
        if not value:
            return None

        # Direct value match — "A+"
        try:
            return cls(value.strip())
        except ValueError:
            pass

        # Name match — "A_POSITIVE"
        try:
            return cls[value.strip().upper()]
        except KeyError:
            pass

        # Case insensitive value match
        value_lower = value.strip().lower()
        for member in cls:
            if member.value.lower() == value_lower:
                return member

        return None

    def get_compatible_donors(self) -> list['BloodGroup']:
        """
        Compatible donor blood groups return karo.

        Logic (Medical Rules):
            Recipient blood group se compatible donors find karo
            AB+ = Universal recipient → sab donors compatible
            O- = Universal donor → sirf O- receive kar sakta hai

        System Design:
            matching_service.py mein use hoga
            SQL query mein IN clause ke liye
            BloodGroup enum list → string list convert karo

        Returns:
            List of compatible donor BloodGroups
        """
        compatibility: dict['BloodGroup', list['BloodGroup']] = {
            BloodGroup.A_POSITIVE: [
                BloodGroup.A_POSITIVE, BloodGroup.A_NEGATIVE,
                BloodGroup.O_POSITIVE, BloodGroup.O_NEGATIVE,
            ],
            BloodGroup.A_NEGATIVE: [
                BloodGroup.A_NEGATIVE, BloodGroup.O_NEGATIVE,
            ],
            BloodGroup.B_POSITIVE: [
                BloodGroup.B_POSITIVE, BloodGroup.B_NEGATIVE,
                BloodGroup.O_POSITIVE, BloodGroup.O_NEGATIVE,
            ],
            BloodGroup.B_NEGATIVE: [
                BloodGroup.B_NEGATIVE, BloodGroup.O_NEGATIVE,
            ],
            BloodGroup.AB_POSITIVE: list(BloodGroup),  # Universal recipient
            BloodGroup.AB_NEGATIVE: [
                BloodGroup.A_NEGATIVE, BloodGroup.B_NEGATIVE,
                BloodGroup.AB_NEGATIVE, BloodGroup.O_NEGATIVE,
            ],
            BloodGroup.O_POSITIVE: [
                BloodGroup.O_POSITIVE, BloodGroup.O_NEGATIVE,
            ],
            BloodGroup.O_NEGATIVE: [
                BloodGroup.O_NEGATIVE,  # Universal donor — sirf O- se le sakta
            ],
        }
        return compatibility.get(self, [self])


# ═══════════════════════════════════════════════════════════
# URGENCY LEVEL ENUM
# ═══════════════════════════════════════════════════════════
#
# SOLID:
#   S → Sirf urgency define karna
#   O → Naya level = yahan add karo — expiry logic change nahi
#
# Logic:
#   Spring Boot UrgencyLevel.java se match
#   CRITICAL → 6 hrs expiry → distance priority
#   URGENT   → 24 hrs expiry → balanced priority
#   NORMAL   → 48 hrs expiry → AI score priority
class UrgencyLevel(str, Enum):
    """
    Blood request urgency level.

    Spring Boot Compatibility:
        Java: UrgencyLevel.CRITICAL.name() → "CRITICAL"
        Python: UrgencyLevel.CRITICAL = "CRITICAL"
        Match ✅

    Business Rules:
        CRITICAL → 6 hrs expiry, distance priority matching
        URGENT   → 24 hrs expiry, balanced matching
        NORMAL   → 48 hrs expiry, AI score priority
    """
    NORMAL   = "NORMAL"
    URGENT   = "URGENT"
    CRITICAL = "CRITICAL"

    def get_expiry_hours(self) -> int:
        """
        Urgency ke hisaab se expiry hours.

        Logic:
            RequestExpiryProperties.java se match
            CRITICAL = emergency = 6 hrs
            URGENT = soon = 24 hrs
            NORMAL = standard = 48 hrs
        """
        expiry_map = {
            UrgencyLevel.NORMAL:   48,
            UrgencyLevel.URGENT:   24,
            UrgencyLevel.CRITICAL:  6,
        }
        return expiry_map[self]

    @property
    def is_critical(self) -> bool:
        """Emergency hai?"""
        return self == UrgencyLevel.CRITICAL


# ═══════════════════════════════════════════════════════════
# TREND DIRECTION ENUM
# ═══════════════════════════════════════════════════════════
#
# SOLID:
#   S → Sirf trend direction define karna
#   O → Naya trend = yahan add karo
#
# Logic:
#   Python AI prediction service se
#   Historical data compare → trend determine
#   lowercase → Python convention
class TrendDirection(str, Enum):
    """
    Blood demand trend direction.

    Logic:
        recent_30 vs previous_30 compare karo
        20% increase → INCREASING
        20% decrease → DECREASING
        Range mein → STABLE
    """
    INCREASING = "increasing"
    DECREASING = "decreasing"
    STABLE     = "stable"

    def get_icon(self) -> str:
        """Frontend display ke liye icon."""
        icons = {
            TrendDirection.INCREASING: "↑",
            TrendDirection.DECREASING: "↓",
            TrendDirection.STABLE:     "→",
        }
        return icons[self]

    @property
    def is_concerning(self) -> bool:
        """Demand badh rahi hai — action needed?"""
        return self == TrendDirection.INCREASING