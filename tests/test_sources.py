import json

import pandas as pd
import pytest

from pricevol import sources
from pricevol.db import PRICE_COLUMNS
from pricevol.sources import (
    SourceError,
    get_source,
    parse_alphavantage_json,
    parse_stooq_csv,
    stooq_symbol,
)

STOOQ_CSV = """Date,Open,High,Low,Close,Volume
2024-01-02,187.15,188.44,183.89,185.64,82488700
2024-01-03,184.22,185.88,183.43,184.25,58414500
2024-01-04,182.15,183.09,180.88,181.91,71983600
"""

ALPHAVANTAGE_JSON = json.dumps(
    {
        "Meta Data": {"2. Symbol": "AAPL"},
        "Time Series (Daily)": {
            "2024-01-04": {
                "1. open": "182.1500",
                "2. high": "183.0900",
                "3. low": "180.8800",
                "4. close": "181.9100",
                "5. volume": "71983600",
            },
            "2024-01-02": {
                "1. open": "187.1500",
                "2. high": "188.4400",
                "3. low": "183.8900",
                "4. close": "185.6400",
                "5. volume": "82488700",
            },
        },
    }
)


# --- registry -------------------------------------------------------------- #

def test_registry_exposes_the_three_providers():
    assert set(sources.SOURCES) == {"yfinance", "stooq", "alphavantage"}
    assert get_source("STOOQ") is sources.fetch_stooq


def test_unknown_source_names_the_alternatives():
    with pytest.raises(SourceError, match="stooq"):
        get_source("bloomberg")


# --- stooq ----------------------------------------------------------------- #

@pytest.mark.parametrize(
    "ticker,expected",
    [("AAPL", "aapl.us"), ("aapl", "aapl.us"), ("BP.UK", "bp.uk"), ("^SPX", "^spx")],
)
def test_stooq_symbol_mapping(ticker, expected):
    assert stooq_symbol(ticker) == expected


def test_parse_stooq_csv():
    frame = parse_stooq_csv(STOOQ_CSV, "AAPL")
    assert list(frame.columns) == PRICE_COLUMNS
    assert len(frame) == 3
    assert frame.index[0] == pd.Timestamp("2024-01-02")
    assert frame["close"].iloc[-1] == pytest.approx(181.91)
    # Stooq history is already adjusted, so adj_close mirrors close.
    assert frame["adj_close"].tolist() == frame["close"].tolist()
    assert frame["volume"].iloc[0] == 82488700


def test_parse_stooq_rejects_an_error_body():
    with pytest.raises(SourceError, match="No data"):
        parse_stooq_csv("No data\n", "NOPE")


def test_stooq_fetch_clips_to_range(monkeypatch):
    monkeypatch.setattr(sources, "_http_get", lambda url, headers=None: STOOQ_CSV)
    frame = sources.fetch_stooq("AAPL", start="2024-01-03", end="2024-01-03")
    assert len(frame) == 1
    assert frame.index[0] == pd.Timestamp("2024-01-03")


def test_stooq_fetch_builds_the_expected_url(monkeypatch):
    seen = {}

    def _fake(url, headers=None):
        seen["url"] = url
        return STOOQ_CSV

    monkeypatch.setattr(sources, "_http_get", _fake)
    sources.fetch_stooq("AAPL")
    assert "s=aapl.us" in seen["url"] and "i=d" in seen["url"]


# --- alpha vantage --------------------------------------------------------- #

def test_parse_alphavantage_json():
    frame = parse_alphavantage_json(ALPHAVANTAGE_JSON, "AAPL")
    assert list(frame.columns) == PRICE_COLUMNS
    assert len(frame) == 2
    assert list(frame.index) == [pd.Timestamp("2024-01-02"), pd.Timestamp("2024-01-04")]  # sorted
    assert frame["close"].iloc[0] == pytest.approx(185.64)
    assert frame["adj_close"].iloc[0] == pytest.approx(185.64)


@pytest.mark.parametrize("key", ["Error Message", "Note", "Information"])
def test_parse_alphavantage_surfaces_api_messages(key):
    with pytest.raises(SourceError, match=key):
        parse_alphavantage_json(json.dumps({key: "rate limit reached"}), "AAPL")


def test_alphavantage_without_a_key_says_where_to_get_one(monkeypatch):
    monkeypatch.delenv(sources.ALPHAVANTAGE_KEY_ENV, raising=False)
    with pytest.raises(SourceError, match="alphavantage.co"):
        sources.fetch_alphavantage("AAPL")


def test_alphavantage_uses_the_env_key(monkeypatch):
    seen = {}

    def _fake(url, headers=None):
        seen["url"] = url
        return ALPHAVANTAGE_JSON

    monkeypatch.setenv(sources.ALPHAVANTAGE_KEY_ENV, "TESTKEY")
    monkeypatch.setattr(sources, "_http_get", _fake)
    frame = sources.fetch_alphavantage("AAPL", start="2024-01-03")
    assert "apikey=TESTKEY" in seen["url"]
    assert len(frame) == 1  # clipped to the requested range


# --- dispatch through fetch_prices ----------------------------------------- #

def test_fetch_prices_dispatches_to_the_named_source(monkeypatch):
    from pricevol.fetch import fetch_prices

    monkeypatch.setattr(sources, "_http_get", lambda url, headers=None: STOOQ_CSV)
    frame = fetch_prices("AAPL", source="stooq")
    assert len(frame) == 3


def test_fetch_prices_retries_then_reports_the_source(monkeypatch):
    from pricevol.fetch import fetch_prices

    attempts = []

    def _boom(url, headers=None):
        attempts.append(url)
        raise SourceError("Cannot reach stooq.com: blocked")

    monkeypatch.setattr(sources, "_http_get", _boom)
    with pytest.raises(RuntimeError, match="stooq"):
        fetch_prices("AAPL", source="stooq", retries=2, pause=0)
    assert len(attempts) == 2
