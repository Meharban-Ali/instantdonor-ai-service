# ai-service/tests/test_database.py

import threading
from unittest.mock import MagicMock, patch, call

import pytest
from sqlalchemy.exc import SQLAlchemyError

from core.database import (
    ConnectArgsFactory,
    DatabaseEngineFactory,
    DatabaseHealthChecker,
    DBHealthInfo,
    check_db_connection,
    get_connection_info,
    get_db,
    get_db_context,
)

# ✅ Bug Fix: Import directly from helpers (no 'tests.' prefix)
from helpers import make_operational_error


# ═══════════════════════════════════════════════════════════
# ConnectArgsFactory Tests
# ═══════════════════════════════════════════════════════════
#
# SOLID S: Sirf ConnectArgsFactory test karna
#
# Logic:
#   Har DB type ke liye correct args verify karo
#   Edge cases: unknown DB, empty URL
class TestConnectArgsFactory:
    """ConnectArgsFactory — DB-specific connection args."""

    # ── MySQL Tests ────────────────────────────────────────

    def test_mysql_pymysql_has_charset(self):
        """MySQL+PyMySQL → charset=utf8mb4."""
        args = ConnectArgsFactory.get(
            "mysql+pymysql://root:12345@localhost/dummy_db"
        )
        assert "charset" in args
        assert args["charset"] == "utf8mb4"

    def test_mysql_has_connect_timeout(self):
        """MySQL → connect_timeout present aur positive."""
        args = ConnectArgsFactory.get(
            "mysql+pymysql://root:12345@localhost/dummy_db"
        )
        assert "connect_timeout" in args
        assert isinstance(args["connect_timeout"], int)
        assert args["connect_timeout"] > 0

    def test_mysql_has_autocommit_false(self):
        """MySQL → autocommit=False."""
        args = ConnectArgsFactory.get(
            "mysql+pymysql://root:12345@localhost/dummy_db"
        )
        assert "autocommit" in args
        assert args["autocommit"] is False

    def test_mysql_aiomysql_detected(self):
        """mysql+aiomysql → MySQL args milne chahiye."""
        args = ConnectArgsFactory.get(
            "mysql+aiomysql://root:12345@localhost/dummy_db"
        )
        assert "charset" in args
        assert args["charset"] == "utf8mb4"

    def test_mariadb_detected(self):
        """mariadb URL → MySQL args milne chahiye."""
        args = ConnectArgsFactory.get(
            "mariadb+pymysql://root:12345@localhost/dummy_db"
        )
        assert "charset" in args

    # ── PostgreSQL Tests ───────────────────────────────────

    def test_postgresql_has_connect_timeout(self):
        """PostgreSQL → connect_timeout present."""
        args = ConnectArgsFactory.get(
            "postgresql+psycopg2://user:pass@localhost/db"
        )
        assert "connect_timeout" in args

    def test_postgresql_has_application_name(self):
        """PostgreSQL → application_name present aur non-empty."""
        args = ConnectArgsFactory.get(
            "postgresql+psycopg2://user:pass@localhost/db"
        )
        assert "application_name" in args
        assert len(args["application_name"]) > 0

    def test_postgresql_asyncpg_detected(self):
        """postgresql+asyncpg → PostgreSQL args."""
        args = ConnectArgsFactory.get(
            "postgresql+asyncpg://user:pass@localhost/db"
        )
        assert "connect_timeout" in args

    def test_postgres_shorthand_detected(self):
        """postgres:// shorthand → PostgreSQL args."""
        args = ConnectArgsFactory.get(
            "postgres://user:pass@localhost/db"
        )
        assert "connect_timeout" in args

    # ── SQLite Tests ───────────────────────────────────────

    def test_sqlite_check_same_thread_false(self):
        """SQLite → check_same_thread=False."""
        args = ConnectArgsFactory.get("sqlite:///test.db")
        assert "check_same_thread" in args
        assert args["check_same_thread"] is False

    def test_sqlite_memory_detected(self):
        """SQLite in-memory → correct args."""
        args = ConnectArgsFactory.get("sqlite:///:memory:")
        assert "check_same_thread" in args

    # ── Unknown/Edge Cases ─────────────────────────────────

    def test_unknown_db_returns_empty_dict(self):
        """Unknown DB → empty dict."""
        args = ConnectArgsFactory.get("unknown://localhost/dummy_db")
        assert args == {}

    def test_empty_url_returns_empty_dict(self):
        """Empty URL → empty dict — crash nahi."""
        args = ConnectArgsFactory.get("")
        assert args == {}


