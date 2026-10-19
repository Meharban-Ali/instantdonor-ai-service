# ai-service/core/async_database.py

import logging
import threading
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Optional

from sqlalchemy.exc import OperationalError, SQLAlchemyError
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from fastapi import HTTPException
from core.config import DatabaseConfig, get_db_config

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════
# ASYNC URL CONVERTER
# ═══════════════════════════════════════════════════════════
#
# SOLID:
#   S → Sirf URL conversion ka kaam
#   O → Naya DB type = naya mapping — class change nahi
#
# Explanation:
#   Sync driver → Async driver convert karo
#   pymysql → aiomysql (MySQL async)
#   psycopg2 → asyncpg (PostgreSQL async)
#   SQLite → aiosqlite (SQLite async)
#   ✅ Bug Fix 6: Sab DB types handle karo
class AsyncUrlConverter:
    """
    Sync DB URL → Async DB URL converter.

    SOLID O: Naya DB = _DRIVER_MAP mein add karo.
    Existing code change nahi hota.

    Mappings:
        mysql+pymysql    → mysql+aiomysql
        postgresql+psycopg2 → postgresql+asyncpg
        sqlite           → sqlite+aiosqlite
    """

    # ✅ O: Map approach — naya driver = yahan add karo
    _DRIVER_MAP = {
        "mysql+pymysql://":        "mysql+aiomysql://",
        "mysql+mysqldb://":        "mysql+aiomysql://",
        "postgresql+psycopg2://":  "postgresql+asyncpg://",
        "postgresql+psycopg://":   "postgresql+asyncpg://",
        "postgresql://":           "postgresql+asyncpg://",
        "postgres://":             "postgresql+asyncpg://",
        "sqlite:///":              "sqlite+aiosqlite:///",
    }

    @classmethod
    def convert(cls, sync_url: str) -> str:
        """
        Sync URL → Async URL convert karo.

        ✅ Bug Fix 6: Sab DB types handle karo

        Args:
            sync_url: Sync DB connection URL

        Returns:
            Async DB connection URL

        Raises:
            ValueError: URL empty ya unsupported

        Examples:
            mysql+pymysql://... → mysql+aiomysql://...
            postgresql+psycopg2://... → postgresql+asyncpg://...
        """
        if not sync_url:
            raise ValueError(
                "DB_URL is empty! Set DB_URL in .env"
            )

        # ✅ Matching driver find karo
        for sync_prefix, async_prefix in cls._DRIVER_MAP.items():
            if sync_url.startswith(sync_prefix):
                converted = sync_url.replace(
                    sync_prefix, async_prefix, 1
                )
                logger.debug(
                    "URL converted: %s... → %s...",
                    sync_prefix[:15], async_prefix[:15]
                )
                return converted

        # ✅ Already async ya unknown
        logger.warning(
            "URL might already be async or unsupported: %s...",
            sync_url[:30]
        )
        return sync_url


