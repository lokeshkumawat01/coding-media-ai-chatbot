"""
Centralized logger setup. All modules import `logger` from here
instead of creating their own logging.getLogger() instances.
"""

import logging
import sys

logger = logging.getLogger("solutions_agency_bot")
logger.setLevel(logging.INFO)

if not logger.handlers:
    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
