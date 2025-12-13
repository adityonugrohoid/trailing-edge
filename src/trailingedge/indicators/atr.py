"""
ATR (Average True Range) Indicator Calculations

Provides multiple ATR calculation methods including Wilder's smoothing, EMA, and SMA.
Supports both Binance kline stream dicts and historical row formats.
"""

import numpy as np
import pandas as pd


def compute_atr_from_rows(klines, period=14, method="wilder"):
    """
    Compute ATR from historical kline rows.

    Args:
        klines: List of kline rows [open_time, open, high, low, close, ...]
        period: ATR period (default 14)
        method: 'wilder', 'ema', or 'sma'

    Returns:
        List of ATR values with None for warmup period
    """
    closes = [float(row[4]) for row in klines]
    highs = [float(row[2]) for row in klines]
    lows = [float(row[3]) for row in klines]
    if len(closes) < period + 1:
        return []

    tr = []
    for i in range(1, len(closes)):
        tr_val = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        tr.append(tr_val)

    if method == "wilder":
        rma = []
        rma_val = np.mean(tr[:period])
        rma.append(rma_val)
        for val in tr[period:]:
            rma_val = (rma_val * (period - 1) + val) / period
            rma.append(rma_val)
        atr_series = [None] * (period) + rma
    elif method == "ema":
        ema = []
        k = 2 / (period + 1)
        ema_val = np.mean(tr[:period])
        ema.append(ema_val)
        for val in tr[period:]:
            ema_val = val * k + ema_val * (1 - k)
            ema.append(ema_val)
        atr_series = [None] * (period) + ema
    elif method == "sma":
        sma = [np.mean(tr[i - period + 1 : i + 1]) for i in range(period - 1, len(tr))]
        atr_series = [None] * (period - 1) + sma
    else:
        raise ValueError("ATR method must be 'wilder', 'ema', or 'sma'")
    return atr_series


def compute_atr_from_kline_dicts(kline_dicts, period=60):
    """
    Compute ATR from list of kline dictionaries.

    Args:
        kline_dicts: List of Binance kline dicts with 'h', 'l', 'c' fields
        period: ATR period (default 60)

    Returns:
        NumPy array of ATR values
    """
    closes = np.array([float(k["c"]) for k in kline_dicts])
    highs = np.array([float(k["h"]) for k in kline_dicts])
    lows = np.array([float(k["l"]) for k in kline_dicts])
    atr_list = []
    for i in range(period, len(kline_dicts)):
        tr = []
        for j in range(i - period + 1, i + 1):
            high = highs[j]
            low = lows[j]
            prev_close = closes[j - 1] if j > 0 else closes[0]
            tr_val = max(high - low, abs(high - prev_close), abs(low - prev_close))
            tr.append(tr_val)
        atr = sum(tr) / period
        atr_list.append(atr)
    return np.array(atr_list)


def compute_atr_from_window(klines, period=60):
    """
    Compute ATR over the most recent 'period' klines in rolling window.
    Expects each kline dict to use Binance kline stream field names.
    Needs at least period+1 klines (for previous close reference).
    Returns float or None if not enough data.

    Args:
        klines: List of kline dicts with 'h', 'l', 'c' fields
        period: ATR period (default 60)

    Returns:
        Float ATR value or None if insufficient data
    """
    if len(klines) < period + 1:
        return None
    highs = [float(k["h"]) for k in klines[-period - 1 :]]
    lows = [float(k["l"]) for k in klines[-period - 1 :]]
    closes = [float(k["c"]) for k in klines[-period - 1 :]]
    atrs = []
    for i in range(1, period + 1):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        atrs.append(tr)
    if atrs:
        return sum(atrs) / len(atrs)
    return None


def compute_atr(
    klines,
    period=14,
    method="wilder",
    row_format="dict",
    return_series=False,
):
    """
    Compute ATR using Welles Wilder (RMA), EMA, or SMA smoothing.
    Supports Binance kline dicts or historical rows.

    Args:
        klines: List of klines (dicts or rows)
        period: ATR period (default 14)
        method: 'wilder', 'ema', or 'sma'/'simple'
        row_format: 'dict' (kline stream dicts) or 'row' (REST/list rows)
        return_series: If True, returns full series; if False, returns last value

    Returns:
        List of ATR values (if return_series=True) or single float/None
    """
    # Parse prices
    if row_format == "dict":
        highs = [float(k["h"]) for k in klines]
        lows = [float(k["l"]) for k in klines]
        closes = [float(k["c"]) for k in klines]
    elif row_format == "row":
        highs = [float(r[2]) for r in klines]
        lows = [float(r[3]) for r in klines]
        closes = [float(r[4]) for r in klines]
    else:
        raise ValueError("row_format must be 'dict' or 'row'")

    if len(closes) < period + 1:
        return None if not return_series else [None] * len(closes)

    # Calculate True Range (TR)
    tr = []
    for i in range(1, len(closes)):
        tr_val = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        tr.append(tr_val)

    if method == "wilder":
        # Wilder's RMA (smoothed moving average)
        rma = []
        rma_val = np.mean(tr[:period])
        rma += [None] * period  # To align with kline length
        rma.append(rma_val)
        for val in tr[period:]:
            rma_val = (rma_val * (period - 1) + val) / period
            rma.append(rma_val)
        atr_series = rma
    elif method == "ema":
        ema = []
        k = 2 / (period + 1)
        ema_val = np.mean(tr[:period])
        ema += [None] * period
        ema.append(ema_val)
        for val in tr[period:]:
            ema_val = val * k + ema_val * (1 - k)
            ema.append(ema_val)
        atr_series = ema
    elif method in ("sma", "simple"):
        sma = [None] * period
        sma += [np.mean(tr[i - period + 1 : i + 1]) for i in range(period - 1, len(tr))]
        atr_series = sma
    else:
        raise ValueError("method must be 'wilder', 'ema', or 'sma'/'simple'")

    # Return series or just last valid ATR
    if return_series:
        return atr_series
    else:
        for v in reversed(atr_series):
            if v is not None:
                return v
        return None


def rolling_median(arr, window):
    """Compute rolling median with pandas."""
    return pd.Series(arr).rolling(window, min_periods=1).median().to_numpy()


def rolling_mean(arr, window):
    """Compute rolling mean with pandas."""
    return pd.Series(arr).rolling(window, min_periods=1).mean().to_numpy()


def rolling_percentile(arr, window, percentile=80):
    """Compute rolling percentile with pandas."""
    return (
        pd.Series(arr)
        .rolling(window, min_periods=1)
        .apply(lambda x: np.percentile(x, percentile))
        .to_numpy()
    )
