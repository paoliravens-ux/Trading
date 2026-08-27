"""Download daily bars from Yahoo Finance via yfinance."""

from __future__ import annotations

import time
from typing import Optional

import pandas as pd

from .db import PRICE_COLUMNS

_RENAMES = {
    "open": "open",
    "high": "high",
    "low": "low",
    "close": "close",
    "adj close": "adj_close",
    "adjclose": "adj_close",
    "volume": "volume",
}


def _flatten_columns(raw: pd.DataFrame, ticker: str) -> pd.DataFrame:
    """yfinance returns MultiIndex columns for some versions/queries."""
    if not isinstance(raw.columns, pd.MultiIndex):
        return raw
    for level in range(raw.columns.nlevels):
        if ticker in raw.columns.get_level_values(level):
            return raw.xs(ticker, axis=1, level=level)
    # Single unnamed ticker level: drop the level that carries no price names.
    return raw.droplevel(list(range(1, raw.columns.nlevels)), axis=1)


def normalize_frame(raw: pd.DataFrame, ticker: str) -> pd.DataFrame:
    """Turn a yfinance frame into the column layout used by the prices table."""
    empty = pd.DataFrame(columns=PRICE_COLUMNS, index=pd.DatetimeIndex([], name="date"))
    if raw is None or raw.empty:
        return empty

    frame = _flatten_columns(raw, ticker).copy()
    frame.columns = [_RENAMES.get(str(c).strip().lower(), str(c).strip().lower()) for c in frame.columns]
    frame = frame.loc[:, ~frame.columns.duplicated()]

    if "adj_close" not in frame.columns and "close" in frame.columns:
        # auto_adjust=True already folds dividends/splits into "close".
        frame["adj_close"] = frame["close"]
    for col in PRICE_COLUMNS:
        if col not in frame.columns:
            frame[col] = pd.NA

    frame = frame[PRICE_COLUMNS]
    frame.index = pd.to_datetime(frame.index).tz_localize(None).normalize()
    frame.index.name = "date"
    frame = frame[~frame.index.duplicated(keep="last")].sort_index()
    frame = frame.dropna(how="all")
    return frame


def fetch_prices(
    ticker: str,
    start: Optional[str] = None,
    end: Optional[str] = None,
    retries: int = 3,
    pause: float = 1.0,
) -> pd.DataFrame:
    """Fetch daily bars for one ticker, indexed by date.

    Retries transient network failures with a linear backoff; an empty result
    (delisted symbol, weekend-only range) comes back as an empty DataFrame
    rather than an error.
    """
    import yfinance as yf  # imported lazily so the rest of the package works offline

    last_error: Optional[Exception] = None
    for attempt in range(1, max(1, retries) + 1):
        try:
            raw = yf.download(
                ticker,
                start=start,
                end=end,
                interval="1d",
                auto_adjust=False,
                actions=False,
                progress=False,
                threads=False,
            )
            return normalize_frame(raw, ticker)
        except Exception as exc:  # noqa: BLE001 - network/parse errors are all retryable
            last_error = exc
            if attempt < retries:
                time.sleep(pause * attempt)
    raise RuntimeError(f"Failed to download {ticker} after {retries} attempts: {last_error}")
