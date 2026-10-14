# ai-service/core/logging_config.py

import logging
import sys
from typing import Optional

# ═══════════════════════════════════════════════════════════
# LOGGING CONFIGURATION
# ═══════════════════════════════════════════════════════════
#
# SOLID:
#   S → Sirf logging setup ka kaam
#   D → Settings inject — hardcode nahi
#
# Logic:
#   Dev → human readable console format
#   Prod → JSON structured format (ELK stack ke liye)
#   Noisy libraries → WARNING level
#
# System Design:
#   main.py ke pehle setup_logging() call karo
#   Baaki modules logger = logging.getLogger(__name__) use karein


def setup_logging(debug: bool = False) -> None:
    """
    Application logging configure karo.

    SOLID S: Sirf logging setup.

    Logic:
        debug=True  → DEBUG level, human readable
        debug=False → INFO level, structured

    Args:
        debug: Debug mode flag
    """
    log_level = logging.DEBUG if debug else logging.INFO

    # ✅ Root logger configure
    logging.basicConfig(
        level   = log_level,
        format  = _get_format(debug),
        stream  = sys.stdout,
        force   = True,   # Existing handlers override
    )

    # ✅ Noisy libraries quiet karo
    _silence_noisy_loggers(debug)

    logging.getLogger(__name__).info(
        "Logging configured: level=%s, format=%s",
        logging.getLevelName(log_level),
        "debug" if debug else "structured",
    )


def _get_format(debug: bool) -> str:
    """
    Log format return karo.

    Logic:
        Dev: Human readable — easy to read
        Prod: JSON structured — log aggregators ke liye
    """
    if debug:
        # Human readable — dev ke liye
        return (
            "%(asctime)s | %(levelname)-8s | "
            "%(name)s:%(lineno)d | %(message)s"
        )
    else:
        # Structured — ELK/CloudWatch ke liye
        return (
            '{"time":"%(asctime)s","level":"%(levelname)s",'
            '"logger":"%(name)s","message":"%(message)s"}'
        )


def _silence_noisy_loggers(debug: bool) -> None:
    """
    Third-party noisy loggers quiet karo.

    Logic:
        Production mein SQL queries log mat karo
        Debug mein sab dekhna chahte hain
    """
    noisy_loggers = [
        "sqlalchemy.engine",
        "sqlalchemy.pool",
        "sqlalchemy.dialects",
        "urllib3",
        "httpx",
        "httpcore",
    ]

    level = logging.DEBUG if debug else logging.WARNING

    for name in noisy_loggers:
        logging.getLogger(name).setLevel(level)