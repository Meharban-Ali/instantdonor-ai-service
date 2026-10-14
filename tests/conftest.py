# ai-service/tests/conftest.py

import sys
from pathlib import Path
import warnings

# ✅ Add parent directory to Python path (critical for imports)
sys.path.insert(0, str(Path(__file__).parent.parent))

# ✅ Suppress Pydantic warnings
warnings.filterwarnings("ignore", category=UserWarning, message=".*protected namespace.*")
warnings.filterwarnings("ignore", category=UserWarning, module="pydantic")

import pytest
from unittest.mock import MagicMock

# Import after path setup
from core.database import DatabaseEngineFactory

# Import helper from helpers.py
from helpers import make_operational_error  # ✅ Note: no 'tests.' prefix


# ─────────────────────────────────────────────────────────────
# Engine reset fixture
# ─────────────────────────────────────────────────────────────

@pytest.fixture(autouse=False)
def reset_engine():
    """Reset engine after each test for isolation."""
    DatabaseEngineFactory.reset()
    yield
    DatabaseEngineFactory.reset()


# ─────────────────────────────────────────────────────────────
# Mock Engine fixture
# ─────────────────────────────────────────────────────────────

@pytest.fixture
def mock_engine():
    """Mock SQLAlchemy engine with pool support."""
    engine = MagicMock()

    # Context manager support
    mock_conn = MagicMock()
    mock_conn.execute = MagicMock(return_value=None)

    mock_context = MagicMock()
    mock_context.__enter__ = MagicMock(return_value=mock_conn)
    mock_context.__exit__ = MagicMock(return_value=False)
    engine.connect.return_value = mock_context

    # Pool attributes
    engine.pool = MagicMock()
    engine.pool.size = MagicMock(return_value=5)
    engine.pool.checkedout = MagicMock(return_value=2)
    engine.pool.overflow = MagicMock(return_value=0)
    engine.pool.checkedin = MagicMock(return_value=3)

    return engine


# ─────────────────────────────────────────────────────────────
# Mock DB Config fixture
# ─────────────────────────────────────────────────────────────

@pytest.fixture
def mock_db_config():
    """Mock database configuration."""
    config = MagicMock()
    config.db_url = "mysql+pymysql://root:test@localhost:3306/test_db"
    config.db_pool_size = 5
    config.db_max_overflow = 10
    config.db_pool_timeout = 30
    config.db_pool_recycle = 1800
    config.db_pool_pre_ping = True
    config.db_echo = False
    return config


# ─────────────────────────────────────────────────────────────
# Mock Session fixture
# ─────────────────────────────────────────────────────────────

@pytest.fixture
def mock_session():
    """Mock SQLAlchemy session."""
    session = MagicMock()
    session.commit = MagicMock(return_value=None)
    session.rollback = MagicMock(return_value=None)
    session.close = MagicMock(return_value=None)
    session.execute = MagicMock(return_value=None)
    return session


# ─────────────────────────────────────────────────────────────
# Export helpers
# ─────────────────────────────────────────────────────────────

__all__ = ["make_operational_error"]