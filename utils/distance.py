# ai-service/utils/distance.py

import math
from dataclasses import dataclass
from enum import Enum
from typing import Protocol, runtime_checkable

# ═══════════════════════════════════════════════════════════
# CONSTANTS
# ═══════════════════════════════════════════════════════════
#
# SOLID D: Named constants — magic numbers nahi
#
# Logic:
#   Earth mean radius = 6371.0 km (WHO/IAU standard)
#   Miles aur Meters bhi define karo — reuse ke liye
#   Ek jagah define → baaki import karo
#
# System Design:
#   DistanceUnit.get_earth_radius() ye use karega
#   Haversine formula mein R = radius

# ✅ Bug Fix 3: Named constants
EARTH_RADIUS_KM      = 6371.0        # Mean radius (km)
EARTH_RADIUS_MILES   = 3958.8        # Mean radius (miles)
EARTH_RADIUS_METERS  = 6_371_000.0   # Mean radius (meters)

# Coordinate validation ranges
LAT_MIN, LAT_MAX  = -90.0,  90.0   # Latitude: South to North
LON_MIN, LON_MAX  = -180.0, 180.0  # Longitude: West to East


# ═══════════════════════════════════════════════════════════
# DISTANCE UNIT ENUM
# ═══════════════════════════════════════════════════════════
#
# SOLID:
#   S → Sirf unit define karna
#   O → Naya unit = yahan add karo — calculator change nahi
#
# Logic:
#   str mixin → JSON serialize automatically
#   get_earth_radius() → Haversine mein directly use
#   Naya unit = enum extend, calculator unchanged (O principle)
#
# System Design:
#   HaversineCalculator.calculate(unit=DistanceUnit.KILOMETERS)
#   Frontend config se unit decide hogi

class DistanceUnit(str, Enum):
    """
    Distance measurement units.

    SOLID O:
        Naya unit = enum mein add karo.
        HaversineCalculator change nahi hoti.

    Usage:
        unit = DistanceUnit.KILOMETERS
        radius = unit.get_earth_radius()  # 6371.0
    """
    KILOMETERS = "km"
    MILES      = "miles"
    METERS     = "meters"

    def get_earth_radius(self) -> float:
        """
        Is unit ke liye Earth radius return karo.

        Logic:
            Haversine formula: distance = R × c
            R unit ke hisaab se different hota hai
            KILOMETERS → 6371.0 km
            MILES      → 3958.8 miles
            METERS     → 6,371,000 meters
        """
        radius_map = {
            DistanceUnit.KILOMETERS: EARTH_RADIUS_KM,
            DistanceUnit.MILES:      EARTH_RADIUS_MILES,
            DistanceUnit.METERS:     EARTH_RADIUS_METERS,
        }
        return radius_map[self]


# ═══════════════════════════════════════════════════════════
# COORDINATE DATACLASS
# ═══════════════════════════════════════════════════════════
#
# SOLID:
#   S → Sirf GPS coordinate represent + validate karna
#   D → Validation yahan — callers mein nahi
#
# ✅ Bug Fix 1: Input validation constructor mein
#
# Logic:
#   lat/lon hamesha pair mein hote hain
#   Alag variables → accidentally swap hone ka risk
#   frozen=True → immutable → thread-safe
#   __post_init__ → invalid state IMPOSSIBLE
#
# System Design:
#   Hospital = Coordinate(28.6139, 77.2090)
#   Donor    = Coordinate(19.0760, 72.8777)
#   dist = hospital.distance_to(donor)

