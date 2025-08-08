"""Utility functions for application logging."""

import csv
import logging
from datetime import datetime
from pathlib import Path


def setup_logging(config: dict):
    """Setup logging configuration."""
    # Create logs directory structure
    log_dir = Path(__file__).parent.parent.parent / "logs"
    text_log_dir = log_dir / "Text_Logs"
    text_log_dir.mkdir(parents=True, exist_ok=True)

    # Ensure trade log directory exists for completeness
    (log_dir / "Trade_Logs").mkdir(parents=True, exist_ok=True)

    # Get config values
    level = config.get("level", "INFO")
    format_str = config.get(
        "format",
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Create filename with date inside Text_Logs
    filename = text_log_dir / f"holly_ibkr_{datetime.now().strftime('%Y%m%d')}.log"

    # Configure logging
    logging.basicConfig(
        level=getattr(logging, level),
        format=format_str,
        handlers=[logging.FileHandler(filename), logging.StreamHandler()],
    )

    # Set third-party loggers to WARNING
    logging.getLogger("ib_insync").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)


def log_trade(record: dict) -> None:
    """Append a trade record to the daily trade log CSV."""

    trade_dir = Path(__file__).parent.parent.parent / "logs" / "Trade_Logs"
    trade_dir.mkdir(parents=True, exist_ok=True)
    filename = trade_dir / f"trades_{datetime.now().strftime('%Y%m%d')}.csv"

    file_exists = filename.exists()
    with open(filename, "a", newline="") as f:
        writer = csv.DictWriter(
            f, fieldnames=["timestamp", "symbol", "action", "shares", "price"]
        )
        if not file_exists:
            writer.writeheader()
        writer.writerow(record)