# ═══════════════════════════════════════════════════════════
# DatabaseEngineFactory Tests
# ═══════════════════════════════════════════════════════════
#
# SOLID S: Sirf engine factory test karna
class TestDatabaseEngineFactory:
    """DatabaseEngineFactory — engine + session management."""

    def setup_method(self):
        """Har test se pehle clean state."""
        DatabaseEngineFactory.reset()

    def teardown_method(self):
        """Har test ke baad clean state."""
        DatabaseEngineFactory.reset()

    # ── URL Validation ─────────────────────────────────────

    def test_empty_url_raises_value_error(self):
        """Empty DB_URL → ValueError."""
        mock_config = MagicMock()
        mock_config.db_url = ""

        with pytest.raises(ValueError, match="DB_URL"):
            DatabaseEngineFactory.get_engine(config=mock_config)

    def test_none_url_raises_error(self):
        """None URL → error raise hona chahiye."""
        mock_config = MagicMock()
        mock_config.db_url = None

        with pytest.raises((ValueError, AttributeError, TypeError)):
            DatabaseEngineFactory.get_engine(config=mock_config)

    # ── Reset Tests ────────────────────────────────────────

    def test_reset_clears_engine(self):
        """Reset → engine None hona chahiye."""
        DatabaseEngineFactory._engine = MagicMock()
        DatabaseEngineFactory.reset()
        assert DatabaseEngineFactory._engine is None

    def test_reset_clears_session_factory(self):
        """Reset → session factory None hona chahiye."""
        DatabaseEngineFactory._session_factory = MagicMock()
        DatabaseEngineFactory.reset()
        assert DatabaseEngineFactory._session_factory is None

    def test_reset_clears_both(self):
        """Reset → engine aur session factory dono clear."""
        DatabaseEngineFactory._engine = MagicMock()
        DatabaseEngineFactory._session_factory = MagicMock()
        DatabaseEngineFactory.reset()
        assert DatabaseEngineFactory._engine is None
        assert DatabaseEngineFactory._session_factory is None

    # ── Thread Safety Tests ────────────────────────────────

    def test_thread_safe_engine_creation(self, mock_db_config):
        """
        ✅ Bug Fix 3: Concurrent calls — single engine hona chahiye.

        Logic:
            Global mock engine banao
            10 threads ek saath call karein
            Sirf 1 engine create hona chahiye
            threading.Lock → race condition prevent
        """
        call_count = []
        errors = []
        shared_lock = threading.Lock()
        mock_engine_ = MagicMock()

        # ✅ Singleton counter
        def counting_create(config):
            with shared_lock:
                call_count.append(1)
            return mock_engine_

        with patch.object(
                DatabaseEngineFactory,
                '_create_engine',
                side_effect=counting_create
        ):
            threads = [
                threading.Thread(
                    target=lambda: _safe_get_engine(
                        mock_db_config, errors
                    )
                )
                for _ in range(10)
            ]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

        # ✅ No errors
        assert not errors, f"Thread errors: {errors}"

        # ✅ _create_engine sirf ek baar call hona chahiye
        assert len(call_count) == 1, (
            f"_create_engine called {len(call_count)} times, expected 1"
        )

    def test_get_engine_singleton(self, mock_db_config):
        """get_engine() → same instance return hona chahiye."""
        mock_engine_ = MagicMock()
        with patch.object(
                DatabaseEngineFactory,
                '_create_engine',
                return_value=mock_engine_
        ):
            engine1 = DatabaseEngineFactory.get_engine(
                config=mock_db_config
            )
            engine2 = DatabaseEngineFactory.get_engine(
                config=mock_db_config
            )
            assert engine1 is engine2

    def test_get_session_factory_singleton(self, mock_db_config):
        """Session factory → singleton hona chahiye."""
        mock_engine_ = MagicMock()
        with patch.object(
                DatabaseEngineFactory,
                '_create_engine',
                return_value=mock_engine_
        ):
            sf1 = DatabaseEngineFactory.get_session_factory(
                config=mock_db_config
            )
            sf2 = DatabaseEngineFactory.get_session_factory(
                config=mock_db_config
            )
            assert sf1 is sf2


