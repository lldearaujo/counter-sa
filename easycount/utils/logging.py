"""Structured logging setup for EasyCount."""

import logging
import sys


def setup_logging(level: str = "INFO", stream_id: str | None = None) -> logging.Logger:
    name = f"easycount.{stream_id}" if stream_id else "easycount"
    logger = logging.getLogger(name)

    if logger.handlers:
        return logger

    handler = logging.StreamHandler(sys.stdout)
    fmt = "%(asctime)s [%(levelname)s] %(name)s — %(message)s"
    handler.setFormatter(logging.Formatter(fmt, datefmt="%Y-%m-%dT%H:%M:%S"))

    logger.addHandler(handler)
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    logger.propagate = False
    return logger
