"""Price data providers.

Each provider is a callable ``(ticker, start, end) -> DataFrame`` indexed by date
with the columns in :data:`pricevol.db.PRICE_COLUMNS`. Fetching and parsing are
kept apart so the parsers can be tested without network access.
"""

from __future__ import annotations

import csv
import io
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Callable, Dict, Optional

import pandas as pd


USER_AGENT = "pricevol/0.1 (+https://github.com/paoliravens-ux/Trading)"
HTTP_TIMEOUT = 30


class SourceError(RuntimeError):
    """A provider refused the request or returned something unusable."""


def _http_get(url: str, headers: Optional[dict] = None) -> str:
    """GET a URL as text. Honours $HTTPS_PROXY via urllib's default handlers."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})})
    try:
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT) as response:
            return response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        raise SourceError(f"HTTP {exc.code} from {urllib.parse.urlsplit(url).netloc}") from exc
    except urllib.error.URLError as exc:
        raise SourceError(f"Cannot reach {urllib.parse.urlsplit(url).netloc}: {exc.reason}") from exc


def _clip(frame: pd.DataFrame, start: Optional[str], end: Optional[str]) -> pd.DataFrame:
    """Trim to the requested range; providers that ignore date params need this."""
    if frame.empty:
        return frame
    if start:
        frame = frame.loc[frame.index >= pd.Timestamp(start)]
    if end:
        frame = frame.loc[frame.index <= pd.Timestamp(end)]
    return frame


# --------------------------------------------------------------------------- #
# yfinance (Yahoo Finance)
# --------------------------------------------------------------------------- #

def fetch_yfinance(ticker: str, start: Optional[str] = None, end: Optional[str] = None) -> pd.DataFrame:
    """Daily bars from Yahoo Finance. No API key; rate limited and unofficial."""
    import yfinance as yf  # imported lazily so other sources work without it

    from .fetch import normalize_frame

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


# --------------------------------------------------------------------------- #
# Stooq (keyless CSV)
# --------------------------------------------------------------------------- #

def stooq_symbol(ticker: str) -> str:
    """Map a plain ticker onto Stooq's symbol space.

    Stooq suffixes symbols by market, so ``AAPL`` becomes ``aapl.us``. A symbol
    that already carries a suffix (``bp.uk``) or an index prefix (``^spx``) is
    passed through lowercased.
    """
    symbol = ticker.strip().lower()
    if not symbol:
        raise SourceError("Empty ticker")
    if "." in symbol or symbol.startswith("^"):
        return symbol
    return f"{symbol}.us"


def parse_stooq_csv(text: str, ticker: str) -> pd.DataFrame:
    """Parse Stooq's daily CSV (``Date,Open,High,Low,Close,Volume``)."""
    from .fetch import normalize_frame

    head = text.lstrip()[:200].splitlines()[0] if text.strip() else ""
    if not head.lower().startswith("date"):
        # Stooq answers plain text on errors: "No data", "Exceeded the daily hits limit".
        raise SourceError(f"Stooq returned no data for {ticker}: {head or 'empty response'!r}")

    rows = list(csv.DictReader(io.StringIO(text)))
    if not rows:
        return normalize_frame(pd.DataFrame(), ticker)

    frame = pd.DataFrame(rows)
    frame = frame.set_index(pd.to_datetime(frame["Date"], errors="coerce"))
    frame = frame.drop(columns=[c for c in ("Date",) if c in frame.columns])
    for col in frame.columns:
        frame[col] = pd.to_numeric(frame[col], errors="coerce")
    # Stooq's daily history is already adjusted for splits and dividends.
    frame["Adj Close"] = frame.get("Close")
    return normalize_frame(frame, ticker)


