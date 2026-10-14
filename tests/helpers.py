# ai-service/tests/helpers.py

from sqlalchemy.exc import OperationalError
from typing import Optional


def make_operational_error(
        message: str = "Connection refused",
        statement: Optional[str] = None,
        params: Optional[dict] = None
) -> OperationalError:
    """
    Create SQLAlchemy OperationalError for testing.

    Args:
        message: Error message
        statement: SQL statement that caused error
        params: Query parameters

    Returns:
        OperationalError instance
    """
    if statement is None:
        statement = "SELECT 1"

    if params is None:
        params = {}

    try:
        # SQLAlchemy 2.x approach
        return OperationalError(
            statement=statement,
            params=params,
            orig=Exception(message),
        )
    except TypeError:
        # Fallback for SQLAlchemy 1.x
        try:
            return OperationalError(message, None, None)
        except Exception:
            # Ultimate fallback
            err = OperationalError.__new__(OperationalError)
            err.args = (message, statement, params)
            return err