@dataclass(frozen=True)
class Coordinate:
    """
    GPS coordinate — validated lat/lon pair.

    SOLID S: Sirf coordinate data + validation.
    SOLID D: Callers ko validate nahi karna.

    Immutable (frozen=True):
        Thread-safe
        Hashable → dict/set mein use possible
        Accidental change nahi

    Usage:
        hospital = Coordinate(28.6139, 77.2090)
        donor    = Coordinate(19.0760, 72.8777)
        dist     = hospital.distance_to(donor)
        # → 1153.46 km
    """
    latitude:  float
    longitude: float

    def __post_init__(self):
        """
        ✅ Bug Fix 1: Validation — invalid state impossible.

        Logic:
            Latitude:  -90 (South Pole) to +90 (North Pole)
            Longitude: -180 (West) to +180 (East)
            Invalid → ValueError at creation time

        System Design:
            Fail fast principle — runtime mein nahi, creation pe
        """
        if not (LAT_MIN <= self.latitude <= LAT_MAX):
            raise ValueError(
                f"Invalid latitude: {self.latitude}.\n"
                f"Must be {LAT_MIN} to {LAT_MAX} degrees.\n"
                f"(South Pole={LAT_MIN}, North Pole={LAT_MAX})"
            )
        if not (LON_MIN <= self.longitude <= LON_MAX):
            raise ValueError(
                f"Invalid longitude: {self.longitude}.\n"
                f"Must be {LON_MIN} to {LON_MAX} degrees.\n"
                f"(West={LON_MIN}, East={LON_MAX})"
            )

    def distance_to(
            self,
            other: 'Coordinate',
            unit: DistanceUnit = DistanceUnit.KILOMETERS
    ) -> float:
        """
        Is coordinate se doosre ka distance.

        Logic:
            Convenience method — calculator inject nahi
            Default calculator HaversineCalculator use karta hai
            hospital.distance_to(donor) → clean API

        Args:
            other: Target coordinate
            unit:  Return unit (default km)

        Returns:
            Distance in specified unit
        """
        calc = HaversineCalculator()
        return calc.calculate(self, other, unit)

    def is_within_radius(
            self,
            other: 'Coordinate',
            radius_km: float
    ) -> bool:
        """
        Kya doosra coordinate radius ke andar hai?

        Logic:
            Quick filter — expensive AI scoring se pehle
            True → scoring karo
            False → skip karo
        """
        return self.distance_to(other) <= radius_km


# ═══════════════════════════════════════════════════════════
# DISTANCE CALCULATOR PROTOCOL
# ═══════════════════════════════════════════════════════════
#
# SOLID:
#   D → High-level code is Protocol pe depend karo
#   O → Naya formula = new class — Protocol implement karo
#   L → Sab implementations interchangeable
#
# Logic:
#   Protocol → Duck typing — explicit inheritance nahi
#   runtime_checkable → isinstance() check possible
#   Testing mein mock karna easy
#   Future: VincentyCalculator (ellipsoidal earth) bhi possible

@runtime_checkable
class DistanceCalculator(Protocol):
    """
    Distance calculator protocol — abstraction.

    SOLID D: High-level modules is pe depend karein.
    SOLID O: Naya formula = new class implements this.
    SOLID L: HaversineCalculator substitutable hai.

    Implementations:
        HaversineCalculator → spherical earth (current)
        Future: VincentyCalculator → ellipsoidal (0.5% more accurate)
    """

    def calculate(
            self,
            point1: Coordinate,
            point2: Coordinate,
            unit: DistanceUnit = DistanceUnit.KILOMETERS
    ) -> float:
        """Distance calculate karo — specified unit mein."""
        ...

    def calculate_bearing(
            self,
            point1: Coordinate,
            point2: Coordinate
    ) -> float:
        """Bearing (direction) 0-360 degrees calculate karo."""
        ...


# ═══════════════════════════════════════════════════════════
# HAVERSINE CALCULATOR
# ═══════════════════════════════════════════════════════════
#
# SOLID:
#   S → Sirf Haversine distance calculation
#   L → DistanceCalculator Protocol implement karta hai
#
# ✅ Bug Fix 2: Floating point precision fix
# ✅ Bug Fix 3: Named constant EARTH_RADIUS_KM
# ✅ Bug Fix 4: Unit support
# ✅ Bug Fix 6: Bearing calculation
#
# Logic:
#   Haversine → spherical earth model
#   0.3% error → blood donation ke liye sufficient
#   Formula steps:
#     1. Degrees → Radians convert
#     2. Haversine formula apply
#     3. ✅ Clamp (floating point safety)
#     4. Distance = R × c
#
# System Design:
#   matching_service.py → donor distance calculate karo
#   SQL mein bhi same formula (LEAST(1.0,...))

