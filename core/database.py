# ai-service/core/database.py

import logging
import threading
import time
from collections.abc import Iterator  # ✅ Bug Fix 4,5
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import create_engine, text  # ✅ Bug Fix 1: event removed
from sqlalchemy.exc import OperationalError, SQLAlchemyError  # ✅ Bug Fix 10
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import NullPool, QueuePool

from fastapi import HTTPException
from core.config import DatabaseConfig, get_db_config

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════
# BASE MODEL
# ═══════════════════════════════════════════════════════════
#
# SOLID:
#   S → Sirf SQLAlchemy base class define karna
#
# Explanation:
#   Sab DB models yeh inherit karenge
#   Spring Boot DB pe read-only access
#   Python models sirf matching ke liye hain
class Base(DeclarativeBase):
    """SQLAlchemy declarative base for all models."""
    pass


# ═══════════════════════════════════════════════════════════
# CONNECT ARGS FACTORY
# ═══════════════════════════════════════════════════════════
#
# SOLID:
#   S → Sirf DB-specific connection args banana
#   O → Naya DB type = naya method — factory change nahi
#   L → Sab methods same interface follow karte hain
#
# Explanation:
#   MySQL, PostgreSQL, SQLite ke alag connect_args hain
#   ✅ Bug Fix 8: MySQL-only args ko alag kiya
#   DB URL se DB type detect karo → correct args return
class ConnectArgsFactory:
    """
    DB-specific connection arguments factory.

    SOLID O: Naya DB type = naya static method.
    Existing methods change nahi hote.

    Supported:
        MySQL/MariaDB → charset, timeout, autocommit
        PostgreSQL    → timeout, app_name, timezone
        SQLite        → thread safety
        Unknown       → empty dict (safe default)
    """

    @staticmethod
    def for_mysql() -> dict:
        """
        MySQL/MariaDB connection args.

        Explanation:
        connect_timeout → connection establish timeout
        charset=utf8mb4 → full Unicode (emojis bhi)
        autocommit=False → explicit transaction control
        """
        return {
            "connect_timeout": 10,
            "charset":         "utf8mb4",
            "autocommit":      False,
        }

    @staticmethod
    def for_postgresql(db_url: str = "") -> dict:
        """
        PostgreSQL connection args.

        Explanation:
        connect_timeout → connection timeout
        application_name → pg_stat_activity mein dikhe
        options → UTC timezone force karo
        sslmode → require for Neon/cloud if requested
        """
        args = {
            "connect_timeout":  10,
            "application_name": "blood_donor_ai",
            "options":          "-c timezone=UTC",
        }
        if "sslmode=require" in db_url.lower() or "neon.tech" in db_url.lower():
            args["sslmode"] = "require"
        return args

    @staticmethod
    def for_sqlite() -> dict:
        """
        SQLite connection args.

        Explanation:
        check_same_thread=False → multi-thread safe
        SQLite default single-thread assume karta hai
        """
        return {
            "check_same_thread": False,
        }

    @classmethod
    def get(cls, db_url: str) -> dict:
        """
        DB URL se correct connect_args return karo.

        ✅ Bug Fix 8: DB type auto-detect

        Args:
            db_url: Database connection URL

        Returns:
            DB-specific connection arguments dict
        """
        url_lower = db_url.lower()

        if "mysql" in url_lower or "mariadb" in url_lower:
            return cls.for_mysql()
        elif "postgresql" in url_lower or "postgres" in url_lower:
            return cls.for_postgresql(db_url)
        elif "sqlite" in url_lower:
            return cls.for_sqlite()
        else:
            logger.warning(
                "Unknown DB type in URL — using empty connect_args. "
                "URL prefix: %s",
                db_url[:30] if db_url else "empty"
            )
            return {}


