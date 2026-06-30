"""
Logging configuration for Trading Bot.
Sets up structured logging to both console and a rotating log file.
"""

import logging
import logging.handlers
import os
from pathlib import Path


LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
LOG_FILE = LOG_DIR / "trading_bot.log"


def setup_logging(level: str = "INFO") -> logging.Logger:
    """Configure and return the root logger for the trading bot."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    log_level = getattr(logging, level.upper(), logging.INFO)

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )

    # Rotating file handler — keeps up to 5 × 5 MB files
    file_handler = logging.handlers.RotatingFileHandler(
        LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    file_handler.setLevel(log_level)
    file_handler.setFormatter(formatter)

    # Console handler — INFO and above only
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)

    root_logger = logging.getLogger("trading_bot")
    root_logger.setLevel(log_level)
    root_logger.propagate = False

    if not root_logger.handlers:
        root_logger.addHandler(file_handler)
        root_logger.addHandler(console_handler)

    return root_logger


def get_logger(name: str) -> logging.Logger:
    """Return a child logger scoped to a module."""
    return logging.getLogger(f"trading_bot.{name}")
