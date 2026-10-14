# ai-service/tests/test_donor_ranker.py

import math
import pytest

from services.donor_ranker import DefaultRankingStrategy, UrgentRankingStrategy


class TestDonorRanking:
    """Test candidate ranking, deduplication, and deterministic ordering."""

    def test_empty_donors_returns_empty_list(self):
        default_strat = DefaultRankingStrategy()
        urgent_strat = UrgentRankingStrategy()
        assert default_strat.rank([], 10) == []
        assert urgent_strat.rank([], 10) == []

    def test_deduplication_removes_duplicate_donor_ids(self):
        """Duplicates with the same donor_id/id should be kept only once."""
        donors = [
            {"id": 1, "name": "Donor A", "ai_score": 0.85, "distance_km": 5.0, "is_eligible": True},
            {"id": 1, "name": "Donor A duplicate", "ai_score": 0.85, "distance_km": 5.0, "is_eligible": True},
            {"id": 2, "name": "Donor B", "ai_score": 0.75, "distance_km": 4.0, "is_eligible": True},
        ]
        strat = DefaultRankingStrategy()
        ranked = strat.rank(donors, 10)
        assert len(ranked) == 2
        assert [d["id"] for d in ranked] == [1, 2]

    def test_deterministic_tie_breaking_default_strategy(self):
        """
        When two donors have identical ai_score:
        1. Closer distance wins.
        2. If distance also matches, lower ID wins.
        """
        donors = [
            {"id": 10, "name": "Donor Far", "ai_score": 0.80, "distance_km": 15.0, "is_eligible": True},
            {"id": 20, "name": "Donor Near", "ai_score": 0.80, "distance_km": 5.0, "is_eligible": True},
            {"id": 5, "name": "Donor Near LowID", "ai_score": 0.80, "distance_km": 5.0, "is_eligible": True},
            {"id": 30, "name": "Donor Top", "ai_score": 0.90, "distance_km": 20.0, "is_eligible": True},
        ]
        strat = DefaultRankingStrategy()
        ranked = strat.rank(donors, 10)
        # Expected:
        # 1. Donor Top (score 0.90)
        # 2. Donor Near LowID (score 0.80, dist 5.0, id 5)
        # 3. Donor Near (score 0.80, dist 5.0, id 20)
        # 4. Donor Far (score 0.80, dist 15.0, id 10)
        ids = [d["id"] for d in ranked]
        assert ids == [30, 5, 20, 10]

    def test_deterministic_tie_breaking_urgent_strategy(self):
        """
        Urgent ranking prioritizes distance first, then ai_score, then donor_id.
        """
        donors = [
            {"id": 1, "name": "Donor A", "ai_score": 0.70, "distance_km": 10.0, "is_eligible": True},
            {"id": 2, "name": "Donor B", "ai_score": 0.90, "distance_km": 10.0, "is_eligible": True},
            {"id": 3, "name": "Donor C", "ai_score": 0.50, "distance_km": 2.0, "is_eligible": True},
            {"id": 4, "name": "Donor Ineligible", "ai_score": 0.99, "distance_km": 1.0, "is_eligible": False},
        ]
        strat = UrgentRankingStrategy()
        ranked = strat.rank(donors, 10)
        # Ineligible is ignored in urgent ranking
        # Expected:
        # 1. Donor C (dist 2.0)
        # 2. Donor B (dist 10.0, score 0.90)
        # 3. Donor A (dist 10.0, score 0.70)
        ids = [d["id"] for d in ranked]
        assert ids == [3, 2, 1]

    def test_safe_handling_of_nan_and_none(self):
        """None or NaN values in scores or distances must not raise TypeError."""
        donors = [
            {"id": 1, "name": "Donor None Score", "ai_score": None, "distance_km": 10.0, "is_eligible": True},
            {"id": 2, "name": "Donor NaN Score", "ai_score": float("nan"), "distance_km": 10.0, "is_eligible": True},
            {"id": 3, "name": "Donor Normal", "ai_score": 0.60, "distance_km": 10.0, "is_eligible": True},
            {"id": 4, "name": "Donor None Dist", "ai_score": 0.80, "distance_km": None, "is_eligible": True},
        ]
        strat = DefaultRankingStrategy()
        ranked = strat.rank(donors, 10)
        assert len(ranked) == 4
        # Normal (0.60) and None Dist (0.80) should be on top
        assert ranked[0]["id"] == 4
        assert ranked[1]["id"] == 3

    def test_eligible_placed_before_ineligible_in_default_strategy(self):
        """In default ranking, eligible donors are ranked first, followed by ineligible."""
        donors = [
            {"id": 1, "ai_score": 0.99, "distance_km": 5.0, "is_eligible": False},
            {"id": 2, "ai_score": 0.50, "distance_km": 5.0, "is_eligible": True},
        ]
        strat = DefaultRankingStrategy()
        ranked = strat.rank(donors, 10)
        assert [d["id"] for d in ranked] == [2, 1]
