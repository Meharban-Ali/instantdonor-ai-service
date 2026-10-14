# ai-service/services/donor_ranker.py

from typing import Protocol, runtime_checkable


# ═══════════════════════════════════════════════════════════
# DONOR RANKING STRATEGY
# ═══════════════════════════════════════════════════════════
#
# SOLID:
#   S → Sirf ranking/sorting ka kaam
#   O → Naya strategy = new class — ranker change nahi
#   L → Strategies interchangeable
#
# Logic:
#   DefaultRankingStrategy → AI score priority
#   UrgentRankingStrategy  → Distance priority (CRITICAL)
#   Eligible donors pehle — medical priority

@runtime_checkable
class DonorRankingStrategy(Protocol):
    """
    Ranking strategy protocol.

    SOLID O: Naya criteria = new class.
    SOLID L: Interchangeable strategies.
    """
    def rank(self, donors: list[dict], limit: int) -> list[dict]:
        """Donors rank karo — top `limit` return."""
        ...


class DefaultRankingStrategy:
    """
    Default ranking — AI score priority.

    Logic:
        1. Eligible donors alag karo
        2. AI score se sort (highest first)
        3. Eligible pehle + ineligible baad
        4. Limit apply karo

    Use case: NORMAL/URGENT urgency
    """

    def rank(self, donors: list[dict], limit: int) -> list[dict]:
        """
        AI score se rank karo.

        Logic:
            Eligible → AI score sort → ineligible →
            AI score sort → combine → limit
        """
        # Eligible aur ineligible alag karo
        eligible   = [d for d in donors if d["is_eligible"]]
        ineligible = [d for d in donors if not d["is_eligible"]]

        # Dono AI score se sort
        eligible.sort(
            key=lambda x: x["ai_score"], reverse=True
        )
        ineligible.sort(
            key=lambda x: x["ai_score"], reverse=True
        )

        # Eligible pehle — limit apply
        return (eligible + ineligible)[:limit]


class UrgentRankingStrategy:
    """
    CRITICAL urgency ranking — distance priority.

    Logic:
        Emergency mein nearest eligible donor sabse important
        Distance se sort — score nahi
        Sirf eligible donors consider karo

    Use case: CRITICAL urgency
    """

    def rank(self, donors: list[dict], limit: int) -> list[dict]:
        """
        Distance se rank karo — nearest first.
        """
        eligible = [d for d in donors if d["is_eligible"]]
        eligible.sort(key=lambda x: x["distance_km"])
        return eligible[:limit]