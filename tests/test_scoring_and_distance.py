# ai-service/tests/test_scoring_and_distance.py

from datetime import date, timedelta
import pytest

from models.enums import BloodGroup
from utils.distance import Coordinate, haversine_distance
from utils.scoring import EligibilityScorer, DistanceScorer, DonorAIScorer


class TestDistanceCalculations:
    """Test haversine calculations and edge cases."""

    def test_same_coordinates_returns_zero(self):
        dist = haversine_distance(28.6139, 77.2090, 28.6139, 77.2090)
        assert dist == 0.0

    def test_known_distance_delhi_mumbai(self):
        """Delhi (28.6139, 77.2090) to Mumbai (19.0760, 72.8777) is approx 1150-1160 km."""
        dist = haversine_distance(28.6139, 77.2090, 19.0760, 72.8777)
        assert 1140.0 < dist < 1170.0

    def test_coordinate_out_of_bounds_raises_value_error(self):
        with pytest.raises(ValueError):
            Coordinate(95.0, 77.0)  # lat > 90

        with pytest.raises(ValueError):
            Coordinate(28.0, 190.0)  # lon > 180


class TestEligibilityRules:
    """Test 90-day medical eligibility rule."""

    def test_unavailable_donor_is_ineligible(self):
        scorer = EligibilityScorer()
        assert scorer.score(last_donation_date=None, is_available=False) == 0.0

    def test_never_donated_donor_is_eligible(self):
        scorer = EligibilityScorer()
        assert scorer.score(last_donation_date=None, is_available=True) == 1.0

    def test_donated_89_days_ago_is_ineligible(self):
        scorer = EligibilityScorer()
        recent = date.today() - timedelta(days=89)
        assert scorer.score(last_donation_date=recent, is_available=True) == 0.0
        assert scorer.days_until_eligible(recent) == 1

    def test_donated_90_days_ago_is_eligible(self):
        scorer = EligibilityScorer()
        eligible_date = date.today() - timedelta(days=90)
        assert scorer.score(last_donation_date=eligible_date, is_available=True) == 1.0
        assert scorer.days_until_eligible(eligible_date) == 0

    def test_donated_150_days_ago_is_eligible(self):
        scorer = EligibilityScorer()
        old_date = date.today() - timedelta(days=150)
        assert scorer.score(last_donation_date=old_date, is_available=True) == 1.0
        assert scorer.days_until_eligible(old_date) == 0


class TestBloodGroupCompatibilityMatrix:
    """Verify ABO + Rh compatibility matrix against universal blood banking rules."""

    def test_o_negative_can_receive_only_from_o_negative(self):
        compatible = BloodGroup.O_NEGATIVE.get_compatible_donors()
        assert compatible == [BloodGroup.O_NEGATIVE]

    def test_ab_positive_is_universal_recipient(self):
        compatible = BloodGroup.AB_POSITIVE.get_compatible_donors()
        assert len(compatible) == 8  # can receive from all 8 blood groups

    def test_a_positive_compatible_donors(self):
        compatible = BloodGroup.A_POSITIVE.get_compatible_donors()
        assert set(compatible) == {
            BloodGroup.A_POSITIVE,
            BloodGroup.A_NEGATIVE,
            BloodGroup.O_POSITIVE,
            BloodGroup.O_NEGATIVE,
        }
