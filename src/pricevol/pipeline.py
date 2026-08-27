"""Ingest prices and compute volatility end to end."""

from __future__ import annotations

from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Callable, Iterable, List, Optional

import pandas as pd

from . import db as db_module
from .config import DEFAULT_DB_PATH, DEFAULT_START, DEFAULT_WINDOW
from .fetch import fetch_prices
from .sources import DEFAULT_SOURCE
from .volatility import realized_volatility_table


@dataclass
class IngestResult:
    ticker: str
    rows: int
    first_date: Optional[str] = None
    last_date: Optional[str] = None
    error: Optional[str] = None
    source: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.error is None


def ingest(
    tickers: Iterable[str],
    db_path: Path | str = DEFAULT_DB_PATH,
    start: Optional[str] = None,
    end: Optional[str] = None,
    full_refresh: bool = False,
    source: Optional[str] = None,
    fetcher: Optional[Callable[..., pd.DataFrame]] = None,
) -> List[IngestResult]:
    """Download each ticker and store its bars.

    By default only the range since the newest stored date is requested (that
    date is re-fetched so a partial last bar gets corrected). ``full_refresh``
    or an explicit ``start`` overrides that. A failure on one ticker is
    recorded and the rest still run.

    ``source`` names a provider from :mod:`pricevol.sources`; ``fetcher`` can
    override the download callable outright (used by the tests).
    """
    source = source or DEFAULT_SOURCE
    fetcher = fetcher or partial(fetch_prices, source=source)
    results: List[IngestResult] = []
    conn = db_module.connect(db_path)
    try:
        db_module.init_db(conn)
        for ticker in tickers:
            ticker_start = start
            if ticker_start is None:
                stored = None if full_refresh else db_module.latest_date(conn, ticker)
                ticker_start = stored or DEFAULT_START
            try:
                frame = fetcher(ticker, start=ticker_start, end=end)
            except Exception as exc:  # noqa: BLE001 - report and continue
                results.append(IngestResult(ticker, 0, error=str(exc), source=source))
                continue

            rows = db_module.upsert_prices(conn, ticker, frame, source=source)
            first = last = None
            if rows:
                first = frame.index.min().strftime("%Y-%m-%d")
                last = frame.index.max().strftime("%Y-%m-%d")
            results.append(IngestResult(ticker, rows, first, last, source=source))
    finally:
        conn.close()
    return results


def compute(
    tickers: Optional[Iterable[str]] = None,
    db_path: Path | str = DEFAULT_DB_PATH,
    window: int = DEFAULT_WINDOW,
    store: bool = True,
) -> pd.DataFrame:
    """Compute rolling realized volatility from stored prices.

    Returns the full ticker/date/realized_vol frame and, unless ``store`` is
    False, writes it to the ``realized_vol`` table under ``window_days``.
    """
    conn = db_module.connect(db_path)
    try:
        db_module.init_db(conn)
        tickers = list(tickers) if tickers else None
        prices = db_module.read_prices(conn, tickers)
        vol = realized_volatility_table(prices, window=window)
        if store and not vol.empty:
            db_module.upsert_volatility(conn, vol, window=window)
        return vol
    finally:
        conn.close()


def latest_volatility(
    tickers: Optional[Iterable[str]] = None,
    db_path: Path | str = DEFAULT_DB_PATH,
    window: int = DEFAULT_WINDOW,
) -> pd.DataFrame:
    """Most recent stored volatility per ticker."""
    conn = db_module.connect(db_path)
    try:
        db_module.init_db(conn)
        return db_module.read_volatility(
            conn, list(tickers) if tickers else None, window=window, latest_only=True
        )
    finally:
        conn.close()
