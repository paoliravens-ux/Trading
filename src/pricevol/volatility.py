"""Realized volatility from daily closes."""

from __future__ import annotations

import numpy as np
import pandas as pd

from .config import DEFAULT_WINDOW, TRADING_DAYS_PER_YEAR


def log_returns(prices: pd.Series) -> pd.Series:
    """Daily log returns; the first observation is NaN by construction."""
    prices = pd.Series(prices).astype("float64")
    prices = prices.where(prices > 0)  # guard against zero/negative prints
    return np.log(prices / prices.shift(1))


def realized_volatility(
    prices: pd.Series,
    window: int = DEFAULT_WINDOW,
    annualize: bool = True,
    ddof: int = 1,
) -> pd.Series:
    """Rolling realized volatility of daily log returns.

    The value at date *t* uses the ``window`` returns ending at *t*, so it needs
    ``window + 1`` closes; earlier dates are NaN. With ``annualize`` the daily
    standard deviation is scaled by sqrt(252).
    """
    if window < 2:
        raise ValueError("window must be at least 2")

    returns = log_returns(prices)
    vol = returns.rolling(window=window, min_periods=window).std(ddof=ddof)
    if annualize:
        vol = vol * np.sqrt(TRADING_DAYS_PER_YEAR)
    return vol


def realized_volatility_table(
    prices: pd.DataFrame,
    window: int = DEFAULT_WINDOW,
    price_col: str = "adj_close",
    annualize: bool = True,
) -> pd.DataFrame:
    """Compute per-ticker realized volatility from a long price frame.

    ``prices`` holds the columns ``ticker``, ``date`` and the chosen price
    column (falling back to ``close`` where the adjusted close is missing).
    Returns a frame of ticker/date/realized_vol with the warm-up rows dropped.
    """
    columns = ["ticker", "date", "realized_vol"]
    if prices is None or prices.empty:
        return pd.DataFrame(columns=columns)

    frame = prices.copy()
    frame["date"] = pd.to_datetime(frame["date"])

    series = frame[price_col] if price_col in frame.columns else pd.Series(np.nan, index=frame.index)
    if "close" in frame.columns:
        series = series.fillna(frame["close"])
    frame["_price"] = pd.to_numeric(series, errors="coerce")

    frame = frame.sort_values(["ticker", "date"])
    frame["realized_vol"] = (
        frame.groupby("ticker", group_keys=False)["_price"]
        .apply(lambda s: realized_volatility(s, window=window, annualize=annualize))
    )

    out = frame.loc[frame["realized_vol"].notna(), columns]
    return out.reset_index(drop=True)