# ── Helper for thread safety test ──────────────────────────

def _safe_get_engine(config, errors: list):
    """Thread-safe engine get — errors capture karo."""
    try:
        DatabaseEngineFactory.get_engine(config=config)
    except Exception as e:
        errors.append(str(e))


# ═══════════════════════════════════════════════════════════
# get_db() Tests — FastAPI Dependency
# ═══════════════════════════════════════════════════════════
#
# SOLID S: Sirf session lifecycle test karna
class TestGetDb:
    """get_db() — FastAPI DB dependency lifecycle tests."""

    def _make_patched_db(self, mock_session):
        """
        Helper: get_db() generator with patched session factory.

        Logic:
            patch session factory → mock_session return karo
            Generator create karo
        """
        session_factory_mock = MagicMock(return_value=mock_session)
        patcher = patch(
            'core.database.DatabaseEngineFactory.get_session_factory',
            return_value=session_factory_mock
        )
        return patcher

    def test_commit_on_success(self, mock_session):
        """
        ✅ Success → commit hona chahiye.

        Logic:
            Generator create → next() → yield
            next() again → trigger normal completion → commit
        """
        with patch(
                'core.database.DatabaseEngineFactory.get_session_factory',
                return_value=MagicMock(return_value=mock_session)
        ):
            gen = get_db()
            next(gen)  # yield tak execute karo

            # Normal generator completion to trigger commit
            try:
                next(gen)
            except StopIteration:
                pass

            mock_session.commit.assert_called_once()

    def test_rollback_on_sqlalchemy_error(self, mock_session):
        """SQLAlchemyError → rollback hona chahiye."""
        with patch(
                'core.database.DatabaseEngineFactory.get_session_factory',
                return_value=MagicMock(return_value=mock_session)
        ):
            gen = get_db()
            next(gen)

            with pytest.raises(SQLAlchemyError):
                gen.throw(
                    SQLAlchemyError,
                    SQLAlchemyError("DB error")
                )

            mock_session.rollback.assert_called_once()
            mock_session.close.assert_called_once()

    def test_rollback_on_generic_exception(self, mock_session):
        """Generic exception → rollback hona chahiye."""
        with patch(
                'core.database.DatabaseEngineFactory.get_session_factory',
                return_value=MagicMock(return_value=mock_session)
        ):
            gen = get_db()
            next(gen)

            with pytest.raises(ValueError):
                gen.throw(ValueError, ValueError("Unexpected"))

            mock_session.rollback.assert_called_once()

    def test_session_always_closed(self, mock_session):
        """
        Session ALWAYS close honi chahiye — success ya error.

        Logic:
            finally block → close() always call hota
            Resource leak prevent
        """
        with patch(
                'core.database.DatabaseEngineFactory.get_session_factory',
                return_value=MagicMock(return_value=mock_session)
        ):
            gen = get_db()
            next(gen)

            with pytest.raises(RuntimeError):
                gen.throw(RuntimeError, RuntimeError("Fatal"))

            # ✅ close() always called
            mock_session.close.assert_called_once()

    def test_get_db_returns_iterator(self):
        """get_db() → Iterator/Generator return hona chahiye."""
        result = get_db()
        # Generator protocol check
        assert hasattr(result, '__next__') or hasattr(result, 'send')
        result.close()  # Cleanup


