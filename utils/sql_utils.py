"""
SQL utility functions for safe query parameter handling.
"""


def escape_like_wildcards(val: str) -> str:
    """
    Escapes SQL LIKE/ILIKE wildcard characters (%, _, \\)
    so user input can be safely matched literally in queries using ESCAPE '\\'.
    """
    if not val:
        return val
    return val.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
