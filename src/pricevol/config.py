"""Defaults and ticker-list handling."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable, List

# Trading days used to annualize a daily standard deviation.
TRADING_DAYS_PER_YEAR = 252

# Rolling window (in trading days) for realized volatility.
DEFAULT_WINDOW = 20

# Where prices land unless overridden by --db or $PRICEVOL_DB.
DEFAULT_DB_PATH = Path(os.environ.get("PRICEVOL_DB", "data/prices.sqlite"))

# Newline-delimited ticker list used when none are given on the command line.
DEFAULT_TICKERS_FILE = Path(os.environ.get("PRICEVOL_TICKERS", "tickers.txt"))

DEFAULT_START = "2015-01-01"


def normalize_ticker(ticker: str) -> str:
    return ticker.strip().upper()


def parse_tickers(raw: Iterable[str]) -> List[str]:
    """Clean, de-duplicate and upper-case tickers while preserving order.

    Accepts either separate arguments or comma-separated strings, so both
    ``ingest AAPL MSFT`` and ``ingest AAPL,MSFT`` work.
    """
    seen = set()
    out = []
    for item in raw:
        for part in str(item).split(","):
            ticker = normalize_ticker(part)
            if not ticker or ticker.startswith("#"):
                continue
            if ticker not in seen:
                seen.add(ticker)
                out.append(ticker)
    return out


def load_tickers(tickers: Iterable[str] | None = None, path: Path | None = None) -> List[str]:
    """Return tickers from the command line, else from the ticker file."""
    parsed = parse_tickers(tickers or [])
    if parsed:
        return parsed

    path = Path(path or DEFAULT_TICKERS_FILE)
    if not path.exists():
        raise FileNotFoundError(
            f"No tickers given and no ticker file at {path}. "
            "Pass tickers as arguments or create the file with one symbol per line."
        )
    lines = [line.split("#", 1)[0] for line in path.read_text().splitlines()]
    found = parse_tickers(lines)
    if not found:
        raise ValueError(f"Ticker file {path} contains no tickers.")
    return found
