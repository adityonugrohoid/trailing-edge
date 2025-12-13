"""
Donchian Channel Indicator Calculations

Computes Donchian Channels (upper, lower, mid) using rolling windows.
Supports both Binance kline stream dicts and historical row formats.
"""

import numpy as np
import pandas as pd


def compute_donchian_channels(
    klines,
    window=20,
    shift=1,
    row_format="dict",
):
    """
    Compute Donchian Channel (upper, lower, mid) using close price,
    with a rolling window and configurable shift.

    Args:
        klines: List of klines (dicts or rows)
        window: Rolling window size (default 20)
        shift: Number of periods to shift back (default 1)
        row_format: 'dict' for kline stream dicts (field 'c'),
                    'row' for REST/list rows ([4] is close)

    Returns:
        Tuple of (upper, lower, mid) as NumPy arrays
    """
    if row_format == "dict":
        closes = np.array([float(k["c"]) for k in klines])
    elif row_format == "row":
        closes = np.array([float(r[4]) for r in klines])
    else:
        raise ValueError("row_format must be 'dict' or 'row'")

    upper = (
        pd.Series(closes).rolling(window, min_periods=1).max().shift(shift).to_numpy()
    )
    lower = (
        pd.Series(closes).rolling(window, min_periods=1).min().shift(shift).to_numpy()
    )
    mid = (upper + lower) / 2
    return upper, lower, mid
