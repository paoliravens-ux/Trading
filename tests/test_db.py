import pandas as pd

from pricevol import db as db_module


def test_roundtrip_and_idempotent_upsert(tmp_path, price_frame):
    path = tmp_path / "prices.sqlite"
    conn = db_module.connect(path)
    db_module.init_db(conn)

    frame = price_frame(seed=11, n=30)
    assert db_module.upsert_prices(conn, "AAPL", frame) == 30
    assert db_module.upsert_prices(conn, "AAPL", frame) == 30  # replaces, does not duplicate

    stored = db_module.read_prices(conn, ["AAPL"])
    assert len(stored) == 30
    assert stored["close"].iloc[-1] == frame["close"].iloc[-1]
    assert db_module.latest_date(conn, "AAPL") == frame.index[-1].strftime("%Y-%m-%d")
    assert db_module.stored_tickers(conn) == ["AAPL"]
    conn.close()


def test_upsert_overwrites_a_revised_bar(tmp_path, price_frame):
    conn = db_module.connect(tmp_path / "p.sqlite")
    db_module.init_db(conn)
    frame = price_frame(seed=2, n=10)
    db_module.upsert_prices(conn, "MSFT", frame)

    revised = frame.copy()
    revised.loc[revised.index[-1], "close"] = 999.0
    db_module.upsert_prices(conn, "MSFT", revised)

    stored = db_module.read_prices(conn, ["MSFT"])
    assert len(stored) == 10
    assert stored["close"].iloc[-1] == 999.0
    conn.close()


def test_read_prices_filters_by_ticker_and_date(tmp_path, price_frame):
    conn = db_module.connect(tmp_path / "p.sqlite")
    db_module.init_db(conn)
    db_module.upsert_prices(conn, "AAPL", price_frame(seed=1, n=20))
    db_module.upsert_prices(conn, "MSFT", price_frame(seed=2, n=20))

    assert set(db_module.read_prices(conn)["ticker"]) == {"AAPL", "MSFT"}
    assert set(db_module.read_prices(conn, ["MSFT"])["ticker"]) == {"MSFT"}

    windowed = db_module.read_prices(conn, start="2024-01-10", end="2024-01-15")
    assert windowed["date"].min() >= pd.Timestamp("2024-01-10")
    assert windowed["date"].max() <= pd.Timestamp("2024-01-15")
    conn.close()


def test_volatility_table_roundtrip(tmp_path):
    conn = db_module.connect(tmp_path / "p.sqlite")
    db_module.init_db(conn)
    vol = pd.DataFrame(
        {
            "ticker": ["AAPL", "AAPL", "MSFT"],
            "date": pd.to_datetime(["2024-02-01", "2024-02-02", "2024-02-02"]),
            "realized_vol": [0.21, 0.22, 0.35],
        }
    )
    assert db_module.upsert_volatility(conn, vol, window=20) == 3

    stored = db_module.read_volatility(conn, window=20)
    assert len(stored) == 3
    assert set(stored["window_days"]) == {20}

    latest = db_module.read_volatility(conn, window=20, latest_only=True)
    assert len(latest) == 2
    assert latest.loc[latest.ticker == "AAPL", "realized_vol"].iloc[0] == 0.22

    assert db_module.read_volatility(conn, window=30).empty
    conn.close()


def test_latest_date_is_none_for_unknown_ticker(tmp_path):
    conn = db_module.connect(tmp_path / "p.sqlite")
    db_module.init_db(conn)
    assert db_module.latest_date(conn, "NOPE") is None
    conn.close()