# ═══════════════════════════════════════════════════════════
# DATABASE ENGINE FACTORY
# ═══════════════════════════════════════════════════════════
#
# SOLID:
#   S → Sirf engine + session factory manage karna
#   O → Async support = AsyncDatabaseEngineFactory — yahan change nahi
#   D → DatabaseConfig inject — hardcode nahi
#
# Explanation:
#   Singleton pattern — ek engine, sab requests share karein
#   ✅ Bug Fix 2: threading.Lock → thread-safe initialization
#   ✅ Bug Fix 3: Empty URL validate karo startup pe
#   ✅ Bug Fix 9: config.db_pool_pre_ping use karo
#   Lazy init → import pe connect nahi → test friendly
class DatabaseEngineFactory:
    """
    Thread-safe SQLAlchemy engine factory.

    SOLID:
        S — Engine + Session management only
        O — Async = new class, this unchanged
        D — DatabaseConfig injected

    Thread Safety:
        Double-checked locking pattern
        threading.Lock → race condition prevent

    Usage:
        engine = DatabaseEngineFactory.get_engine()
        factory = DatabaseEngineFactory.get_session_factory()
    """

    _engine = None
    _session_factory = None

    # ✅ Bug Fix 2: Thread safety ke liye RLock (Reentrant Lock)
    _lock = threading.RLock()

    @classmethod
    def get_engine(
            cls,
            config: Optional[DatabaseConfig] = None
    ):
        """
        Singleton engine — thread-safe lazy initialization.

        ✅ Bug Fix 2: Double-checked locking
        ✅ Bug Fix 3: Empty URL validate karo

        Explanation:
        First check bina lock ke — fast path
        Lock sirf tab lo jab engine nahi hai
        Double check inside lock — race condition prevent

        Args:
            config: Optional config — testing override ke liye

        Returns:
            SQLAlchemy Engine instance

        Raises:
            ValueError: DB URL missing ya invalid
        """
        # Fast path — lock nahi chahiye
        if cls._engine is not None:
            return cls._engine

        # ✅ Bug Fix 2: Lock ke andar double check
        with cls._lock:
            if cls._engine is None:
                db_config = config or get_db_config()
                cls._engine = cls._create_engine(db_config)
                logger.info(
                    "DB engine created: pool_size=%d, "
                    "max_overflow=%d, pre_ping=%s",
                    db_config.db_pool_size,
                    db_config.db_max_overflow,
                    db_config.db_pool_pre_ping,
                )

        return cls._engine

    @classmethod
    def get_session_factory(
            cls,
            config: Optional[DatabaseConfig] = None
    ) -> sessionmaker:
        """
        Singleton session factory.

        Explanation:
        Session factory ek baar banao — reuse karo
        expire_on_commit=False → committed objects accessible
        autoflush=False → explicit control
        """
        if cls._session_factory is not None:
            return cls._session_factory

        with cls._lock:
            if cls._session_factory is None:
                engine = cls.get_engine(config)
                cls._session_factory = sessionmaker(
                    bind             = engine,
                    autocommit       = False,
                    autoflush        = False,
                    expire_on_commit = False,
                )

        return cls._session_factory

    @classmethod
    def _create_engine(cls, config: DatabaseConfig):
        """
        SQLAlchemy engine create karo.

        ✅ Bug Fix 3: Empty URL → ValueError
        ✅ Bug Fix 8: DB-specific connect_args
        ✅ Bug Fix 9: config.db_pool_pre_ping use karo

        Explanation:
        QueuePool → connection reuse — performance
        NullPool → SQLite ke liye (no pooling)
        pool_pre_ping → stale connection detect + refresh
        connect_args → DB-specific settings
        """
        # ✅ Bug Fix 3: URL validate karo
        if not config.db_url:
            raise ValueError(
                "DB_URL is not configured!\n"
                "Set DB_URL in .env file.\n"
                "Format: mysql+pymysql://user:pass@host:port/db"
            )

        # ✅ Bug Fix 8: DB-specific connect_args
        connect_args = ConnectArgsFactory.get(config.db_url)

        # SQLite ke liye NullPool — pooling support nahi
        pool_class = (
            NullPool
            if "sqlite" in config.db_url.lower()
            else QueuePool
        )

        engine = create_engine(
            config.db_url,
            poolclass    = pool_class,
            pool_size    = config.db_pool_size,
            max_overflow = config.db_max_overflow,
            pool_timeout = config.db_pool_timeout,
            pool_recycle = config.db_pool_recycle,

            # ✅ Bug Fix 9: Config se — hardcoded True nahi
            pool_pre_ping = config.db_pool_pre_ping,

            echo         = config.db_echo,
            connect_args = connect_args,
        )

        return engine

    @classmethod
    def reset(cls) -> None:
        """
        Engine reset karo — testing ke liye.

        Explanation:
        Test isolation — har test fresh engine se start kare
        Resources properly dispose karo — connection leak nahi
        Lock ke andar reset — thread-safe
        """
        with cls._lock:
            if cls._engine is not None:
                cls._engine.dispose()
                logger.debug("DB engine disposed")
            cls._engine = None
            cls._session_factory = None


