"""SQLite storage for daily bars and computed volatility."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterable, Optional, Sequence

import pandas as pd

SCHEMA_VERSION = 1

PRICE_COLUMNS = ["open", "high", "low", "close", "adj_close", "volume"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS prices (
    ticker    TEXT NOT NULL,
    date      TEXT NOT NULL,          -- ISO-8601 YYYY-MM-DD
    open      REAL,
    high      REAL,
    low       REAL,
    close     REAL,
    adj_close REAL,
    volume    INTEGER,
    PRIMARY KEY (ticker, date)
);

CREATE INDEX IF NOT EXISTS idx_prices_date ON prices (date);

CREATE TABLE IF NOT EXISTS realized_vol (
    ticker       TEXT NOT NULL,
    date         TEXT NOT NULL,
    window_days  INTEGER NOT NULL,
    realized_vol REAL,               -- annualized stdev of daily log returns
    PRIMARY KEY (ticker, date, window_days)
);

CREATE INDEX IF NOT EXISTS idx_realized_vol_date ON realized_vol (date);
"""


def connect(db_path: Path | str) -> sqlite3.Connection:
    """Open (and create if needed) the SQLite database."""
    path = Path(db_path)
    if path.parent and str(path.parent) not in ("", "."):
        path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    """Create the schema. Safe to call on every run."""
    with conn:
        conn.executescript(SCHEMA)
        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")


def _price_rows(ticker: str, frame: pd.DataFrame) -> list[tuple]:
    rows = []
    for date, row in frame.iterrows():
        values = [row.get(col) for col in PRICE_COLUMNS]
        values = [None if pd.isna(v) else v for v in values]
        volume = values[-1]
        values[-1] = None if volume is None else int(volume)
        rows.append((ticker, pd.Timestamp(date).strftime("%Y-%m-%d"), *values))
    return rows


def upsert_prices(conn: sqlite3.Connection, ticker: str, frame: pd.DataFrame) -> int:
    """Insert or replace daily bars for one ticker. Returns rows written.

    ``frame`` is indexed by date and holds the columns in ``PRICE_COLUMNS``;
    re-ingesting an overlapping range simply overwrites the existing rows, so
    the command is safe to re-run.
    """
    if frame is None or frame.empty:
        return 0
    rows = _price_rows(ticker, frame)
    with conn:
        conn.executemany(
            """
            INSERT INTO prices (ticker, date, open, high, low, close, adj_close, volume)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(ticker, date) DO UPDATE SET
                open      = excluded.open,
                high      = excluded.high,
                low       = excluded.low,
                close     = excluded.close,
                adj_close = excluded.adj_close,
                volume    = excluded.volume
            """,
            rows,
        )
    return len(rows)


def upsert_volatility(conn: sqlite3.Connection, frame: pd.DataFrame, window: int) -> int:
    """Persist realized volatility rows (columns: ticker, date, realized_vol)."""
    if frame is None or frame.empty:
        return 0
    rows = [
        (
            row.ticker,
            pd.Timestamp(row.date).strftime("%Y-%m-%d"),
            int(window),
            None if pd.isna(row.realized_vol) else float(row.realized_vol),
        )
        for row in frame.itertuples(index=False)
    ]
    with conn:
        conn.executemany(
            """
            INSERT INTO realized_vol (ticker, date, window_days, realized_vol)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(ticker, date, window_days) DO UPDATE SET
                realized_vol = excluded.realized_vol
            """,
            rows,
        )
    return len(rows)


def _where(clauses: Sequence[str]) -> str:
    return (" WHERE " + " AND ".join(clauses)) if clauses else ""


def read_prices(
    conn: sqlite3.Connection,
    tickers: Optional[Iterable[str]] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
) -> pd.DataFrame:
    """Read stored bars as a DataFrame sorted by ticker then date."""
    clauses, params = [], []
    tickers = list(tickers) if tickers else []
    if tickers:
        clauses.append(f"ticker IN ({','.join('?' * len(tickers))})")
        params.extend(tickers)
    if start:
        clauses.append("date >= ?")
        params.append(start)
    if end:
        clauses.append("date <= ?")
        params.append(end)

    sql = (
        "SELECT ticker, date, open, high, low, close, adj_close, volume FROM prices"
        + _where(clauses)
        + " ORDER BY ticker, date"
    )
    frame = pd.read_sql_query(sql, conn, params=params)
    if not frame.empty:
        frame["date"] = pd.to_datetime(frame["date"])
    return frame


def read_volatility(
    conn: sqlite3.Connection,
    tickers: Optional[Iterable[str]] = None,
    window: Optional[int] = None,
    latest_only: bool = False,
) -> pd.DataFrame:
    """Read stored volatility, optionally only the most recent row per ticker."""
    clauses, params = [], []
    tickers = list(tickers) if tickers else []
    if tickers:
        clauses.append(f"ticker IN ({','.join('?' * len(tickers))})")
        params.extend(tickers)
    if window is not None:
        clauses.append("window_days = ?")
        params.append(int(window))

    sql = (
        "SELECT ticker, date, window_days, realized_vol FROM realized_vol"
        + _where(clauses)
        + " ORDER BY ticker, date"
    )
    frame = pd.read_sql_query(sql, conn, params=params)
    if frame.empty:
        return frame
    frame["date"] = pd.to_datetime(frame["date"])
    frame = frame.dropna(subset=["realized_vol"])
    if latest_only and not frame.empty:
        frame = frame.sort_values("date").groupby(["ticker", "window_days"], as_index=False).tail(1)
        frame = frame.sort_values("ticker").reset_index(drop=True)
    return frame


def latest_date(conn: sqlite3.Connection, ticker: str) -> Optional[str]:
    """Most recent stored date for a ticker, or None if it has no rows."""
    row = conn.execute("SELECT MAX(date) AS d FROM prices WHERE ticker = ?", (ticker,)).fetchone()
    return row["d"] if row and row["d"] else None


def stored_tickers(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute("SELECT DISTINCT ticker FROM prices ORDER BY ticker").fetchall()
    return [r["ticker"] for r in rows]
