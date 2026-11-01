"""Structured logging setup, replacing the original project's `print()` calls.

Call `configure_logging()` once at process start (done in ui/streamlit_app.py).
Everywhere else, just do `logger = logging.getLogger(__name__)` and log normally.
"""

from __future__ import annotations

import logging
import sys


def configure_logging(level: str = "INFO") -> None:
    root = logging.getLogger()
    if root.handlers:
        # Already configured (e.g. Streamlit reruns the script on every interaction).
        root.setLevel(level)
        return

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    )
    root.addHandler(handler)
    root.setLevel(level)

    # Quiet down noisy third-party loggers unless we're debugging.
    if level.upper() != "DEBUG":
        for noisy in ("urllib3", "httpx", "httpcore"):
            logging.getLogger(noisy).setLevel(logging.WARNING)
