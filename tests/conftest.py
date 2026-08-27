import numpy as np
import pandas as pd
import pytest


@pytest.fixture
def price_frame():
    """Deterministic 60-day price series indexed by business day."""

    def _make(seed: int = 0, n: int = 60, start: str = "2024-01-01", level: float = 100.0):
        rng = np.random.default_rng(seed)
        dates = pd.bdate_range(start, periods=n, name="date")
        closes = level * np.exp(np.cumsum(rng.normal(0, 0.01, size=n)))
        return pd.DataFrame(
            {
                "open": closes * 0.99,
                "high": closes * 1.01,
                "low": closes * 0.98,
                "close": closes,
                "adj_close": closes,
                "volume": rng.integers(1_000_000, 5_000_000, size=n),
            },
            index=dates,
        )

    return _make