# ═══════════════════════════════════════════════════════════
# FASTAPI DB DEPENDENCY
# ═══════════════════════════════════════════════════════════
#
# SOLID:
#   S → Sirf FastAPI session lifecycle manage karna
#
# ✅ Bug Fix 4: Iterator type hint (Generator nahi)
# ✅ Bug Fix 10: SQLAlchemyError alag handle
#
# Explanation:
#   FastAPI Depends(get_db) se inject hota hai
#   Har request fresh session milti hai
#   Success → commit
#   DB error → rollback + re-raise (SQLAlchemy specific)
#   Any error → rollback + re-raise
#   Always → close (resource leak prevent)
def get_db() -> Iterator[Session]:  # ✅ Bug Fix 4
    """
    FastAPI database session dependency.

    SOLID S: Sirf session lifecycle manage karna.

    Usage:
        @router.get("/donors")
        def get_donors(db: Session = Depends(get_db)):
            result = db.execute(query).fetchall()
            return result

    Lifecycle:
        Request aaya → session banao
        Handler chala → yield session
        Success → commit
        Error → rollback + re-raise
        End → session close (always)
    """
    session_factory = DatabaseEngineFactory.get_session_factory()
    db: Session = session_factory()

    try:
        yield db

        # ✅ Success pe commit
        db.commit()

    except HTTPException:
        # Client control flow exception (e.g. 401 Unauthorized, 400 Bad Request)
        db.rollback()
        raise

    except SQLAlchemyError as e:
        # ✅ Bug Fix 10: DB-specific error
        db.rollback()
        logger.error(
            "DB session SQLAlchemy error — rolled back: %s",
            str(e),
            exc_info=True  # Full traceback log mein
        )
        raise

    except Exception as e:
        # ✅ Non-DB errors bhi rollback
        db.rollback()
        logger.error(
            "DB session unexpected error — rolled back: %s",
            str(e),
            exc_info=True
        )
        raise

    finally:
        # ✅ Always close — resource leak nahi
        db.close()


# ═══════════════════════════════════════════════════════════
# CONTEXT MANAGER — Service layer ke liye
# ═══════════════════════════════════════════════════════════
#
# SOLID:
#   S → Sirf non-FastAPI session management
#
# ✅ Bug Fix 5: Iterator type hint
# ✅ Bug Fix 10: SQLAlchemyError alag handle
#
# Explanation:
#   Service layer mein FastAPI Depends() nahi chalti
#   with statement → automatic cleanup
#   Same behavior as get_db() — commit/rollback/close
@contextmanager
def get_db_context() -> Iterator[Session]:  # ✅ Bug Fix 5
    """
    Context manager for non-FastAPI code.

    SOLID S: Service layer session management.

    Usage:
        with get_db_context() as db:
            donors = db.execute(query).fetchall()
            # Auto commit on exit
            # Auto rollback on error
    """
    session_factory = DatabaseEngineFactory.get_session_factory()
    db: Session = session_factory()

    try:
        yield db
        db.commit()

    except HTTPException:
        # Client control flow exception
        db.rollback()
        raise

    except SQLAlchemyError as e:
        # ✅ Bug Fix 10: DB-specific
        db.rollback()
        logger.error(
            "DB context SQLAlchemy error — rolled back: %s",
            str(e),
            exc_info=True
        )
        raise

    except Exception as e:
        db.rollback()
        logger.error(
            "DB context unexpected error — rolled back: %s",
            str(e),
            exc_info=True
        )
        raise

    finally:
        db.close()


# ═══════════════════════════════════════════════════════════
# HEALTH CHECK RESULT — Typed dataclass
# ═══════════════════════════════════════════════════════════
#
# SOLID:
#   S → Sirf health result data represent karna
#
# Explanation:
#   dict return se zyada type-safe
#   frozen=True → immutable — thread-safe
#   Properties → derived values calculate karo
@dataclass(frozen=True)
class DBHealthInfo:
    """
    DB health check ka typed result.

    SOLID S: Sirf data container — logic nahi.

    Attributes:
        status:      healthy | unhealthy
        is_healthy:  bool shortcut
        pool_size:   Total pool connections
        checked_out: Active connections
        overflow:    Overflow connections
        checked_in:  Idle connections
        latency_ms:  Health check latency
    """
    status:      str
    is_healthy:  bool
    pool_size:   int
    checked_out: int
    overflow:    int
    checked_in:  int
    latency_ms:  float

    def to_dict(self) -> dict:
        """Monitoring endpoints ke liye dict."""
        return {
            "status":      self.status,
            "is_healthy":  self.is_healthy,
            "pool_size":   self.pool_size,
            "checked_out": self.checked_out,
            "overflow":    self.overflow,
            "checked_in":  self.checked_in,
            "latency_ms":  self.latency_ms,
        }


