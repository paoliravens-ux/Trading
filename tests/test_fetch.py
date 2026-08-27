import pandas as pd

from pricevol.db import PRICE_COLUMNS
from pricevol.fetch import normalize_frame


def _yahoo_style(index, multi=False, ticker="AAPL"):
    data = {
        "Open": [1.0, 2.0],
        "High": [1.5, 2.5],
        "Low": [0.5, 1.5],
        "Close": [1.2, 2.2],
        "Adj Close": [1.1, 2.1],
        "Volume": [100, 200],
    }
    frame = pd.DataFrame(data, index=index)
    if multi:
        frame.columns = pd.MultiIndex.from_product([frame.columns, [ticker]], names=["Price", "Ticker"])
    return frame


def test_normalize_renames_and_orders_columns():
    idx = pd.to_datetime(["2024-01-02", "2024-01-03"])
    out = normalize_frame(_yahoo_style(idx), "AAPL")
    assert list(out.columns) == PRICE_COLUMNS
    assert out["adj_close"].tolist() == [1.1, 2.1]
    assert out.index.name == "date"


def test_normalize_flattens_multiindex_columns():
    idx = pd.to_datetime(["2024-01-02", "2024-01-03"])
    out = normalize_frame(_yahoo_style(idx, multi=True), "AAPL")
    assert list(out.columns) == PRICE_COLUMNS
    assert out["close"].tolist() == [1.2, 2.2]


def test_normalize_drops_timezone_and_sorts():
    idx = pd.to_datetime(["2024-01-03 09:30", "2024-01-02 09:30"]).tz_localize("America/New_York")
    out = normalize_frame(_yahoo_style(idx), "AAPL")
    assert out.index.tz is None
    assert list(out.index) == [pd.Timestamp("2024-01-02"), pd.Timestamp("2024-01-03")]


def test_normalize_backfills_adj_close_when_auto_adjusted():
    idx = pd.to_datetime(["2024-01-02", "2024-01-03"])
    raw = _yahoo_style(idx).drop(columns=["Adj Close"])
    out = normalize_frame(raw, "AAPL")
    assert out["adj_close"].tolist() == out["close"].tolist()


def test_normalize_empty_frame():
    out = normalize_frame(pd.DataFrame(), "AAPL")
    assert out.empty
    assert list(out.columns) == PRICE_COLUMNS
