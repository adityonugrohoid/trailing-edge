import numpy as np

from trailingedge.indicators.atr import compute_atr
from trailingedge.indicators.donchian import compute_donchian_channels


def test_compute_atr_simple():
    """Test ATR calculation with simple predictable data."""
    # Create 5 candles where High-Low is always 10.0
    # klines format: [t, o, h, l, c, v, T, q, n, V, Q, B]
    # We only need h(2), l(3), c(4)
    klines = []
    for _ in range(5):
        # Open=100, High=110, Low=100, Close=105
        # TR = max(110-100, abs(110-prev_close), abs(100-prev_close))
        # For simplicity, let's make TR always 10
        row = [0, "100", "110", "100", "105", 0, 0, 0, 0, 0, 0, 0]
        klines.append(row)

    # With period=2, ATR should eventually stabilize around 10.0
    # Must specify row_format='row' because we are passing lists, not dicts
    atr_series = compute_atr(
        klines, period=2, method="wilder", row_format="row", return_series=True
    )

    # Check that we got a result and the last value is close to 10.0
    assert len(atr_series) == 5
    assert np.isclose(atr_series[-1], 10.0)


def test_compute_donchian_channels():
    """Test Donchian Channel calculation."""
    # Explicit data points for Close prices
    # We use 5 candles.
    # Indices: 0   1   2   3   4
    # Closes:  10, 20, 40, 10, 50
    closes = [10, 20, 40, 10, 50]

    klines = []
    for c in closes:
        # row format: [t, o, h, l, c, ...]
        # We only care about c (index 4)
        row = [0, "0", "0", "0", str(c), 0, 0, 0, 0, 0, 0, 0]
        klines.append(row)

    # Window=3, Shift=1
    # For index 4 (last candle):
    # Shift 1 -> Look at index 3.
    # Window at index 3 (size 3) covers indices [1, 2, 3].
    # Values in window: [20, 40, 10].
    # Max = 40. Min = 10. Mid = 25.

    upper, lower, mid = compute_donchian_channels(
        klines, window=3, shift=1, row_format="row"
    )

    assert upper[-1] == 40.0
    assert lower[-1] == 10.0
    assert mid[-1] == 25.0
