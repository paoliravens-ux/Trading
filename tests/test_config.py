import pytest

from pricevol.config import load_tickers, parse_tickers


def test_parse_uppercases_dedupes_and_splits_commas():
    assert parse_tickers([" aapl ", "msft,spy", "AAPL"]) == ["AAPL", "MSFT", "SPY"]


def test_parse_ignores_blanks_and_comments():
    assert parse_tickers(["", "  ", "# comment"]) == []


def test_load_prefers_command_line(tmp_path):
    path = tmp_path / "tickers.txt"
    path.write_text("SPY\n")
    assert load_tickers(["QQQ"], path) == ["QQQ"]


def test_load_reads_file_with_comments(tmp_path):
    path = tmp_path / "tickers.txt"
    path.write_text("# header\nAAPL  # inline note\n\nMSFT\n")
    assert load_tickers([], path) == ["AAPL", "MSFT"]


def test_load_without_tickers_or_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_tickers([], tmp_path / "missing.txt")


def test_load_with_empty_file(tmp_path):
    path = tmp_path / "tickers.txt"
    path.write_text("# nothing here\n")
    with pytest.raises(ValueError):
        load_tickers([], path)
