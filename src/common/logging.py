"""
Structured logging, shared by every service.

Why structlog instead of print()/basic logging: every pipeline stage runs as a
separate container and, later, on a schedule with no one watching. When something
breaks at 3am on a cron run, you need log lines that are greppable and carry
context (which posting id, which source) — not a wall of unstructured print output.
"""
from __future__ import annotations

import logging
import sys

import structlog

from src.common.config import get_settings


def configure_logging() -> None:
    settings = get_settings()
    level = getattr(logging, settings.log_level.upper(), logging.INFO)

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=level,
    )

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.dev.ConsoleRenderer()
            if settings.environment == "local"
            else structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)
