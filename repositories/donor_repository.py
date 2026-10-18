# ai-service/repositories/donor_repository.py

import logging
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from models.enums import BloodGroup

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════
# DONOR REPOSITORY
# ═══════════════════════════════════════════════════════════
#
# SOLID:
#   S → Sirf DB query ka kaam
#   D → Session inject — tight coupling nahi
#
# ✅ Bug Fix 1: SQL injection fix — parameterized
#
# Logic:
#   Haversine formula SQL mein — Python loop nahi
#   LEAST(1.0,...) → acos() domain error prevent
#   :blood_groups → tuple binding → IN clause safe
#   is_available=1 filter → unavailable skip
#
# System Design:
#   MatchingService → DonorRepository → MySQL DB
#   Read-only access — Spring Boot DB
#   3x limit → AI filter karega baad mein

class DonorRepository:
    """
    Donor DB queries — read-only.

    SOLID S: Sirf DB operations.
    SOLID D: Session injected.

    ✅ Bug Fix 1: SQL injection prevented.
    Parameterized queries only.

    Usage:
        repo = DonorRepository(db)
        donors = repo.find_nearby_donors(
            lat=28.6139, lng=77.2090,
            radius_km=25.0,
            blood_groups=["A+", "A-", "O+", "O-"],
            limit=30
        )
    """

    def __init__(self, db: Session):
        self._db = db

    def find_nearby_donors(
            self,
            lat:          float,
            lng:          float,
            radius_km:    float,
            blood_groups: list[str],
            limit:        int,
    ) -> list[dict]:
        """
        MySQL Haversine query — nearby compatible donors.

        ✅ Bug Fix 1: Parameterized — SQL injection impossible

        Logic:
            Haversine formula SQL mein calculate karo
            LEAST(1.0,...) → floating point safety (like Python)
            is_available=1 → unavailable donors skip
            ORDER BY reliability → best donors pehle
            LIMIT → performance

        SQL Explanation:
            6371 × acos(LEAST(1.0, cos(lat1)×cos(lat2)×cos(lon2-lon1) + sin(lat1)×sin(lat2)))
            = Great circle distance in km
            <= radius_km → filter

        Args:
            lat, lng:     Hospital location
            radius_km:    Search radius
            blood_groups: Compatible blood group values
            limit:        Max results

        Returns:
            List of donor dicts with all fields

        Raises:
            SQLAlchemyError: DB query fail
        """
        if not blood_groups:
            logger.warning("No blood groups provided — returning empty")
            return []

        # ✅ Bug Fix 1: Parameterized — NO f-string in SQL!
        # :blood_groups → SQLAlchemy tuple binding
        # Safe from injection
        query = text("""
                     SELECT
                         dp.id,
                         dp.user_id,
                         dp.blood_group,
                         dp.city,
                         dp.latitude,
                         dp.longitude,
                         dp.is_available,
                         dp.last_donation_date,
                         dp.next_eligible_date,
                         dp.reliability_score,
                         dp.total_donations,
                         dp.response_rate
                     FROM donor_profiles dp
                              INNER JOIN users u
                                         ON dp.user_id = u.id
                     WHERE u.is_active       = true
                       AND dp.is_available   = true
                       AND dp.blood_group    IN :blood_groups
                       AND (
                               6371 * acos(LEAST(1.0,
                                                 cos(radians(:lat))
                                                     * cos(radians(dp.latitude))
                                                     * cos(radians(dp.longitude) - radians(:lng))
                                                     + sin(radians(:lat))
                                                     * sin(radians(dp.latitude))
                                           ))
                               ) <= :radius_km
                     ORDER BY dp.reliability_score DESC
                         LIMIT :lim
                     """)

        try:
            result = self._db.execute(
                query,
                {
                    "lat":          lat,
                    "lng":          lng,
                    "radius_km":    radius_km,
                    # ✅ Tuple → SQLAlchemy IN clause binding
                    "blood_groups": tuple(blood_groups),
                    "lim":          limit,
                }
            )
            columns = result.keys()
            rows    = result.fetchall()
            donors  = [dict(zip(columns, row)) for row in rows]

            logger.debug(
                "DB query: %d donors found, radius=%skm, groups=%s",
                len(donors), radius_km, blood_groups
            )
            return donors

        except Exception as e:
            logger.error(
                "DB query failed: radius=%s, groups=%s, error=%s",
                radius_km, blood_groups, str(e),
                exc_info=True
            )
            raise