class HaversineCalculator:
    """
    Haversine formula — spherical earth distance.

    SOLID S: Sirf distance calculation.
    SOLID L: DistanceCalculator Protocol se substitutable.

    Haversine Formula:
        a = sin²(Δlat/2) + cos(lat1)·cos(lat2)·sin²(Δlon/2)
        c = 2·atan2(√a, √(1−a))
        d = R·c

    Accuracy: ~0.3% error (spherical model)
    Use case: Blood donor search → sufficient accuracy

    Why not Vincenty?
        0.5% more accurate but 10x slower
        For 25km radius → 0.3% = 75 meters → negligible
    """

    def calculate(
            self,
            point1: Coordinate,
            point2: Coordinate,
            unit: DistanceUnit = DistanceUnit.KILOMETERS
    ) -> float:
        """
        Do GPS points ke beech distance.

        ✅ Bug Fix 2: Floating point precision (clamp)
        ✅ Bug Fix 4: Unit support

        Logic Steps:
            1. Same point → 0.0 early return
            2. Degrees → Radians (math functions radians chahte)
            3. Haversine formula
            4. min(1.0, max(0.0, a)) → NaN prevent
            5. Unit ke hisaab se radius × angle

        Args:
            point1: Hospital/request location
            point2: Donor location
            unit:   Return unit (default km)

        Returns:
            Distance rounded to 2 decimal places

        Raises:
            ValueError: Invalid coords (Coordinate constructor)
        """
        # ─── Step 1: Same point early return ───────────────
        # Logic:
        #   Exact same coordinates → 0.0
        #   Floating point compare → exact match sirf
        if (point1.latitude  == point2.latitude and
                point1.longitude == point2.longitude):
            return 0.0

        # ─── Step 2: Degrees → Radians ─────────────────────
        # Logic:
        #   math.sin/cos radians expect karte hain
        #   math.radians(degrees) = degrees × π/180
        lat1_r = math.radians(point1.latitude)
        lat2_r = math.radians(point2.latitude)
        dlat   = math.radians(point2.latitude  - point1.latitude)
        dlng   = math.radians(point2.longitude - point1.longitude)

        # ─── Step 3: Haversine Formula ──────────────────────
        # Logic:
        #   sin²(Δlat/2) → vertical component
        #   cos(lat1)×cos(lat2)×sin²(Δlon/2) → horizontal
        #   Sum → combined spherical distance component
        a = (
                math.sin(dlat / 2) ** 2
                + math.cos(lat1_r) * math.cos(lat2_r)
                * math.sin(dlng / 2) ** 2
        )

        # ─── Step 4: Floating Point Safety ──────────────────
        # ✅ Bug Fix 2: CRITICAL FIX
        # Logic:
        #   Floating point → a slightly > 1.0 possible
        #   math.sqrt(1 - 1.0000001) → math.sqrt(negative) → NaN!
        #   min(1.0, max(0.0, a)) → safe range enforce
        #   Same fix as SQL: LEAST(1.0, ...)
        a = min(1.0, max(0.0, a))
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

        # ─── Step 5: Distance Calculate ─────────────────────
        # ✅ Bug Fix 4: Unit se radius milta hai
        radius   = unit.get_earth_radius()
        distance = radius * c

        return round(distance, 2)

    def calculate_bearing(
            self,
            point1: Coordinate,
            point2: Coordinate
    ) -> float:
        """
        ✅ Bug Fix 6: Bearing/Direction calculate karo.

        Logic:
            point1 se point2 ki compass direction
            0°=North, 90°=East, 180°=South, 270°=West
            (bearing + 360) % 360 → always positive 0-360

        System Design:
            Frontend map pe direction arrow
            "Donor is 15km North-East of hospital"

        Args:
            point1: Starting location (hospital)
            point2: Target location (donor)

        Returns:
            Bearing in degrees (0.0 to 360.0)
        """
        lat1_r = math.radians(point1.latitude)
        lat2_r = math.radians(point2.latitude)
        dlng   = math.radians(
            point2.longitude - point1.longitude
        )

        # Forward azimuth formula
        x = math.sin(dlng) * math.cos(lat2_r)
        y = (
                math.cos(lat1_r) * math.sin(lat2_r)
                - math.sin(lat1_r) * math.cos(lat2_r)
                * math.cos(dlng)
        )

        bearing = math.degrees(math.atan2(x, y))

        # Normalize 0°-360°
        return (bearing + 360.0) % 360.0

    def get_compass_direction(
            self,
            bearing: float
    ) -> str:
        """
        Bearing → compass direction string.

        Logic:
            0-22.5°   → N
            22.5-67.5° → NE
            ...etc
            Human-readable direction

        Returns:
            "N", "NE", "E", "SE", "S", "SW", "W", "NW"
        """
        directions = ["N","NE","E","SE","S","SW","W","NW"]
        index = round(bearing / 45) % 8
        return directions[index]


