# pricevol

Pulls daily price history for a list of tickers, stores it in SQLite, and computes rolling
**20-day realized volatility**. Three interchangeable data providers, so a blocked or
rate-limited API is a flag change rather than a rewrite.

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

## Data sources

```bash
pricevol sources          # what's available and whether a key is set
```

| `--source` | Key needed | Notes |
| --- | --- | --- |
| `yfinance` (default) | no | Yahoo Finance. Unofficial, rate limited, and blocked on some networks. |
| `stooq` | no | stooq.com daily CSV. No signup. Split/dividend adjusted, so `adj_close` mirrors `close`. US symbols map to `aapl.us`; pass `bp.uk` or `^spx` verbatim. |
| `alphavantage` | yes | Free key from [alphavantage.co](https://www.alphavantage.co/support/#api-key), exported as `$ALPHAVANTAGE_API_KEY`. Free tier is rate limited to a handful of calls a minute. |

```bash
pricevol run AAPL MSFT --source stooq
PRICEVOL_SOURCE=stooq pricevol run          # or set it once
```

The provider is recorded per bar in `prices.source`, so you can see where each row came
from after switching (`pricevol status` shows it). Adding another provider means writing a
`(ticker, start, end) -> DataFrame` callable in `sources.py` and registering it in `SOURCES`.

## Use

```bash
pricevol run                       # ingest + compute for tickers.txt
pricevol run AAPL MSFT NVDA        # ...or for these symbols
pricevol ingest AAPL --start 2020-01-01 --source stooq   # download only
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
prices(ticker, date, open, high, low, close, adj_close, volume, source,
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
  sources.py     the providers (yfinance / stooq / alphavantage) + registry
  fetch.py       provider dispatch, retries, column normalization
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

The suite stubs the HTTP layer and uses synthetic prices, so it runs offline; the Stooq
and Alpha Vantage parsers are tested against captured response bodies.

Only `pricevol ingest`/`run` touch the network. On a restricted network the `stooq` and
`alphavantage` sources fail loudly with the reason (`Cannot reach stooq.com: ...`), while
`yfinance` reports `0 rows / empty response` instead, because it swallows the error and
returns an empty frame rather than raising.