# ═══════════════════════════════════════════════════════════
# ASYNC DATABASE ENGINE FACTORY
# ═══════════════════════════════════════════════════════════
#
# SOLID:
#   S → Sirf async engine + session factory manage karna
#   O → Sync support = database.py — yahan change nahi
#   D → DatabaseConfig inject — hardcode nahi
#
# Explanation:
#   ✅ Bug Fix 2: threading.Lock → thread-safe init
#   ✅ Bug Fix 3: Empty URL validate karo
#   ✅ Bug Fix 4: config.db_pool_pre_ping use karo
#   ✅ Bug Fix 5: pool_timeout add kiya
#   ✅ Bug Fix 8: reset() method add kiya
class AsyncDatabaseEngineFactory:
    """
    Thread-safe async SQLAlchemy engine factory.

    SOLID:
        S — Async engine + session management only
        O — Sync support = database.py (separate)
        D — DatabaseConfig injected

    Performance Benefits:
        Non-blocking DB calls
        100+ concurrent requests handle kar sakta hai
        FastAPI async endpoints ke saath perfect

    Usage:
        engine = AsyncDatabaseEngineFactory.get_async_engine()
        factory = AsyncDatabaseEngineFactory.get_async_session_factory()
    """

    _async_engine          = None
    _async_session_factory = None

    # ✅ Bug Fix 2: Thread safety ke liye RLock (Reentrant Lock)
    _lock = threading.RLock()

    @classmethod
    def get_async_engine(
            cls,
            config: Optional[DatabaseConfig] = None
    ):
        """
        Singleton async engine — thread-safe.

        ✅ Bug Fix 2: Double-checked locking
        ✅ Bug Fix 3: Empty URL validate
        ✅ Bug Fix 4: config.db_pool_pre_ping
        ✅ Bug Fix 5: pool_timeout added
        ✅ Bug Fix 9: Detailed logging

        Args:
            config: Optional — testing override ke liye

        Returns:
            AsyncEngine instance

        Raises:
            ValueError: DB_URL missing
        """
        # Fast path
        if cls._async_engine is not None:
            return cls._async_engine

        # ✅ Bug Fix 2: Lock ke andar double check
        with cls._lock:
            if cls._async_engine is None:
                db_config  = config or get_db_config()

                # ✅ Bug Fix 3: URL validate
                if not db_config.db_url:
                    raise ValueError(
                        "DB_URL is not configured!\n"
                        "Set DB_URL in .env file."
                    )

                # ✅ Bug Fix 6: AsyncUrlConverter use karo
                async_url = AsyncUrlConverter.convert(
                    db_config.db_url
                )

                connect_args = {}
                if "asyncpg" in async_url:
                    from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
                    parsed = urlparse(async_url)
                    qs = parse_qs(parsed.query)
                    sslmode = qs.pop("sslmode", None)
                    if sslmode:
                        new_query = urlencode(qs, doseq=True)
                        async_url = urlunparse(parsed._replace(query=new_query))
                        if sslmode[0] in ("require", "verify-ca", "verify-full"):
                            connect_args["ssl"] = "require"
                    if "ssl=require" in async_url.lower() or "neon.tech" in async_url.lower():
                        connect_args["ssl"] = "require"

                cls._async_engine = create_async_engine(
                    async_url,
                    connect_args = connect_args,
                    pool_size    = db_config.db_pool_size,
                    max_overflow = db_config.db_max_overflow,
                    pool_timeout = db_config.db_pool_timeout,  # ✅ Bug Fix 5
                    pool_recycle = db_config.db_pool_recycle,
                    # ✅ Bug Fix 4: Config se — hardcoded nahi
                    pool_pre_ping = db_config.db_pool_pre_ping,
                    echo          = db_config.db_echo,
                )

                # ✅ Bug Fix 9: Detailed logging
                logger.info(
                    "Async DB engine created: "
                    "pool_size=%d, max_overflow=%d, "
                    "pre_ping=%s, echo=%s",
                    db_config.db_pool_size,
                    db_config.db_max_overflow,
                    db_config.db_pool_pre_ping,
                    db_config.db_echo,
                )

        return cls._async_engine

    @classmethod
    def get_async_session_factory(
            cls,
            config: Optional[DatabaseConfig] = None
    ) -> async_sessionmaker:
        """
        Singleton async session factory.

        Explanation:
        expire_on_commit=False → committed objects accessible
        autoflush=False → explicit control
        """
        if cls._async_session_factory is not None:
            return cls._async_session_factory

        with cls._lock:
            if cls._async_session_factory is None:
                engine = cls.get_async_engine(config)
                cls._async_session_factory = async_sessionmaker(
                    bind             = engine,
                    class_           = AsyncSession,
                    autocommit       = False,
                    autoflush        = False,
                    expire_on_commit = False,
                )
                logger.debug("Async session factory created")

        return cls._async_session_factory

    @classmethod
    async def reset(cls) -> None:
        """
        ✅ Bug Fix 8: Async engine reset — testing ke liye.

        Explanation:
        Test isolation — har test fresh engine se
        async dispose → properly cleanup karo
        """
        with cls._lock:
            if cls._async_engine is not None:
                await cls._async_engine.dispose()
                logger.debug("Async DB engine disposed")
            cls._async_engine          = None
            cls._async_session_factory = None


