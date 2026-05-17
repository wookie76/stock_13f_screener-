from __future__ import annotations

import sys

from loguru import logger


def configure_logging(level: str = "INFO") -> None:
    """Configure loguru once for CLI/app usage."""
    logger.remove()
    logger.add(
        sys.stderr,
        level=level.upper(),
        colorize=True,
        format="<green>{time:HH:mm:ss}</green> | <level>{level:<8}</level> | {message}",
    )
