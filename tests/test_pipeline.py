import numpy as np
import pandas as pd
import pytest

from pricevol import db as db_module
from pricevol import pipeline
from pricevol.cli import main


@pytest.fixture
def fake_fetcher(price_frame):
    """Stand-in for yfinance: serves a fixed history, honouring `start`."""
    history = {
        "AAPL": price_frame(seed=1, n=60),
        "MSFT": price_frame(seed=2, n=60),
    }
    calls = []

    def _fetch(ticker, start=None, end=None, **kwargs):
        calls.append((ticker, start, end))
        if ticker not in history:
            raise RuntimeError(f"no data for {ticker}")
        frame = history[ticker]
        if start:
            frame = frame.loc[frame.index >= pd.Timestamp(start)]
        return frame

    _fetch.calls = calls
    return _fetch


def test_ingest_then_compute(tmp_path, fake_fetcher):
    db = tmp_path / "p.sqlite"
    results = pipeline.ingest(["AAPL", "MSFT"], db_path=db, fetcher=fake_fetcher)
    assert [r.rows for r in results] == [60, 60]
    assert all(r.ok for r in results)

    vol = pipeline.compute(["AAPL", "MSFT"], db_path=db, window=20)
    assert len(vol) == 80
    assert vol["realized_vol"].between(0, 5).all()

    latest = pipeline.latest_volatility(db_path=db, window=20)
    assert len(latest) == 2
    assert set(latest["ticker"]) == {"AAPL", "MSFT"}


def test_ingest_resumes_from_last_stored_date(tmp_path, fake_fetcher):
    db = tmp_path / "p.sqlite"
    pipeline.ingest(["AAPL"], db_path=db, fetcher=fake_fetcher)
    assert fake_fetcher.calls[0][1] == "2015-01-01"  # default cold start

    pipeline.ingest(["AAPL"], db_path=db, fetcher=fake_fetcher)
    conn = db_module.connect(db)
    last = db_module.latest_date(conn, "AAPL")
    conn.close()
    assert fake_fetcher.calls[1][1] == last  # re-fetches the newest bar

    # Re-running does not duplicate rows.
    conn = db_module.connect(db)
    assert len(db_module.read_prices(conn, ["AAPL"])) == 60
    conn.close()


def test_full_refresh_ignores_stored_data(tmp_path, fake_fetcher):
    db = tmp_path / "p.sqlite"
    pipeline.ingest(["AAPL"], db_path=db, fetcher=fake_fetcher)
    pipeline.ingest(["AAPL"], db_path=db, full_refresh=True, fetcher=fake_fetcher)
    assert fake_fetcher.calls[1][1] == "2015-01-01"


def test_one_bad_ticker_does_not_stop_the_rest(tmp_path, fake_fetcher):
    db = tmp_path / "p.sqlite"
    results = pipeline.ingest(["AAPL", "BADTICKER"], db_path=db, fetcher=fake_fetcher)
    ok, bad = results
    assert ok.ok and ok.rows == 60
    assert not bad.ok and "no data" in bad.error


def test_compute_without_store_leaves_table_empty(tmp_path, fake_fetcher):
    db = tmp_path / "p.sqlite"
    pipeline.ingest(["AAPL"], db_path=db, fetcher=fake_fetcher)
    vol = pipeline.compute(["AAPL"], db_path=db, window=20, store=False)
    assert not vol.empty
    assert pipeline.latest_volatility(db_path=db, window=20).empty


def test_compute_needs_more_closes_than_the_window(tmp_path, price_frame):
    db = tmp_path / "p.sqlite"
    short = {"TINY": price_frame(seed=4, n=10)}
    pipeline.ingest(["TINY"], db_path=db, fetcher=lambda t, **kw: short[t])
    assert pipeline.compute(["TINY"], db_path=db, window=20).empty


def test_cli_status_and_vol(tmp_path, fake_fetcher, capsys, monkeypatch):
    db = tmp_path / "p.sqlite"
    pipeline.ingest(["AAPL"], db_path=db, fetcher=fake_fetcher)

    assert main(["status", "--db", str(db)]) == 0
    assert "AAPL" in capsys.readouterr().out

    csv = tmp_path / "vol.csv"
    assert main(["vol", "AAPL", "--db", str(db), "--window", "20", "--csv", str(csv)]) == 0
    out = capsys.readouterr().out
    assert "20-day annualized realized volatility" in out
    assert len(pd.read_csv(csv)) == 40

    assert main(["latest", "AAPL", "--db", str(db)]) == 0
    assert "AAPL" in capsys.readouterr().out


def test_cli_init_creates_schema(tmp_path, capsys):
    db = tmp_path / "new.sqlite"
    assert main(["init", "--db", str(db)]) == 0
    assert db.exists()
    conn = db_module.connect(db)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()
    assert {"prices", "realized_vol"} <= tables
