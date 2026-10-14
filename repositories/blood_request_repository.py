# ai-service/repositories/blood_request_repository.py

import logging
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════
# BLOOD REQUEST REPOSITORY
# ═══════════════════════════════════════════════════════════
#
# SOLID:
#   S → Sirf DB query ka kaam
#   D → Session inject — tight coupling nahi
#
# ✅ Bug Fix 1: Trailing comma removed
# ✅ Bug Fix 2: SQL injection fix
#
# Logic:
#   Historical blood requests fetch karo
#   City + blood_group filter
#   days_ago + weekday → trend analysis ke liye
#
# System Design:
#   PredictionService → BloodRequestRepository → MySQL
#   Read-only — Spring Boot DB
#   :bg IS NULL → blood_group filter optional

class BloodRequestRepository:
    """
    Blood request historical data — read-only.

    SOLID S: Sirf DB query ka kaam.
    SOLID D: Session injected.

    ✅ Bug Fix 2: SQL injection prevented.
    Parameterized queries only — no f-string.

    Usage:
        repo = BloodRequestRepository(db)
        history = repo.get_request_history(
            city="Delhi",
            blood_group="A+",
            days=90
        )
    """

    def __init__(self, db: Session):
        self._db = db

    def get_request_history(
            self,
            city:         str,
            blood_group:  Optional[str],
            days:         int
    ) -> list[dict]:
        """
        Historical blood request data fetch karo.

        ✅ Bug Fix 1: Trailing comma removed
        ✅ Bug Fix 2: :bg IS NULL → conditional filter safe

        Logic:
            city + days → base filter (always)
            blood_group → conditional filter
            :bg IS NULL → group filter skip karo
            days_ago + weekday → trend analysis input

        SQL Explanation:
            DATEDIFF(NOW(), created_at) → days_ago calculate
            DAYNAME(created_at) → weekday name
            :bg IS NULL OR blood_group = :bg → safe conditional

        Args:
            city:        City name (case-insensitive)
            blood_group: Optional blood group filter
            days:        Lookback period in days

        Returns:
            List of dicts with days_ago, weekday, blood_group

        Raises:
            SQLAlchemyError: DB query fail
        """
        # ✅ Bug Fix 2: NO f-string — fully parameterized!
        # :bg IS NULL → blood_group = None dene pe filter skip
        query = text("""
                     SELECT
                         DATEDIFF(NOW(), created_at)  AS days_ago,
                         DAYNAME(created_at)          AS weekday,
                         blood_group,
                         urgency
                     FROM blood_requests
                     WHERE LOWER(city) = LOWER(:city)
                       AND created_at  >= DATE_SUB(NOW(), INTERVAL :days DAY)
                       AND (:bg IS NULL OR blood_group = :bg)
                     ORDER BY created_at DESC
                     """)

        try:
            result = self._db.execute(
                query,
                {
                    "city": city.strip(),
                    "days": days,
                    # ✅ None → SQL NULL → filter skip
                    "bg":   blood_group,
                }
            )
            columns = result.keys()
            rows    = result.fetchall()
            data    = [dict(zip(columns, row)) for row in rows]

            logger.debug(
                "History fetched: city=%s, blood_group=%s, "
                "days=%d, records=%d",
                city, blood_group, days, len(data)
            )

            # ✅ Bug Fix 1: No trailing comma — list return
            return data

        except Exception as e:
            logger.error(
                "History query failed: city=%s, error=%s",
                city, str(e),
                exc_info=True
            )
            raise