# pricevol

Pulls daily price history for a list of tickers with [yfinance](https://github.com/ranaroussi/yfinance),
stores it in SQLite, and computes rolling **20-day realized volatility**.

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"        # or: pip install -r requirements-dev.txt
```

## Pick your tickers

Either edit `tickers.txt` (one symbol per line, `#` comments allowed) or pass symbols
on the command line — command-line symbols always win.

```
AAPL
MSFT
SPY
```

## Use

```bash
pricevol run                       # ingest + compute for tickers.txt
pricevol run AAPL MSFT NVDA        # ...or for these symbols
pricevol ingest AAPL --start 2020-01-01   # download only
pricevol vol AAPL --window 20 --csv out/vol.csv
pricevol latest                    # newest volatility per ticker
pricevol status                    # what the database holds
```

Every command takes `--db PATH` (default `data/prices.sqlite`, overridable with
`$PRICEVOL_DB`). `--tickers-file` overrides `tickers.txt` (or `$PRICEVOL_TICKERS`).

Sample output:

```
$ pricevol latest
Latest 20-day annualized realized volatility:
  AAPL     2025-05-07   12.32%
  SPY      2025-05-07   10.14%
```

Re-running is safe: `ingest` resumes from the newest stored date per ticker (re-fetching
that day so a partial bar gets corrected) and writes with an upsert, so nothing duplicates.
Use `--full` to re-download the entire history.

## How volatility is computed

For each ticker, on the adjusted close (falling back to the raw close where the
adjusted series is missing):

1. Daily log returns, `r_t = ln(P_t / P_{t-1})`.
2. Rolling sample standard deviation over the trailing `window` returns (`ddof=1`).
3. Annualized by `sqrt(252)`.

So the value on date *t* uses the 20 returns ending at *t* and needs 21 closes; earlier
dates are warm-up and are not stored. Pass `--window` for a different lookback — results
are keyed by window, so 20- and 60-day series coexist in the same table.

## Schema

```sql
prices(ticker, date, open, high, low, close, adj_close, volume,
       PRIMARY KEY (ticker, date))

realized_vol(ticker, date, window_days, realized_vol,   -- annualized
             PRIMARY KEY (ticker, date, window_days))
```

Dates are ISO-8601 `YYYY-MM-DD` strings, timezone-stripped and normalized to midnight.
Query it like any SQLite file:

```bash
sqlite3 data/prices.sqlite \
  "SELECT ticker, date, ROUND(realized_vol*100, 2) AS vol_pct
     FROM realized_vol WHERE window_days = 20
     ORDER BY date DESC LIMIT 10;"
```

## Layout

```
src/pricevol/
  config.py      defaults, ticker-list parsing
  fetch.py       yfinance download + column normalization
  db.py          SQLite schema, upserts, reads
  volatility.py  log returns and rolling realized volatility
  pipeline.py    ingest / compute / latest orchestration
  cli.py         argparse entry point (`pricevol`)
tests/           pytest suite, no network required
```

## Tests

```bash
pytest
```

The suite stubs the downloader and uses synthetic prices, so it runs offline. Only
`pricevol ingest`/`run` touch the network; a sandbox that blocks `*.yahoo.com` will
report `0 rows / empty response` rather than failing loudly, since yfinance returns an
empty frame instead of raising.