# ═══════════════════════════════════════════════════════════
# DATABASE HEALTH CHECKER
# ═══════════════════════════════════════════════════════════
#
# SOLID:
#   S → Sirf DB health check karna
#
# ✅ Bug Fix 6: Double DB call fix
# ✅ Bug Fix 7: Safe pool attribute access
#
# Explanation:
#   Retry with exponential backoff
#   Network blip pe wrong result nahi
#   Pool stats — monitoring/alerting ke liye
#   Typed return — dict nahi DBHealthInfo
class DatabaseHealthChecker:
    """
    DB connection health checker with retry.

    SOLID S: Sirf health check — session management nahi.

    Retry Strategy:
        Attempt 1 → fail → wait 1s
        Attempt 2 → fail → wait 2s
        Attempt 3 → fail → return False

    Usage:
        healthy = DatabaseHealthChecker.check_connection()
        info = DatabaseHealthChecker.get_health_info()
    """

    MAX_RETRIES  = 3
    RETRY_DELAY  = 1.0  # Base seconds — exponential backoff

    @classmethod
    def check_connection(cls) -> bool:
        """
        DB connection check — retry ke saath.

        Explanation:
        OperationalError → retry (network blip)
        Other Exception → immediately False (critical error)
        Exponential backoff → zyada wait karo repeated fails pe

        Returns:
            True if connected, False otherwise
        """
        for attempt in range(1, cls.MAX_RETRIES + 1):
            try:
                engine = DatabaseEngineFactory.get_engine()
                start = time.perf_counter()

                with engine.connect() as conn:
                    conn.execute(text("SELECT 1"))

                latency_ms = (time.perf_counter() - start) * 1000

                if attempt > 1:
                    logger.info(
                        "DB connected after %d attempts (%.2fms)",
                        attempt, latency_ms
                    )
                else:
                    logger.debug(
                        "DB health check OK: %.2fms",
                        latency_ms
                    )
                return True

            except OperationalError as e:
                # Retry karo — network blip ho sakta hai
                logger.warning(
                    "DB attempt %d/%d failed: %s",
                    attempt, cls.MAX_RETRIES,
                    str(e).split('\n')[0]  # First line only
                )
                if attempt < cls.MAX_RETRIES:
                    # ✅ Exponential backoff
                    sleep_time = cls.RETRY_DELAY * attempt
                    logger.debug(
                        "Retrying in %.1fs...", sleep_time
                    )
                    time.sleep(sleep_time)

            except Exception as e:
                # Critical error — retry nahi
                logger.error(
                    "Unexpected DB health error: %s",
                    str(e),
                    exc_info=True
                )
                return False

        logger.error(
            "DB connection failed after %d attempts",
            cls.MAX_RETRIES
        )
        return False

    @classmethod
    def get_health_info(cls) -> DBHealthInfo:
        """
        Complete DB health info — typed result.

        ✅ Bug Fix 6: Single check_connection() call
        ✅ Bug Fix 7: Safe pool attribute access

        Explanation:
        is_healthy ek baar check karo — result reuse
        Pool stats safely access karo — AttributeError nahi
        Latency bhi measure karo — monitoring ke liye

        Returns:
            DBHealthInfo dataclass (frozen — thread safe)
        """
        # ✅ Bug Fix 6: Ek baar check — double call nahi
        start = time.perf_counter()
        is_healthy = cls.check_connection()
        latency_ms = round(
            (time.perf_counter() - start) * 1000, 2
        )

        # ✅ Bug Fix 7: Safe pool access
        def safe_pool_attr(pool, attr: str) -> int:
            """
            Pool attribute safely access karo.

            Explanation:
            NullPool, StaticPool mein size() nahi hota
            getattr + callable → safely handle
            """
            try:
                method = getattr(pool, attr, None)
                if callable(method):
                    return int(method())
                return 0
            except Exception:
                return 0

        try:
            engine = DatabaseEngineFactory.get_engine()
            pool   = engine.pool

            return DBHealthInfo(
                status      = "healthy" if is_healthy else "unhealthy",
                is_healthy  = is_healthy,
                pool_size   = safe_pool_attr(pool, 'size'),
                checked_out = safe_pool_attr(pool, 'checkedout'),
                overflow    = safe_pool_attr(pool, 'overflow'),
                checked_in  = safe_pool_attr(pool, 'checkedin'),
                latency_ms  = latency_ms,
            )

        except Exception as e:
            logger.error(
                "Failed to get pool info: %s", str(e)
            )
            # ✅ Pool info fail → health result phir bhi return
            return DBHealthInfo(
                status      = "unhealthy",
                is_healthy  = False,
                pool_size   = 0,
                checked_out = 0,
                overflow    = 0,
                checked_in  = 0,
                latency_ms  = latency_ms,
            )


# ═══════════════════════════════════════════════════════════
# CONVENIENCE FUNCTIONS — Backward compatibility
# ═══════════════════════════════════════════════════════════
#
# Explanation:
#   Purana code break na ho — same function names
#   Internally DatabaseHealthChecker use karo
#   Dict return — existing callers ke liye

def check_db_connection() -> bool:
    """
    Simple health check — backward compatible.

    Returns:
        True if DB connected, False otherwise
    """
    return DatabaseHealthChecker.check_connection()


def get_connection_info() -> dict:
    """
    Connection pool info as dict — backward compatible.

    Returns:
        Dict with health status + pool statistics
    """
    # ✅ Bug Fix 6: get_health_info() use karo — double call nahi
    return DatabaseHealthChecker.get_health_info().to_dict()