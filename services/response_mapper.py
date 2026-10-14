# ai-service/services/response_mapper.py

from models.response_schemas import MatchedDonor
from models.common import ScoreBreakdown
from models.enums import BloodGroup


# ═══════════════════════════════════════════════════════════
# DONOR RESPONSE MAPPER
# ═══════════════════════════════════════════════════════════
#
# SOLID:
#   S → Sirf dict → MatchedDonor mapping
#
# ✅ Bug Fix 4: phone_masked — privacy
# ✅ Bug Fix 5: blood_group_display correct
# ✅ Bug Fix 6: ai_score = 0-1 (schema ke liye)
#
# Logic:
#   Scored donor dict → MatchedDonor Pydantic model
#   Privacy: phone mask karo
#   Type safety: ScoreBreakdown typed
#   Scale: ai_score = 0-1 (schema validation pass)

class DonorResponseMapper:
    """
    Scored donor dict → MatchedDonor response.

    SOLID S: Sirf mapping logic.

    ✅ Bug Fix 4: phone_masked — GDPR compliance
    ✅ Bug Fix 5: blood_group already "A+" format
    ✅ Bug Fix 6: ai_score = 0-1 for schema

    Usage:
        mapper = DonorResponseMapper()
        donors = mapper.to_matched_donors(scored_donors)
    """

    @staticmethod
    def to_matched_donor(
            donor: dict,
            rank:  int
    ) -> MatchedDonor:
        """
        Single donor dict → MatchedDonor.

        ✅ Bug Fix 4: Phone masked
        ✅ Bug Fix 5: blood_group_display = "A+" (already correct)
        ✅ Bug Fix 6: ai_score = 0-1

        Args:
            donor: Scored donor dict
            rank:  Match rank (1=best)

        Returns:
            MatchedDonor Pydantic model
        """
        # Convert DB enum string (e.g. A_POSITIVE) to API display format (e.g. A+)
        db_blood_group = donor["blood_group"]
        bg_enum = BloodGroup.from_string(db_blood_group)
        blood_group = bg_enum.value if bg_enum else db_blood_group

        # ✅ Bug Fix 4: Privacy — phone mask
        phone_masked = MatchedDonor.mask_phone(
            donor.get("phone")
        )

        # ✅ Bug Fix 6: ai_score = 0-1 (schema validation)
        # ScoreBreakdown typed — not dict
        breakdown: ScoreBreakdown = donor["score_breakdown"]

        return MatchedDonor(
            donor_id           = donor["id"],
            user_id            = donor["user_id"],
            rank               = rank,
            name               = donor.get("name") or f"Donor #{donor.get('id', donor.get('donor_id', 'Unknown'))}",
            phone_masked       = phone_masked,      # ✅ Privacy (None when phone not fetched)
            blood_group        = blood_group,
            blood_group_display = blood_group,       # ✅ Already "A+"
            city               = donor["city"],
            latitude           = float(donor["latitude"]),
            longitude          = float(donor["longitude"]),
            distance_km        = round(donor["distance_km"], 2),
            reliability_score  = float(
                donor.get("reliability_score") or 50.0
            ),
            response_rate      = float(
                donor.get("response_rate") or 0.0
            ),
            total_donations    = int(
                donor.get("total_donations") or 0
            ),
            is_available       = bool(donor["is_available"]),
            is_eligible        = donor["is_eligible"],
            last_donation_date = donor.get("last_donation_date"),
            next_eligible_date = donor.get("next_eligible_date"),
            ai_score           = donor["ai_score"],  # ✅ 0-1
            score_breakdown    = breakdown,           # ✅ Typed
        )

    @staticmethod
    def to_matched_donors(donors: list[dict]) -> list[MatchedDonor]:
        """Batch mapping — rank auto-assign."""
        return [
            DonorResponseMapper.to_matched_donor(d, rank)
            for rank, d in enumerate(donors, start=1)
        ]