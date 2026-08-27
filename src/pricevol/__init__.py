"""Pull daily price history, store it in SQLite, compute realized volatility."""

from .config import DEFAULT_DB_PATH, DEFAULT_WINDOW, load_tickers
from .db import connect, init_db, latest_date, read_prices, upsert_prices, upsert_volatility
from .fetch import fetch_prices, normalize_frame
from .sources import SOURCES, SourceError, get_source
from .volatility import log_returns, realized_volatility, realized_volatility_table

__all__ = [
    "DEFAULT_DB_PATH",
    "DEFAULT_WINDOW",
    "load_tickers",
    "connect",
    "init_db",
    "latest_date",
    "read_prices",
    "upsert_prices",
    "upsert_volatility",
    "fetch_prices",
    "normalize_frame",
    "SOURCES",
    "SourceError",
    "get_source",
    "log_returns",
    "realized_volatility",
    "realized_volatility_table",
]

__version__ = "0.1.0"