# ═══════════════════════════════════════════════════════════
# FASTAPI ASYNC DB DEPENDENCY
# ═══════════════════════════════════════════════════════════
#
# SOLID:
#   S → Sirf async session lifecycle manage karna
#
# ✅ Bug Fix 1: Trailing comma removed
# ✅ Bug Fix 7: SQLAlchemyError alag handle
#
# Explanation:
#   async with → session auto-managed
#   commit → success pe
#   rollback → error pe
#   SQLAlchemyError → DB specific
#   Exception → Any other error
async def get_async_db() -> AsyncIterator[AsyncSession]:
    """
    FastAPI async DB dependency.

    SOLID S: Sirf async session lifecycle.

    ✅ Bug Fix 1: Trailing comma removed
    ✅ Bug Fix 7: SQLAlchemyError alag

    Usage:
        @router.get("/donors")
        async def get_donors(
            db: AsyncSession = Depends(get_async_db)
        ):
            result = await db.execute(query)
            return result.fetchall()

    Lifecycle:
        Request → async session banao
        yield → handler ko do
        Success → commit
        DB Error → rollback (SQLAlchemyError)
        Any Error → rollback
        End → session dispose
    """
    session_factory = AsyncDatabaseEngineFactory.get_async_session_factory()
    session: AsyncSession = session_factory()

    try:
        yield session

        # ✅ Success pe commit
        await session.commit()

    except HTTPException:
        # Client control flow exception (e.g. 401 Unauthorized, 400 Bad Request)
        await session.rollback()
        raise

    except SQLAlchemyError as e:
        # ✅ Bug Fix 7: DB-specific error
        await session.rollback()
        logger.error(
            "Async DB SQLAlchemy error — rolled back: %s",
            str(e),
            exc_info=True
        )
        raise

    except Exception as e:
        # ✅ Non-DB errors bhi rollback
        await session.rollback()
        logger.error(
            "Async DB unexpected error — rolled back: %s",
            str(e),
            exc_info=True
        )
        raise  # ✅ Bug Fix 1: Trailing comma removed

    finally:
        # ✅ Always close
        await session.close()


# ═══════════════════════════════════════════════════════════
# ASYNC HEALTH CHECKER
# ═══════════════════════════════════════════════════════════
#
# SOLID:
#   S → Sirf async DB health check
#
# ✅ Bug Fix 10: AsyncDatabaseHealthChecker add kiya
#
# Explanation:
#   Async SELECT 1 → non-blocking health check
#   health_service.py mein use hoga
@dataclass(frozen=True)
class AsyncDBHealthInfo:
    """Async DB health check result — typed."""
    status:     str
    is_healthy: bool
    latency_ms: float

    def to_dict(self) -> dict:
        return {
            "status":     self.status,
            "is_healthy": self.is_healthy,
            "latency_ms": self.latency_ms,
        }


class AsyncDatabaseHealthChecker:
    """
    Async DB health checker.

    ✅ Bug Fix 10: Health check add kiya

    SOLID S: Sirf async health check.

    Usage:
        healthy = await AsyncDatabaseHealthChecker.check()
        info = await AsyncDatabaseHealthChecker.get_health_info()
    """

    @classmethod
    async def check_connection(cls) -> bool:
        """
        Async DB connection check.

        Returns:
            True if connected, False otherwise
        """
        try:
            from sqlalchemy import text

            engine = AsyncDatabaseEngineFactory.get_async_engine()
            start  = time.perf_counter()

            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))

            latency_ms = (time.perf_counter() - start) * 1000
            logger.debug(
                "Async DB health check OK: %.2fms", latency_ms
            )
            return True

        except OperationalError as e:
            logger.warning(
                "Async DB health check failed: %s", str(e)
            )
            return False

        except Exception as e:
            logger.error(
                "Async DB unexpected health error: %s",
                str(e), exc_info=True
            )
            return False

    @classmethod
    async def get_health_info(cls) -> AsyncDBHealthInfo:
        """
        Complete async DB health info.

        Returns:
            AsyncDBHealthInfo — typed result
        """
        start      = time.perf_counter()
        is_healthy = await cls.check_connection()
        latency_ms = round(
            (time.perf_counter() - start) * 1000, 2
        )

        return AsyncDBHealthInfo(
            status     = "healthy" if is_healthy else "unhealthy",
            is_healthy = is_healthy,
            latency_ms = latency_ms,
        )