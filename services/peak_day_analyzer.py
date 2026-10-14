# ai-service/services/peak_day_analyzer.py

from dataclasses import dataclass, field


# ═══════════════════════════════════════════════════════════
# PEAK DAY RESULT
# ═══════════════════════════════════════════════════════════

@dataclass(frozen=True)
class PeakDayResult:
    """Peak day analysis ka typed result."""
    peak_days:  list[str]
    day_counts: dict[str, int]


# ═══════════════════════════════════════════════════════════
# PEAK DAY ANALYZER
# ═══════════════════════════════════════════════════════════
#
# SOLID:
#   S → Sirf peak day analysis ka kaam
#
# ✅ Bug Fix 8: Default peak days — empty list fix
#
# Logic:
#   Weekday distribution count karo
#   Most frequent days → peak days
#   No data → default ["Monday", "Friday"]
#
# Why Monday + Friday default?
#   Hospital visits Monday highest (week start)
#   Friday second (before weekend)
#   Medical literature supports this

class PeakDayAnalyzer:
    """
    Peak demand day analyzer.

    SOLID S: Sirf weekday distribution analysis.

    ✅ Bug Fix 8: Default peak days if no data.

    Logic:
        Weekday counts karo
        Top N days sort karo
        No data → medical-default days
    """

    # ✅ Bug Fix 8: Medical default
    DEFAULT_PEAK_DAYS = ["Monday", "Friday"]
    TOP_N_DAYS        = 2

    def analyze(self, past_data: list[dict]) -> PeakDayResult:
        """
        Peak days analyze karo.

        ✅ Bug Fix 8: Empty → default peak days

        Logic:
            day_counts = {weekday: count}
            Sort by count descending
            Top 2 → peak days

        Args:
            past_data: DB se historical records

        Returns:
            PeakDayResult with peak_days + distribution
        """
        day_counts: dict[str, int] = {}

        for row in past_data:
            weekday = row.get("weekday")
            if weekday:
                day_counts[weekday] = day_counts.get(weekday, 0) + 1

        # ✅ Bug Fix 8: No data → default
        if not day_counts:
            return PeakDayResult(
                peak_days  = self.DEFAULT_PEAK_DAYS,
                day_counts = {}
            )

        peak_days = sorted(
            day_counts,
            key=day_counts.get,
            reverse=True
        )[:self.TOP_N_DAYS]

        # ✅ Less than 2 → fill with defaults
        while len(peak_days) < self.TOP_N_DAYS:
            for default in self.DEFAULT_PEAK_DAYS:
                if default not in peak_days:
                    peak_days.append(default)
                    break

        return PeakDayResult(
            peak_days  = peak_days,
            day_counts = day_counts
        )