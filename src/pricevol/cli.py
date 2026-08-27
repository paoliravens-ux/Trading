"""Command line interface: pricevol <command> [tickers] [options]."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional, Sequence

import pandas as pd

from . import db as db_module
from . import pipeline
from .config import DEFAULT_DB_PATH, DEFAULT_TICKERS_FILE, DEFAULT_WINDOW, load_tickers


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("tickers", nargs="*", help="Ticker symbols (default: read tickers.txt).")
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH), help="SQLite file (default: %(default)s).")
    parser.add_argument(
        "--tickers-file",
        default=str(DEFAULT_TICKERS_FILE),
        help="Ticker list used when none are given (default: %(default)s).",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pricevol",
        description="Pull daily prices with yfinance, store them in SQLite, compute realized volatility.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="Create the SQLite database and schema.")
    p_init.add_argument("--db", default=str(DEFAULT_DB_PATH), help="SQLite file (default: %(default)s).")

    p_ingest = sub.add_parser("ingest", help="Download daily bars and store them.")
    _add_common(p_ingest)
    p_ingest.add_argument("--start", help="First date to request (YYYY-MM-DD). Default: resume from stored data.")
    p_ingest.add_argument("--end", help="Last date to request (YYYY-MM-DD, exclusive in yfinance).")
    p_ingest.add_argument("--full", action="store_true", help="Re-download full history instead of resuming.")

    p_vol = sub.add_parser("vol", help="Compute realized volatility from stored prices.")
    _add_common(p_vol)
    p_vol.add_argument("--window", type=int, default=DEFAULT_WINDOW, help="Trading days (default: %(default)s).")
    p_vol.add_argument("--no-store", action="store_true", help="Print without writing to the database.")
    p_vol.add_argument("--tail", type=int, default=10, help="Rows to show per ticker (default: %(default)s).")
    p_vol.add_argument("--csv", help="Also write the full result to this CSV path.")

    p_run = sub.add_parser("run", help="Ingest, then compute volatility (the usual daily job).")
    _add_common(p_run)
    p_run.add_argument("--start", help="First date to request (YYYY-MM-DD).")
    p_run.add_argument("--end", help="Last date to request (YYYY-MM-DD).")
    p_run.add_argument("--full", action="store_true", help="Re-download full history instead of resuming.")
    p_run.add_argument("--window", type=int, default=DEFAULT_WINDOW, help="Trading days (default: %(default)s).")
    p_run.add_argument("--tail", type=int, default=5, help="Rows to show per ticker (default: %(default)s).")
    p_run.add_argument("--csv", help="Also write the full result to this CSV path.")

    p_latest = sub.add_parser("latest", help="Show the most recent stored volatility per ticker.")
    _add_common(p_latest)
    p_latest.add_argument("--window", type=int, default=DEFAULT_WINDOW, help="Trading days (default: %(default)s).")

    p_status = sub.add_parser("status", help="Show what the database holds.")
    p_status.add_argument("--db", default=str(DEFAULT_DB_PATH), help="SQLite file (default: %(default)s).")

    return parser


def _resolve_tickers(args: argparse.Namespace) -> list[str]:
    return load_tickers(args.tickers, Path(args.tickers_file))


def _print_ingest(results) -> int:
    failures = 0
    for res in results:
        if not res.ok:
            failures += 1
            print(f"  {res.ticker:<8} FAILED: {res.error}", file=sys.stderr)
        elif res.rows:
            print(f"  {res.ticker:<8} {res.rows:>6} rows  {res.first_date} → {res.last_date}")
        else:
            # yfinance answers with an empty frame instead of raising when a
            # symbol is unknown or the request never reached Yahoo.
            print(
                f"  {res.ticker:<8}      0 rows  empty response "
                "(already up to date, unknown symbol, or the request was blocked)"
            )
    return failures


def _print_vol(vol: pd.DataFrame, window: int, tail: int) -> None:
    if vol.empty:
        print(f"No volatility rows — need more than {window} daily closes per ticker.")
        return
    shown = vol.copy()
    shown["date"] = shown["date"].dt.strftime("%Y-%m-%d")
    shown["realized_vol"] = shown["realized_vol"].map(lambda v: f"{v:.4f}  ({v * 100:.2f}%)")
    for ticker, group in shown.groupby("ticker"):
        print(f"\n{ticker} — {window}-day annualized realized volatility (last {tail}):")
        for row in group.tail(tail).itertuples(index=False):
            print(f"  {row.date}  {row.realized_vol}")


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "init":
        conn = db_module.connect(args.db)
        try:
            db_module.init_db(conn)
        finally:
            conn.close()
        print(f"Initialized {args.db}")
        return 0

    if args.command == "status":
        conn = db_module.connect(args.db)
        try:
            db_module.init_db(conn)
            rows = conn.execute(
                """
                SELECT ticker, COUNT(*) AS n, MIN(date) AS first, MAX(date) AS last
                FROM prices GROUP BY ticker ORDER BY ticker
                """
            ).fetchall()
        finally:
            conn.close()
        if not rows:
            print(f"{args.db} holds no prices yet — run `pricevol ingest`.")
            return 0
        print(f"{args.db}:")
        for row in rows:
            print(f"  {row['ticker']:<8} {row['n']:>6} bars  {row['first']} → {row['last']}")
        return 0

    tickers = _resolve_tickers(args)

    if args.command in ("ingest", "run"):
        print(f"Ingesting {len(tickers)} ticker(s) into {args.db}")
        results = pipeline.ingest(
            tickers, db_path=args.db, start=args.start, end=args.end, full_refresh=args.full
        )
        failures = _print_ingest(results)
        if args.command == "ingest":
            return 1 if failures else 0

    if args.command in ("vol", "run"):
        window = args.window
        vol = pipeline.compute(
            tickers,
            db_path=args.db,
            window=window,
            store=not getattr(args, "no_store", False),
        )
        _print_vol(vol, window, getattr(args, "tail", 10))
        csv_path = getattr(args, "csv", None)
        if csv_path and not vol.empty:
            Path(csv_path).parent.mkdir(parents=True, exist_ok=True)
            vol.to_csv(csv_path, index=False)
            print(f"\nWrote {len(vol)} rows to {csv_path}")
        return 0

    if args.command == "latest":
        latest = pipeline.latest_volatility(tickers, db_path=args.db, window=args.window)
        if latest.empty:
            print(f"No stored {args.window}-day volatility — run `pricevol vol` first.")
            return 0
        print(f"Latest {args.window}-day annualized realized volatility:")
        for row in latest.itertuples(index=False):
            print(f"  {row.ticker:<8} {pd.Timestamp(row.date):%Y-%m-%d}  {row.realized_vol * 100:6.2f}%")
        return 0

    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
