import numpy as np
import pandas as pd
import pytest

from pricevol.config import TRADING_DAYS_PER_YEAR
from pricevol.volatility import log_returns, realized_volatility, realized_volatility_table


def test_log_returns_first_value_is_nan():
    prices = pd.Series([100.0, 110.0, 121.0])
    returns = log_returns(prices)
    assert np.isnan(returns.iloc[0])
    assert returns.iloc[1] == pytest.approx(np.log(1.1))
    assert returns.iloc[2] == pytest.approx(np.log(1.1))


def test_constant_growth_has_zero_volatility():
    prices = pd.Series(100.0 * 1.001 ** np.arange(40))
    vol = realized_volatility(prices, window=20)
    assert vol.iloc[-1] == pytest.approx(0.0, abs=1e-12)


def test_warmup_rows_are_nan_and_first_value_lands_on_window_plus_one():
    prices = pd.Series(np.linspace(100, 130, 30) + np.sin(np.arange(30)))
    vol = realized_volatility(prices, window=20)
    # 20 returns are needed, and the first return is NaN, so index 20 is first.
    assert vol.iloc[:20].isna().all()
    assert not np.isnan(vol.iloc[20])


def test_matches_manual_annualized_stdev(price_frame):
    frame = price_frame(seed=7)
    vol = realized_volatility(frame["adj_close"], window=20)

    returns = np.log(frame["adj_close"] / frame["adj_close"].shift(1))
    expected = returns.iloc[-20:].std(ddof=1) * np.sqrt(TRADING_DAYS_PER_YEAR)
    assert vol.iloc[-1] == pytest.approx(expected)


def test_annualize_flag_scales_by_sqrt_252(price_frame):
    prices = price_frame(seed=3)["adj_close"]
    daily = realized_volatility(prices, window=20, annualize=False).iloc[-1]
    annual = realized_volatility(prices, window=20).iloc[-1]
    assert annual == pytest.approx(daily * np.sqrt(TRADING_DAYS_PER_YEAR))


def test_window_must_be_at_least_two():
    with pytest.raises(ValueError):
        realized_volatility(pd.Series([1.0, 2.0, 3.0]), window=1)


def test_table_computes_each_ticker_independently(price_frame):
    aapl = price_frame(seed=1).reset_index().assign(ticker="AAPL")
    msft = price_frame(seed=2).reset_index().assign(ticker="MSFT")
    long = pd.concat([aapl, msft], ignore_index=True)

    table = realized_volatility_table(long, window=20)

    assert set(table["ticker"]) == {"AAPL", "MSFT"}
    assert list(table.columns) == ["ticker", "date", "realized_vol"]
    # 60 closes, 20-day window -> 40 rows per ticker, warm-up dropped.
    assert (table.groupby("ticker").size() == 40).all()
    assert table["realized_vol"].notna().all()

    solo = realized_volatility(price_frame(seed=1)["adj_close"], window=20).dropna()
    assert table.loc[table.ticker == "AAPL", "realized_vol"].to_numpy() == pytest.approx(solo.to_numpy())


def test_table_falls_back_to_close_when_adj_close_missing(price_frame):
    frame = price_frame(seed=5).reset_index().assign(ticker="X")
    frame["adj_close"] = np.nan
    table = realized_volatility_table(frame, window=20)
    assert len(table) == 40


def test_table_on_empty_input():
    table = realized_volatility_table(pd.DataFrame(), window=20)
    assert table.empty
    assert list(table.columns) == ["ticker", "date", "realized_vol"]