# ═══════════════════════════════════════════════════════════
# BATCH DISTANCE CALCULATOR
# ═══════════════════════════════════════════════════════════
#
# SOLID:
#   S → Sirf batch calculation ka kaam
#   D → DistanceCalculator inject karo
#
# ✅ Bug Fix 5: Batch + numpy vectorized
#
# Logic:
#   100 donors ke liye 100 individual calls → O(n) loops → slow
#   Numpy vectorized → SIMD CPU instructions → 10-100x faster
#   1000 donors: Loop ~200ms vs Numpy ~2ms
#
# System Design:
#   matching_service.py → batch_haversine() call karo
#   DB Haversine query ke baad Python-side re-verify
#   Filter karo → score karo → rank karo

class BatchDistanceCalculator:
    """
    Vectorized batch distance calculation.

    SOLID S: Sirf batch calculation.
    SOLID D: DistanceCalculator injected.

    Performance:
        Python loop: O(n) × overhead → slow
        Numpy vectorized: SIMD instructions → 10-100x faster
        100 donors → loop: ~5ms, numpy: ~0.1ms

    Usage:
        batch = BatchDistanceCalculator()
        distances = batch.calculate_batch(
            center, donor_coordinates
        )
    """

    def __init__(
            self,
            calculator: DistanceCalculator | None = None
    ):
        # ✅ D: Calculator inject — default HaversineCalculator
        self._calc = calculator or HaversineCalculator()

    def calculate_batch(
            self,
            center: Coordinate,
            points: list[Coordinate],
            unit:   DistanceUnit = DistanceUnit.KILOMETERS
    ) -> list[float]:
        """
        Center se multiple points ka distance.

        Logic:
            numpy available → vectorized (fast path)
            numpy missing → Python loop (fallback)
            Empty list → empty list (safe)

        Args:
            center: Hospital/request location
            points: List of donor coordinates
            unit:   Distance unit

        Returns:
            Distances list — same order as input
        """
        if not points:
            return []

        # numpy vectorized — fastest
        return self._numpy_batch(center, points, unit)

    def _numpy_batch(
            self,
            center: Coordinate,
            points: list[Coordinate],
            unit:   DistanceUnit
    ) -> list[float]:
        """
        Numpy vectorized Haversine — fastest.

        Logic (Vectorized):
            1. Center radians → scalar
            2. All donors radians → numpy arrays
            3. Haversine formula → vectorized operations
            4. np.clip(a, 0, 1) → ✅ Bug Fix 2 floating point
            5. R × c → distance array

        Performance:
            Numpy: C extension → SIMD CPU instructions
            sin/cos sab ek saath calculate → no Python loop overhead
        """
        try:
            import numpy as np

            # Center → scalar radians
            lat1 = math.radians(center.latitude)
            lon1 = math.radians(center.longitude)

            # All donors → numpy arrays (vectorized)
            lat2 = np.radians(np.array(
                [p.latitude  for p in points], dtype=np.float64
            ))
            lon2 = np.radians(np.array(
                [p.longitude for p in points], dtype=np.float64
            ))

            # Differences
            dlat = lat2 - lat1
            dlng = lon2 - lon1

            # Haversine — vectorized
            a = (
                    np.sin(dlat / 2) ** 2
                    + math.cos(lat1) * np.cos(lat2)
                    * np.sin(dlng / 2) ** 2
            )

            # ✅ Bug Fix 2: Clamp — floating point safety
            a = np.clip(a, 0.0, 1.0)
            c = 2 * np.arctan2(np.sqrt(a), np.sqrt(1 - a))

            # Unit-based radius
            radius    = unit.get_earth_radius()
            distances = radius * c

            return [round(float(d), 2) for d in distances]

        except ImportError:
            # ✅ Numpy nahi → Python loop fallback
            return self._python_loop(center, points, unit)

    def _python_loop(
            self,
            center: Coordinate,
            points: list[Coordinate],
            unit:   DistanceUnit
    ) -> list[float]:
        """
        Python loop fallback — numpy nahi toh.

        Logic:
            Defensive coding — requirements mein numpy hai
            But agar kisi reason se import fail hue
            Correct result de — sirf slower
        """
        return [
            self._calc.calculate(center, point, unit)
            for point in points
        ]

    def filter_within_radius(
            self,
            center:    Coordinate,
            points:    list[Coordinate],
            radius_km: float
    ) -> list[tuple[Coordinate, float]]:
        """
        Radius ke andar points filter karo + distance.

        Logic:
            AI scoring expensive hai
            Pehle distance filter karo
            Sirf nearby donors pe scoring apply
            Tuple → (coordinate, distance_km)

        System Design:
            matching_service.py mein use:
                1. filter_within_radius() → nearby donors
                2. DonorScoringService.score_donors_batch()
                3. DefaultRankingStrategy.rank()

        Returns:
            List of (coordinate, distance_km) — sorted by distance
        """
        if not points:
            return []

        distances = self.calculate_batch(
            center, points, DistanceUnit.KILOMETERS
        )

        # Filter + pair karo
        within = [
            (point, dist)
            for point, dist in zip(points, distances)
            if dist <= radius_km
        ]

        # Distance se sort karo — nearest first
        within.sort(key=lambda x: x[1])
        return within