# ═══════════════════════════════════════════════════════════
# get_db_context() Tests — Context Manager
# ═══════════════════════════════════════════════════════════
class TestGetDbContext:
    """get_db_context() — Service layer context manager."""

    def test_commit_on_success(self, mock_session):
        """Context manager → success pe commit + close."""
        with patch(
                'core.database.DatabaseEngineFactory.get_session_factory',
                return_value=MagicMock(return_value=mock_session)
        ):
            with get_db_context():
                pass  # No exception

            mock_session.commit.assert_called_once()
            mock_session.close.assert_called_once()

    def test_rollback_on_value_error(self, mock_session):
        """ValueError → rollback + close."""
        with patch(
                'core.database.DatabaseEngineFactory.get_session_factory',
                return_value=MagicMock(return_value=mock_session)
        ):
            with pytest.raises(ValueError):
                with get_db_context():
                    raise ValueError("Test error")

            mock_session.rollback.assert_called_once()
            mock_session.close.assert_called_once()

    def test_rollback_on_sqlalchemy_error(self, mock_session):
        """SQLAlchemyError → rollback + close."""
        with patch(
                'core.database.DatabaseEngineFactory.get_session_factory',
                return_value=MagicMock(return_value=mock_session)
        ):
            with pytest.raises(SQLAlchemyError):
                with get_db_context():
                    raise SQLAlchemyError("DB error")

            mock_session.rollback.assert_called_once()
            mock_session.close.assert_called_once()

    def test_no_rollback_on_success(self, mock_session):
        """Success → rollback nahi hona chahiye."""
        with patch(
                'core.database.DatabaseEngineFactory.get_session_factory',
                return_value=MagicMock(return_value=mock_session)
        ):
            with get_db_context():
                pass

            mock_session.rollback.assert_not_called()


