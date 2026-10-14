import math
from typing import Protocol, runtime_checkable


def _deduplicate_donors(donors: list[dict]) -> list[dict]:
    """Deduplicate donors by donor_id or id, preserving first occurrence."""
    seen_ids = set()
    deduped = []
    for d in donors:
        d_id = d.get("id") or d.get("donor_id")
        if d_id is not None:
            if d_id in seen_ids:
                continue
            seen_ids.add(d_id)
        deduped.append(d)
    return deduped


def _safe_float(val: any, default: float = 0.0) -> float:
    """Safely convert value to float, handling None and NaN."""
    if val is None:
        return default
    try:
        f = float(val)
        return default if math.isnan(f) else f
    except (ValueError, TypeError):
        return default


def _default_sort_key(d: dict) -> tuple:
    """
    Deterministic sort key for default ranking:
    1. Highest ai_score (-score)
    2. Lowest distance_km (dist)
    3. Lowest donor_id (deterministic tie-breaker)
    """
    score = _safe_float(d.get("ai_score"), 0.0)
    dist = _safe_float(d.get("distance_km"), float("inf"))
    d_id = d.get("id") or d.get("donor_id") or 0
    return (-score, dist, d_id)


def _urgent_sort_key(d: dict) -> tuple:
    """
    Deterministic sort key for urgent ranking:
    1. Lowest distance_km (dist)
    2. Highest ai_score (-score)
    3. Lowest donor_id (deterministic tie-breaker)
    """
    dist = _safe_float(d.get("distance_km"), float("inf"))
    score = _safe_float(d.get("ai_score"), 0.0)
    d_id = d.get("id") or d.get("donor_id") or 0
    return (dist, -score, d_id)


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
#   DefaultRankingStrategy → AI score priority (deterministic tie-break)
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
    Default ranking — AI score priority with deterministic tie-breaking.

    Logic:
        1. Deduplicate candidate list
        2. Eligible donors alag karo
        3. Deterministic sort: -ai_score, distance_km, donor_id
        4. Eligible pehle + ineligible baad
        5. Limit apply karo
    """

    def rank(self, donors: list[dict], limit: int) -> list[dict]:
        """
        AI score se rank karo.
        """
        if not donors:
            return []

        safe_limit = max(1, min(limit, 100))
        unique_donors = _deduplicate_donors(donors)

        # Eligible aur ineligible alag karo
        eligible = [d for d in unique_donors if d.get("is_eligible", False)]
        ineligible = [d for d in unique_donors if not d.get("is_eligible", False)]

        # Deterministic sorting
        eligible.sort(key=_default_sort_key)
        ineligible.sort(key=_default_sort_key)

        # Eligible pehle — limit apply
        return (eligible + ineligible)[:safe_limit]


class UrgentRankingStrategy:
    """
    CRITICAL urgency ranking — distance priority with deterministic tie-breaking.

    Logic:
        Emergency mein nearest eligible donor sabse important
        Distance se sort — score nahi
        Deterministic tie-breaker: distance_km, -ai_score, donor_id
    """

    def rank(self, donors: list[dict], limit: int) -> list[dict]:
        """
        Distance se rank karo — nearest first.
        """
        if not donors:
            return []

        safe_limit = max(1, min(limit, 100))
        unique_donors = _deduplicate_donors(donors)

        eligible = [d for d in unique_donors if d.get("is_eligible", False)]
        eligible.sort(key=_urgent_sort_key)
        return eligible[:safe_limit]