# ═══════════════════════════════════════════════════════════
# MODULE-LEVEL SINGLETONS
# ═══════════════════════════════════════════════════════════
#
# Logic:
#   Service layer mein instantiate karne ki zaroorat nahi
#   Import karke directly use karo
#   Testing mein override possible

_calculator       = HaversineCalculator()
_batch_calculator = BatchDistanceCalculator(_calculator)


# ═══════════════════════════════════════════════════════════
# CONVENIENCE FUNCTIONS — Public API
# ═══════════════════════════════════════════════════════════
#
# SOLID:
#   S → Simple interface — implementation details hide
#
# Logic:
#   Classes seedha use karne ke bajaye
#   Simple function calls — backward compatible
#   matching_service.py yahan import karega

def haversine_distance(
        lat1: float,
        lon1: float,
        lat2: float,
        lon2: float,
        unit: DistanceUnit = DistanceUnit.KILOMETERS
) -> float:
    """
    Do GPS coordinates ka distance.

    ✅ Bug Fix 1: Validation via Coordinate constructor
    ✅ Bug Fix 2: Floating point fix via HaversineCalculator
    ✅ Bug Fix 3: Named constant via DistanceUnit
    ✅ Bug Fix 4: Unit support

    Logic:
        Coordinate banao → validation automatic
        HaversineCalculator.calculate() call karo
        Unit se radius decide hoti hai

    Args:
        lat1, lon1: Hospital/request location
        lat2, lon2: Donor location
        unit:       Return unit (default km)

    Returns:
        Distance (2 decimal places)

    Raises:
        ValueError: Invalid coordinates

    Example:
        dist = haversine_distance(
            28.6139, 77.2090,  # Delhi
            19.0760, 72.8777   # Mumbai
        )
        # → 1153.46 km
    """
    point1 = Coordinate(lat1, lon1)  # Validation here
    point2 = Coordinate(lat2, lon2)
    return _calculator.calculate(point1, point2, unit)


def batch_haversine(
        center_lat:  float,
        center_lon:  float,
        latitudes:   list[float],
        longitudes:  list[float],
        unit:        DistanceUnit = DistanceUnit.KILOMETERS
) -> list[float]:
    """
    ✅ Bug Fix 5: Batch distance — N donors ek saath.

    Logic:
        Hospital → sab donors ka distance ek call mein
        numpy vectorized → 10-100x faster than loop
        matching_service.py ye use karega

    Args:
        center_lat, center_lon: Hospital location
        latitudes:  Donor latitudes (same order)
        longitudes: Donor longitudes (same order)
        unit:       Distance unit

    Returns:
        Distances list — same order as input

    Raises:
        ValueError: Length mismatch ya invalid coords

    Example:
        dists = batch_haversine(
            28.61, 77.20,
            [19.07, 12.97],   # Mumbai, Bangalore
            [72.87, 77.59]
        )
        # → [1153.46, 1742.33]
    """
    if len(latitudes) != len(longitudes):
        raise ValueError(
            f"Length mismatch: "
            f"latitudes={len(latitudes)}, "
            f"longitudes={len(longitudes)}.\n"
            f"Must be same length!"
        )

    center = Coordinate(center_lat, center_lon)
    points = [
        Coordinate(lat, lon)
        for lat, lon in zip(latitudes, longitudes)
    ]
    return _batch_calculator.calculate_batch(center, points, unit)


def is_within_radius(
        center_lat: float,
        center_lon: float,
        point_lat:  float,
        point_lon:  float,
        radius_km:  float
) -> bool:
    """
    Point radius ke andar hai?

    Logic:
        Quick filter — AI scoring se pehle use karo
        True → donor candidate, score karo
        False → skip karo, scoring waste

    System Design:
        matching_service.py mein pre-filter ke liye

    Args:
        center: Hospital location
        point:  Donor location
        radius_km: Search radius

    Returns:
        True if within radius
    """
    center = Coordinate(center_lat, center_lon)
    point  = Coordinate(point_lat,  point_lon)
    return center.is_within_radius(point, radius_km)