# ═══════════════════════════════════════════════════════════
# DatabaseHealthChecker Tests
# ═══════════════════════════════════════════════════════════
class TestDatabaseHealthChecker:
    """DatabaseHealthChecker — health check + retry logic."""

    # ── Connection Tests ───────────────────────────────────

    def test_check_connection_success(self, mock_engine):
        """DB connected → True."""
        with patch.object(
                DatabaseEngineFactory, 'get_engine',
                return_value=mock_engine
        ):
            result = DatabaseHealthChecker.check_connection()
            assert result is True

    def test_check_connection_operational_error(self):
        """
        OperationalError → False.

        ✅ Bug Fix 6: make_operational_error correct format.
        """
        with patch.object(
                DatabaseEngineFactory, 'get_engine',
                side_effect=make_operational_error("Connection refused")
        ):
            result = DatabaseHealthChecker.check_connection()
            assert result is False

    def test_check_connection_unexpected_error(self):
        """Unexpected error → False (no retry)."""
        with patch.object(
                DatabaseEngineFactory, 'get_engine',
                side_effect=RuntimeError("Critical!")
        ):
            result = DatabaseHealthChecker.check_connection()
            assert result is False

    # ── Retry Tests ────────────────────────────────────────

    def test_retry_on_operational_error(self):
        """
        MAX_RETRIES baar retry hona chahiye.

        Logic:
            OperationalError → retry
            3 attempts → False
            sleep calls = MAX_RETRIES - 1
        """
        with patch.object(
                DatabaseEngineFactory, 'get_engine',
                side_effect=make_operational_error("Connection failed")
        ) as mock_get:
            with patch('time.sleep') as mock_sleep:
                result = DatabaseHealthChecker.check_connection()

                # ✅ Exactly MAX_RETRIES attempts
                assert mock_get.call_count == \
                       DatabaseHealthChecker.MAX_RETRIES

                # ✅ MAX_RETRIES-1 sleeps (last attempt no sleep)
                assert mock_sleep.call_count == \
                       DatabaseHealthChecker.MAX_RETRIES - 1

                assert result is False

    def test_retry_succeeds_on_second_attempt(self, mock_engine):
        """
        ✅ Bug Fix 5: Second attempt success → True.

        Logic:
            1st: OperationalError → retry
            2nd: mock_engine return → connect() success
        """
        with patch.object(
                DatabaseEngineFactory, 'get_engine',
                side_effect=[
                    make_operational_error("Blip"),  # 1st fail
                    mock_engine,                      # 2nd success
                ]
        ):
            with patch('time.sleep'):
                result = DatabaseHealthChecker.check_connection()
                assert result is True

    def test_no_retry_on_runtime_error(self):
        """Non-OperationalError → 1 attempt only, no retry."""
        with patch.object(
                DatabaseEngineFactory, 'get_engine',
                side_effect=RuntimeError("Critical!")
        ) as mock_get:
            result = DatabaseHealthChecker.check_connection()
            assert mock_get.call_count == 1
            assert result is False

    # ── Health Info Tests ──────────────────────────────────

    def test_health_info_returns_dbhealthinfo(self, mock_engine):
        """get_health_info() → DBHealthInfo instance."""
        with patch.object(
                DatabaseHealthChecker, 'check_connection',
                return_value=True
        ):
            with patch.object(
                    DatabaseEngineFactory, 'get_engine',
                    return_value=mock_engine
            ):
                info = DatabaseHealthChecker.get_health_info()
                assert isinstance(info, DBHealthInfo)

    def test_health_info_healthy(self, mock_engine):
        """Healthy → status='healthy', is_healthy=True."""
        with patch.object(
                DatabaseHealthChecker, 'check_connection',
                return_value=True
        ):
            with patch.object(
                    DatabaseEngineFactory, 'get_engine',
                    return_value=mock_engine
            ):
                info = DatabaseHealthChecker.get_health_info()
                assert info.is_healthy is True
                assert info.status == "healthy"

    def test_health_info_unhealthy(self, mock_engine):
        """Unhealthy → status='unhealthy', is_healthy=False."""
        with patch.object(
                DatabaseHealthChecker, 'check_connection',
                return_value=False
        ):
            with patch.object(
                    DatabaseEngineFactory, 'get_engine',
                    return_value=mock_engine
            ):
                info = DatabaseHealthChecker.get_health_info()
                assert info.is_healthy is False
                assert info.status == "unhealthy"

    def test_health_info_pool_stats(self, mock_engine):
        """Pool stats correctly populated."""
        with patch.object(
                DatabaseHealthChecker, 'check_connection',
                return_value=True
        ):
            with patch.object(
                    DatabaseEngineFactory, 'get_engine',
                    return_value=mock_engine
            ):
                info = DatabaseHealthChecker.get_health_info()
                assert info.pool_size == 5
                assert info.checked_out == 2
                assert info.overflow == 0
                assert info.checked_in == 3

    def test_health_info_latency_non_negative(self, mock_engine):
        """Latency ms >= 0."""
        with patch.object(
                DatabaseHealthChecker, 'check_connection',
                return_value=True
        ):
            with patch.object(
                    DatabaseEngineFactory, 'get_engine',
                    return_value=mock_engine
            ):
                info = DatabaseHealthChecker.get_health_info()
                assert info.latency_ms >= 0.0

    def test_health_info_single_check_call(self, mock_engine):
        """
        ✅ Bug Fix 6: check_connection() sirf ek baar call hona.

        Logic:
            Double DB call bug fix verify karo
        """
        with patch.object(
                DatabaseHealthChecker, 'check_connection',
                return_value=True
        ) as mock_check:
            with patch.object(
                    DatabaseEngineFactory, 'get_engine',
                    return_value=mock_engine
            ):
                DatabaseHealthChecker.get_health_info()
                assert mock_check.call_count == 1

    def test_health_info_pool_error_returns_zeros(self):
        """Pool AttributeError → zeros return, no crash."""
        broken_engine = MagicMock()
        broken_engine.pool.size.side_effect = AttributeError("No size")

        with patch.object(
                DatabaseHealthChecker, 'check_connection',
                return_value=True
        ):
            with patch.object(
                    DatabaseEngineFactory, 'get_engine',
                    return_value=broken_engine
            ):
                info = DatabaseHealthChecker.get_health_info()
                assert isinstance(info, DBHealthInfo)
                assert info.pool_size == 0

    def test_to_dict_has_all_keys(self, mock_engine):
        """to_dict() → sab required keys present."""
        with patch.object(
                DatabaseHealthChecker, 'check_connection',
                return_value=True
        ):
            with patch.object(
                    DatabaseEngineFactory, 'get_engine',
                    return_value=mock_engine
            ):
                info = DatabaseHealthChecker.get_health_info()
                d = info.to_dict()

                expected = {
                    "status", "is_healthy", "pool_size",
                    "checked_out", "overflow",
                    "checked_in", "latency_ms"
                }
                assert set(d.keys()) == expected