def fetch_stooq(ticker: str, start: Optional[str] = None, end: Optional[str] = None) -> pd.DataFrame:
    """Daily bars from stooq.com. No API key or signup required."""
    url = f"https://stooq.com/q/d/l/?s={urllib.parse.quote(stooq_symbol(ticker))}&i=d"
    return _clip(parse_stooq_csv(_http_get(url), ticker), start, end)


# --------------------------------------------------------------------------- #
# Alpha Vantage (free API key)
# --------------------------------------------------------------------------- #

ALPHAVANTAGE_KEY_ENV = "ALPHAVANTAGE_API_KEY"

_AV_FIELDS = {
    "1. open": "open",
    "2. high": "high",
    "3. low": "low",
    "4. close": "close",
    "5. volume": "volume",
    "6. volume": "volume",
    "5. adjusted close": "adj_close",
}


def parse_alphavantage_json(payload: str | dict, ticker: str) -> pd.DataFrame:
    """Parse an Alpha Vantage TIME_SERIES_DAILY response."""
    from .fetch import normalize_frame

    data = json.loads(payload) if isinstance(payload, str) else payload

    for key in ("Error Message", "Note", "Information"):
        if key in data:
            # Rate limits and bad symbols both arrive as HTTP 200 with a message.
            raise SourceError(f"Alpha Vantage ({key}) for {ticker}: {data[key]}")

    series_key = next((k for k in data if k.lower().startswith("time series")), None)
    if series_key is None:
        raise SourceError(f"Alpha Vantage returned no time series for {ticker}: {sorted(data)[:3]}")

    records = {}
    for date, fields in data[series_key].items():
        row = {_AV_FIELDS[k]: v for k, v in fields.items() if k in _AV_FIELDS}
        records[pd.Timestamp(date)] = row
    if not records:
        return normalize_frame(pd.DataFrame(), ticker)

    frame = pd.DataFrame.from_dict(records, orient="index").apply(pd.to_numeric, errors="coerce")
    if "adj_close" not in frame.columns:
        frame["adj_close"] = frame.get("close")
    return normalize_frame(frame, ticker)


def fetch_alphavantage(
    ticker: str,
    start: Optional[str] = None,
    end: Optional[str] = None,
    api_key: Optional[str] = None,
) -> pd.DataFrame:
    """Daily bars from Alpha Vantage. Needs a free key in $ALPHAVANTAGE_API_KEY."""
    key = api_key or os.environ.get(ALPHAVANTAGE_KEY_ENV)
    if not key:
        raise SourceError(
            f"Alpha Vantage needs an API key. Get a free one at "
            f"https://www.alphavantage.co/support/#api-key and export {ALPHAVANTAGE_KEY_ENV}."
        )
    url = (
        "https://www.alphavantage.co/query?function=TIME_SERIES_DAILY"
        f"&symbol={urllib.parse.quote(ticker)}&outputsize=full&apikey={urllib.parse.quote(key)}"
    )
    return _clip(parse_alphavantage_json(_http_get(url), ticker), start, end)


# --------------------------------------------------------------------------- #
# Registry
# --------------------------------------------------------------------------- #

SOURCES: Dict[str, Callable[..., pd.DataFrame]] = {
    "yfinance": fetch_yfinance,
    "stooq": fetch_stooq,
    "alphavantage": fetch_alphavantage,
}

SOURCE_NOTES = {
    "yfinance": "Yahoo Finance, no key, unofficial and rate limited",
    "stooq": "stooq.com CSV, no key or signup, split/dividend adjusted",
    "alphavantage": f"needs a free key in ${ALPHAVANTAGE_KEY_ENV}",
}

DEFAULT_SOURCE = os.environ.get("PRICEVOL_SOURCE", "yfinance")


def get_source(name: str) -> Callable[..., pd.DataFrame]:
    """Look up a provider by name."""
    try:
        return SOURCES[name.strip().lower()]
    except KeyError:
        raise SourceError(
            f"Unknown source {name!r}. Available: {', '.join(sorted(SOURCES))}."
        ) from None
