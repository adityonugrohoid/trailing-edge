"""
Binance Spot WebSocket Kline Fetch Utility

Fetches historical klines in batch mode via WebSocket session.
"""

import asyncio
import json
import time
from datetime import datetime, timezone

import matplotlib.pyplot as plt
import numpy as np
import websockets

from trailingedge.indicators.atr import (
    compute_atr_from_rows,
    rolling_median,
)
from trailingedge.indicators.donchian import compute_donchian_channels

WS_URL = "wss://ws-api.binance.com:443/ws-api/v3"

# --- Test/Chart Config (for __main__ only) ---
SYMBOL = "ETHFDUSD"
INTERVAL = "1m"
TOTAL = 1440  # 24 hours
TIME_ZONE = "0"  # UTC
ATR_PERIOD_FAST = 14
ATR_PERIOD_SLOW = 60
ROLL_WINDOW = 360
DONCHIAN_WINDOW = 20
DONCHIAN_SHIFT = 1


def now():
    """Return current local time for logs, always in YYYY-MM-DD HH:MM:SS."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def fmt_utc_minute(epoch_ms):
    if epoch_ms is None:
        return "live"
    return datetime.fromtimestamp(epoch_ms // 1000, tz=timezone.utc).strftime(
        "%Y-%m-%d %H:%M"
    )


def flatten_klines_to_csv(raw_result, flat_csv_file):
    """
    Save a list of raw klines (from WS fetch) to a flat CSV.
    """
    import pandas as pd

    columns = [
        "open_time",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "close_time",
        "quote_asset_volume",
        "number_of_trades",
        "taker_buy_base_asset_vol",
        "taker_buy_quote_asset_vol",
        "unused",
    ]
    all_klines = []
    for kline in raw_result:
        k_dict = dict(zip(columns, kline, strict=True))
        all_klines.append(k_dict)
    if all_klines:
        df = pd.DataFrame(all_klines)
        df.to_csv(flat_csv_file, index=False)
        print(f"[{now()}] Saved {len(df)} klines to {flat_csv_file}")
    else:
        print(f"[{now()}] No klines found to flatten.")


async def fetch_kline_batch(
    ws,
    symbol: str,
    interval: str = "1m",
    limit: int = 1000,
    start_time: int = None,
    end_time: int = None,
    time_zone: str = "0",  # Use UTC by default!
):
    """
    Fetch batch of historical klines via Binance WS-API v3.
    :param ws: Open, authenticated websocket session
    :param symbol: Symbol, e.g. 'BTCFDUSD'
    :param interval: Interval, e.g. '1m' (default), '1s', '5m'
    :param limit: Number of klines to fetch (max 1000, or up to 1440 for 1d)
    :param start_time: UTC ms (optional)
    :param end_time: UTC ms (optional)
    :param time_zone: String (default "0" for UTC)
    :return: Full WS response dict
    """
    params = {
        "symbol": symbol,
        "interval": interval,
        "limit": limit,
        "timeZone": time_zone,
    }
    if start_time is not None:
        params["startTime"] = int(start_time)
    if end_time is not None:
        params["endTime"] = int(end_time)

    payload = {"id": "fetch_kline", "method": "klines", "params": params}

    print(
        f"[{now()}] Fetching {limit} x {interval} klines for {symbol} "
        f"(start={fmt_utc_minute(start_time)}, end={fmt_utc_minute(end_time)}, TZ={time_zone})"
    )

    await ws.send(json.dumps(payload))
    response = await ws.recv()
    return json.loads(response)


async def fetch_kline_historical_custom_limit(
    ws, symbol, interval="1m", total_candles=1440, time_zone="0"
):
    """
    Fetches up to total_candles klines via Binance WS-API v3, batching as needed.
    Returns: flat list of klines (raw WS API format).
    """

    klines = []
    fetch_limit = min(total_candles, 1000)
    end_time = int(time.time() // 60 * 60 * 1000)
    start_time = end_time - total_candles * 60 * 1000

    # --- First batch
    resp = await fetch_kline_batch(
        ws=ws,
        symbol=symbol,
        interval=interval,
        limit=fetch_limit,
        start_time=start_time,
        time_zone=time_zone,
    )
    klines += resp.get("result", [])

    # --- Additional batch if needed
    remaining = total_candles - fetch_limit
    if remaining > 0 and len(klines) > 0:
        last_close_time = klines[-1][6]  # [6] = close_time in ms
        resp2 = await fetch_kline_batch(
            ws=ws,
            symbol=symbol,
            interval=interval,
            limit=remaining,
            start_time=last_close_time + 1,
            end_time=end_time,
            time_zone=time_zone,
        )
        klines += resp2.get("result", [])

    if len(klines) < total_candles:
        print(
            f"[{now()}] WARNING: Fetched {len(klines)} candles (expected {total_candles})"
        )
    else:
        print(f"[{now()}] Successfully fetched {len(klines)} klines")

    return klines


async def main_fetch_atr_dual_channel_chart():
    async with websockets.connect(WS_URL) as ws:
        from trailingedge.auth.manager import send_session_logon

        await send_session_logon(ws)
        print(
            f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Connected and authenticated for ATR chart fetch."
        )

        klines = await fetch_kline_historical_custom_limit(
            ws, SYMBOL, interval=INTERVAL, total_candles=TOTAL, time_zone=TIME_ZONE
        )
        if not klines or len(klines) < TOTAL:
            print(
                f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] WARNING: Only {len(klines)} klines fetched (expected {TOTAL})."
            )
            return

        closes = np.array([float(row[4]) for row in klines])

        # --- ATR calculations ---
        atr_fast = compute_atr_from_rows(
            klines, period=ATR_PERIOD_FAST, method="wilder"
        )
        atr_slow = compute_atr_from_rows(
            klines, period=ATR_PERIOD_SLOW, method="wilder"
        )

        # --- Clean ATR arrays (None -> np.nan) ---
        atr_fast = np.array(
            [x if x is not None else np.nan for x in atr_fast], dtype=np.float64
        )
        atr_slow = np.array(
            [x if x is not None else np.nan for x in atr_slow], dtype=np.float64
        )

        # Rolling median for fast ATR
        rolling_median_fast = rolling_median(atr_fast, ROLL_WINDOW)

        x = np.arange(len(closes))
        tick_spacing = 60
        ticks = np.arange(0, len(x), tick_spacing)

        # --- FAST ATR Plot (plus slow ATR as threshold) ---
        plt.figure(figsize=(13, 6))
        ax1 = plt.gca()
        color_fast = "tab:red"
        color_slow = "tab:green"
        color_close = "tab:gray"
        color_median = "tab:blue"

        # Fast ATR line
        lns1 = ax1.plot(
            x,
            atr_fast,
            color=color_fast,
            linestyle="--",
            linewidth=1.0,
            alpha=0.5,
            label=f"Fast ATR (EMA {ATR_PERIOD_FAST})",
        )
        # Rolling median (window)
        l_med = ax1.plot(
            x,
            rolling_median_fast,
            color=color_median,
            linestyle="--",
            linewidth=1.0,
            alpha=0.5,
            label=f"{ROLL_WINDOW}c Rolling Median (Fast ATR)",
        )
        # Slow ATR as dynamic threshold
        l_slow = ax1.plot(
            x,
            atr_slow,
            color=color_slow,
            linestyle="--",
            linewidth=1.0,
            alpha=0.5,
            label=f"Slow ATR (Wilder {ATR_PERIOD_SLOW})",
        )
        # Kline close on 2nd axis
        ax2 = ax1.twinx()
        lns2 = ax2.plot(
            x, closes, color=color_close, label="Kline Close", linewidth=2.0, alpha=0.7
        )

        ax1.set_ylabel("ATR Value", color=color_fast)
        ax2.set_ylabel("Close Price", color=color_close)
        ax1.set_title(
            f"{SYMBOL} {INTERVAL} — Fast ATR (EMA {ATR_PERIOD_FAST}) vs Slow ATR (Wilder {ATR_PERIOD_SLOW})"
        )
        # Combine all lines for legend
        lines = lns1 + l_med + l_slow + lns2
        labels = [
            f"Fast ATR (EMA {ATR_PERIOD_FAST})",
            f"{ROLL_WINDOW}c Rolling Median (Fast ATR)",
            f"Slow ATR (Wilder {ATR_PERIOD_SLOW})",
            "Kline Close",
        ]
        ax1.legend(lines, labels, loc="upper left")
        ax1.grid(True, alpha=0.2)
        plt.xlabel("Candle (time increasing →)")
        ax1.set_xticks(ticks)
        ax1.set_xticklabels([str(i) for i in ticks], rotation=45, fontsize=8)
        plt.tight_layout()

        plt.show()


async def main_fetch_donchian_channel_chart():
    async with websockets.connect(WS_URL) as ws:
        from trailingedge.auth.manager import send_session_logon

        await send_session_logon(ws)
        print(
            f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Connected and authenticated for Donchian Channel chart fetch."
        )

        klines = await fetch_kline_historical_custom_limit(
            ws, SYMBOL, interval=INTERVAL, total_candles=TOTAL, time_zone=TIME_ZONE
        )
        if not klines or len(klines) < TOTAL:
            print(
                f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] WARNING: Only {len(klines)} klines fetched (expected {TOTAL})."
            )
            return

        closes = np.array([float(row[4]) for row in klines])

        # --- Donchian Channel Calculation ---
        upper, lower, mid = compute_donchian_channels(
            klines, window=DONCHIAN_WINDOW, shift=DONCHIAN_SHIFT
        )

        x = np.arange(len(closes))
        tick_spacing = 60
        ticks = np.arange(0, len(x), tick_spacing)

        # --- Plot Close + Donchian Channels ---
        plt.figure(figsize=(13, 6))
        ax1 = plt.gca()
        color_upper = "tab:blue"
        color_lower = "tab:orange"
        color_mid = "tab:green"
        color_close = "tab:gray"

        lns1 = ax1.plot(
            x,
            upper,
            color=color_upper,
            linewidth=1.3,
            label=f"Donchian Upper ({DONCHIAN_WINDOW})",
        )
        lns2 = ax1.plot(
            x,
            lower,
            color=color_lower,
            linewidth=1.3,
            label=f"Donchian Lower ({DONCHIAN_WINDOW})",
        )
        lns3 = ax1.plot(
            x,
            mid,
            color=color_mid,
            linewidth=1.0,
            linestyle="--",
            alpha=0.6,
            label="Donchian Mid",
        )
        lns4 = ax1.plot(
            x, closes, color=color_close, linewidth=2.0, alpha=0.7, label="Kline Close"
        )

        ax1.set_ylabel("Price")
        ax1.set_title(
            f"{SYMBOL} {INTERVAL} — Donchian Channel (Window={DONCHIAN_WINDOW})"
        )
        lines = lns1 + lns2 + lns3 + lns4
        labels = [
            f"Donchian Upper ({DONCHIAN_WINDOW})",
            f"Donchian Lower ({DONCHIAN_WINDOW})",
            "Donchian Mid",
            "Kline Close",
        ]
        ax1.legend(lines, labels, loc="upper left")
        ax1.grid(True, alpha=0.2)
        plt.xlabel("Candle (time increasing →)")
        ax1.set_xticks(ticks)
        ax1.set_xticklabels([str(i) for i in ticks], rotation=45, fontsize=8)
        plt.tight_layout()
        plt.show()


if __name__ == "__main__":
    asyncio.run(main_fetch_donchian_channel_chart())