# ═══════════════════════════════════════════════════════════
# DBHealthInfo Tests
# ═══════════════════════════════════════════════════════════
class TestDBHealthInfo:
    """DBHealthInfo frozen dataclass tests."""

    def _make_info(self, is_healthy: bool = True) -> DBHealthInfo:
        """Test DBHealthInfo create karo."""
        return DBHealthInfo(
            status="healthy" if is_healthy else "unhealthy",
            is_healthy=is_healthy,
            pool_size=5,
            checked_out=2,
            overflow=0,
            checked_in=3,
            latency_ms=15.5,
        )

    def test_frozen_immutable(self):
        """
        ✅ Bug Fix 2: DBHealthInfo → immutable hona chahiye.

        Logic:
            frozen=True → FrozenInstanceError (AttributeError)
            Status read-only hai → assign karna fail karna chahiye
        """
        info = self._make_info()
        # ✅ Bug Fix 2: Specific exception types
        with pytest.raises((AttributeError, TypeError)):
            info.status = "changed"  # type: ignore

    def test_to_dict_all_keys(self):
        """to_dict() → sab required keys present."""
        info = self._make_info()
        d = info.to_dict()

        expected_keys = {
            "status", "is_healthy", "pool_size",
            "checked_out", "overflow",
            "checked_in", "latency_ms"
        }
        assert set(d.keys()) == expected_keys

    def test_healthy_values(self):
        """Healthy info → correct field values."""
        info = self._make_info(is_healthy=True)
        assert info.status == "healthy"
        assert info.is_healthy is True
        assert info.pool_size == 5
        assert info.latency_ms == 15.5

    def test_unhealthy_values(self):
        """Unhealthy info → correct field values."""
        info = self._make_info(is_healthy=False)
        assert info.status == "unhealthy"
        assert info.is_healthy is False

    def test_to_dict_values_match_fields(self):
        """to_dict() values → fields se match karna chahiye."""
        info = self._make_info()
        d = info.to_dict()
        assert d["status"] == info.status
        assert d["is_healthy"] == info.is_healthy
        assert d["pool_size"] == info.pool_size
        assert d["latency_ms"] == info.latency_ms


# ═══════════════════════════════════════════════════════════
# Convenience Functions Tests
# ═══════════════════════════════════════════════════════════
class TestConvenienceFunctions:
    """check_db_connection() aur get_connection_info() tests."""

    def test_check_db_connection_delegates(self):
        """check_db_connection() → DatabaseHealthChecker delegate."""
        with patch.object(
                DatabaseHealthChecker, 'check_connection',
                return_value=True
        ) as mock_check:
            result = check_db_connection()
            assert result is True
            mock_check.assert_called_once()

    def test_check_db_connection_returns_false_on_fail(self):
        """check_db_connection() → False when DB down."""
        with patch.object(
                DatabaseHealthChecker, 'check_connection',
                return_value=False
        ):
            result = check_db_connection()
            assert result is False

    def test_get_connection_info_returns_dict(self, mock_engine):
        """get_connection_info() → dict with required keys."""
        with patch.object(
                DatabaseHealthChecker, 'check_connection',
                return_value=True
        ):
            with patch.object(
                    DatabaseEngineFactory, 'get_engine',
                    return_value=mock_engine
            ):
                result = get_connection_info()
                assert isinstance(result, dict)
                assert "status" in result
                assert "is_healthy" in result
                assert "pool_size" in result