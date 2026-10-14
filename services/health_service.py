# ai-service/services/health_service.py

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Protocol, runtime_checkable

from core.config import get_settings, get_redis_config
from core.database import DatabaseHealthChecker

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════
# COMPONENT HEALTH CHECKER PROTOCOL
# ═══════════════════════════════════════════════════════════
#
# SOLID:
#   S → Sirf ek component check karna
#   O → Naya component = new class — HealthService change nahi
#   D → HealthService is Protocol pe depend kare
#
# Logic:
#   Har component apna health khud check karta hai
#   HealthService aggregate karta hai

@runtime_checkable
class ComponentHealthChecker(Protocol):
    """
    Single component health checker protocol.

    SOLID O: Naya component = new class.
    SOLID D: HealthService depend karta hai.
    """

    @property
    def component_name(self) -> str:
        """Component ka naam."""
        ...

    def is_healthy(self) -> bool:
        """Component healthy hai?"""
        ...


# ═══════════════════════════════════════════════════════════
# DATABASE HEALTH COMPONENT
# ═══════════════════════════════════════════════════════════

class DatabaseHealthComponent:
    """
    MySQL DB health checker.

    SOLID S: Sirf DB check karna.
    """

    @property
    def component_name(self) -> str:
        return "database"

    def is_healthy(self) -> bool:
        """
        DB alive hai?

        Logic:
            DatabaseHealthChecker.check_connection()
            Retry logic already included
            False → DB down
        """
        try:
            return DatabaseHealthChecker.check_connection()
        except Exception as e:
            logger.warning("DB health check error: %s", str(e))
            return False


# ═══════════════════════════════════════════════════════════
# REDIS HEALTH COMPONENT
# ═══════════════════════════════════════════════════════════

class RedisHealthComponent:
    """
    Redis cache health checker.

    SOLID S: Sirf Redis check karna.
    """

    @property
    def component_name(self) -> str:
        return "redis"

    def is_healthy(self) -> bool:
        """
        Redis alive hai?

        Logic:
            Redis PING → PONG
            Timeout = 3 seconds
            False → Redis down (non-critical)
        """
        try:
            import redis as redis_client
            config = get_redis_config()
            client = redis_client.Redis(
                host                   = config.redis_host,
                port                   = config.redis_port,
                password               = config.redis_password or None,
                socket_connect_timeout = 3.0,
                socket_timeout         = 3.0,
            )
            client.ping()
            return True
        except Exception as e:
            logger.warning("Redis health check failed: %s", str(e))
            return False


# ═══════════════════════════════════════════════════════════
# ML MODEL HEALTH COMPONENT
# ═══════════════════════════════════════════════════════════

class MLModelHealthComponent:
    """
    ML model in-memory readiness health checker.

    SOLID S: Check whether the ML model is successfully loaded in memory.
    """

    @property
    def component_name(self) -> str:
        return "ml_model"

    def is_healthy(self) -> bool:
        """
        Check if the ML model is loaded and ready in memory.
        """
        try:
            from core.model_loader import MLModelManager
            manager = MLModelManager.get_instance()
            if not manager.is_loaded:
                # Attempt on-demand load if not yet initialized
                manager.load_model()
            return manager.is_loaded
        except Exception as e:
            logger.warning("ML model health check failed: %s", str(e))
            return False


# ═══════════════════════════════════════════════════════════
# COMPONENT STATUS
# ═══════════════════════════════════════════════════════════

@dataclass(frozen=True)
class ComponentStatus:
    """Single component health status."""
    name:       str
    healthy:    bool
    latency_ms: float = 0.0


# ═══════════════════════════════════════════════════════════
# HEALTH CHECK RESULT
# ═══════════════════════════════════════════════════════════

@dataclass
class HealthCheckResult:
    """
    Complete health check result.

    SOLID S: Sirf result data container.

    Properties:
        is_healthy → overall healthy?
        db_connected → DB status
        redis_connected → Redis status
        model_loaded → ML model status
    """
    overall_status: str
    components:     list[ComponentStatus] = field(default_factory=list)
    timestamp:      datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    @property
    def is_healthy(self) -> bool:
        return self.overall_status == "healthy"

    def _get_status(self, name: str) -> bool:
        return any(
            c.healthy for c in self.components
            if c.name == name
        )

    @property
    def db_connected(self) -> bool:
        return self._get_status("database")

    @property
    def redis_connected(self) -> bool:
        return self._get_status("redis")

    @property
    def model_loaded(self) -> bool:
        return self._get_status("ml_model")


# ═══════════════════════════════════════════════════════════
# HEALTH SERVICE
# ═══════════════════════════════════════════════════════════
#
# SOLID:
#   S → Sirf health aggregation ka kaam
#   O → Naya component = list mein add karo
#   D → ComponentHealthChecker Protocol inject
#
# Logic:
#   Critical components fail → "unhealthy"
#   Non-critical fail → "degraded"
#   Sab OK → "healthy"
#
# System Design:
#   Kubernetes liveness/readiness probes ke liye
#   200 → traffic route karo
#   503 → traffic route mat karo

class HealthService:
    """
    Aggregate health checker.

    SOLID S: Health aggregation only.
    SOLID O: Naya checker = checkers list extend karo.
    SOLID D: ComponentHealthChecker Protocol inject.

    Status Logic:
        healthy   → sab components OK
        degraded  → non-critical fail (Redis)
        unhealthy → critical fail (DB)
    """

    # Critical components — fail → "unhealthy"
    CRITICAL_COMPONENTS = {"database", "ml_model"}

    def __init__(
            self,
            checkers: list[ComponentHealthChecker] | None = None
    ):
        # ✅ D: Checkers inject — default set provide
        self._checkers = checkers or [
            DatabaseHealthComponent(),
            RedisHealthComponent(),
            MLModelHealthComponent(),
        ]

    def check_health(self) -> HealthCheckResult:
        """
        Sab components check karo.

        Logic:
            Har component independently check karo
            Latency measure karo
            overall_status determine karo

        Returns:
            HealthCheckResult with all component statuses
        """
        component_statuses: list[ComponentStatus] = []

        for checker in self._checkers:
            start = time.perf_counter()
            try:
                healthy = checker.is_healthy()
            except Exception as e:
                logger.error(
                    "Health checker %s crashed: %s",
                    checker.component_name, str(e),
                    exc_info=True
                )
                healthy = False
            finally:
                latency_ms = round(
                    (time.perf_counter() - start) * 1000, 2
                )

            status = ComponentStatus(
                name       = checker.component_name,
                healthy    = healthy,
                latency_ms = latency_ms,
            )
            component_statuses.append(status)

            logger.debug(
                "Component %s: healthy=%s, latency=%.2fms",
                checker.component_name, healthy, latency_ms
            )

        overall = self._determine_overall(component_statuses)

        return HealthCheckResult(
            overall_status = overall,
            components     = component_statuses,
            timestamp      = datetime.now(timezone.utc),
        )

    def _determine_overall(
            self,
            statuses: list[ComponentStatus]
    ) -> str:
        """
        Overall status determine karo.

        Logic:
            Critical component fail → "unhealthy"
            Non-critical fail → "degraded"
            Sab OK → "healthy"
        """
        for s in statuses:
            if not s.healthy and s.name in self.CRITICAL_COMPONENTS:
                return "unhealthy"

        all_ok = all(s.healthy for s in statuses)
        return "healthy" if all_ok else "degraded"


# ─── Dependency Factory ─────────────────────────────────────
def get_health_service() -> HealthService:
    """FastAPI Depends ke liye factory."""
    return HealthService()