# ai-service/models/request_schemas.py

from pydantic import BaseModel, ConfigDict, Field, field_validator
from typing import Optional

from models.enums import BloodGroup, UrgencyLevel

# ═══════════════════════════════════════════════════════════
# DONOR MATCH REQUEST
# ═══════════════════════════════════════════════════════════
#
# SOLID:
#   S → Sirf match request schema
#   I → Request schemas alag file — response se separate
#   D → Enum types — String nahi
#
# ✅ Bug Fix 8: model_config add kiya
#
# Logic:
#   blood_group → compatible donors dhundo
#   lat/lon → hospital location → distance calculate
#   radius_km → search boundary
#   urgency → CRITICAL=distance priority, else AI score
#   limit → max results
class DonorMatchRequest(BaseModel):
    """
    AI donor matching request.

    SOLID I: Request sirf yahan — response se separated.
    SOLID D: BloodGroup enum — string nahi.

    Logic Flow:
        1. blood_group → compatible groups find karo
        2. lat/lon + radius → DB Haversine query
        3. urgency → ranking strategy select
        4. limit → result count
    """

    # ✅ Bug Fix 8: Pydantic v2 config
    model_config = ConfigDict(
        use_enum_values      = False,  # Enum objects rakho
        str_strip_whitespace = True,
        json_schema_extra    = {
            "example": {
                "blood_group":    "A+",
                "latitude":       28.6139,
                "longitude":      77.2090,
                "radius_km":      25.0,
                "urgency":        "URGENT",
                "units_required": 2,
                "limit":          10,
                "request_id":     123
            }
        }
    )

    # ✅ Bug Fix 2: BloodGroup "A+" format
    blood_group: BloodGroup = Field(
        ...,
        description="Recipient blood group — compatible donors search"
    )

    # Hospital location
    latitude: float = Field(
        ..., ge=-90.0, le=90.0,
        description="Hospital latitude"
    )
    longitude: float = Field(
        ..., ge=-180.0, le=180.0,
        description="Hospital longitude"
    )

    # Search config
    radius_km: float = Field(
        default=25.0, ge=1.0, le=200.0,
        description="Search radius in km"
    )
    urgency: UrgencyLevel = Field(
        default=UrgencyLevel.NORMAL,
        description="CRITICAL=distance priority, else AI score"
    )
    units_required: int = Field(
        default=1, ge=1, le=10,
        description="Blood units needed"
    )
    limit: int = Field(
        default=10, ge=1, le=50,
        description="Max donors to return"
    )

    # Spring Boot BloodRequest ID — optional
    request_id: Optional[int] = Field(
        default=None,
        description="Spring Boot BloodRequest ID — tracking"
    )

    # ✅ Blood group validator — flexible parsing
    @field_validator('blood_group', mode='before')
    @classmethod
    def validate_blood_group(cls, v) -> BloodGroup:
        """
        "A+", "A_POSITIVE", "a+" → BloodGroup enum.

        Logic:
            Frontend/Spring Boot different formats bhej sakta hai
            BloodGroup.from_string() → flexible parsing
            None/invalid → ValueError with clear message
        """
        if isinstance(v, BloodGroup):
            return v
        result = BloodGroup.from_string(str(v))
        if result is None:
            valid = [bg.value for bg in BloodGroup]
            raise ValueError(
                f"Invalid blood group: '{v}'.\n"
                f"Valid values: {valid}"
            )
        return result

    def get_compatible_groups(self) -> list[BloodGroup]:
        """
        Compatible donor blood groups.

        Logic:
            blood_group.get_compatible_donors() call karo
            matching_service.py mein use hoga
            SQL IN clause ke liye string values
        """
        return self.blood_group.get_compatible_donors()


# ═══════════════════════════════════════════════════════════
# DEMAND PREDICTION REQUEST
# ═══════════════════════════════════════════════════════════
#
# SOLID:
#   S → Sirf prediction request schema
#
# Logic:
#   city → historical data city filter
#   blood_group → None = sab groups
#   days_ahead → forecast period
class DemandPredictionRequest(BaseModel):
    """
    Blood demand prediction request.

    Logic:
        city + blood_group → DB se 90-day history
        days_ahead → forecast calculate karo
        Trend analyze → recommendation generate
    """

    model_config = ConfigDict(
        str_strip_whitespace = True,
        json_schema_extra    = {
            "example": {
                "city":       "Delhi",
                "blood_group": "O+",
                "days_ahead":  30
            }
        }
    )

    city: str = Field(
        ..., min_length=2, max_length=100,
        description="City name for prediction"
    )
    blood_group: Optional[BloodGroup] = Field(
        default=None,
        description="Blood group filter (None = all groups)"
    )
    days_ahead: int = Field(
        default=30, ge=1, le=90,
        description="Prediction period in days"
    )

    # City normalize karo
    @field_validator('city')
    @classmethod
    def normalize_city(cls, v: str) -> str:
        """
        City name normalize karo.

        Logic:
            "delhi" → "Delhi" (title case)
            " Mumbai " → "Mumbai" (strip)
            DB query case-insensitive hogi
        """
        return v.strip().title()