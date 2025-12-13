"""
Binance Spot WebSocket streaming utilities for market data.

Provides real-time BookTicker and Kline data streams that update
shared dictionaries in-place for use in trading algorithms.
"""

import asyncio
import json
import time
from datetime import datetime

import websockets

WS_STREAM_URL = "wss://stream.binance.com:9443/ws"
CONNECTION_TIMEOUT = 10  # seconds
MAX_RETRIES = 3
RETRY_DELAYS = [2, 4, 8]  # seconds for exponential backoff


def now() -> str:
    """Return current local time."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


async def stream_bookticker_shared(symbol: str, snapshot_dict: dict):
    """
    Stream real-time bookTicker data for a symbol, updating a shared snapshot dictionary in place.
    Includes retry logic with exponential backoff for connection failures.

    :param symbol: Binance trading symbol, e.g. 'BTCUSDT'
    :param snapshot_dict: Dict to be updated in-place with latest bid/ask/qty/timestamp.
    """
    stream_name = f"{symbol.lower()}@bookTicker"
    url = f"{WS_STREAM_URL}/{stream_name}"
    retry_count = 0

    while retry_count < MAX_RETRIES:
        try:
            print(f"[{now()}] Connecting to Binance stream: {url}")
            async with websockets.connect(
                url, ping_interval=20, close_timeout=CONNECTION_TIMEOUT
            ) as ws:
                print(f"[{now()}] Connected to Binance BookTicker stream.")
                retry_count = 0  # Reset on successful connection

                async for message in ws:
                    data = json.loads(message)
                    bid_price = float(data["b"])
                    bid_qty = float(data["B"])
                    ask_price = float(data["a"])
                    ask_qty = float(data["A"])
                    ts = int(time.time() * 1000)
                    snapshot_dict.update(
                        {
                            "symbol": symbol.upper(),
                            "bid_price": bid_price,
                            "bid_qty": bid_qty,
                            "ask_price": ask_price,
                            "ask_qty": ask_qty,
                            "timestamp": ts,
                        }
                    )
        except websockets.exceptions.ConnectionClosedError as e:
            retry_count += 1
            print(
                f"[{now()}] [ERROR] BookTicker WebSocket connection closed: {e.code} - {e.reason}"
            )
            if retry_count < MAX_RETRIES:
                delay = RETRY_DELAYS[retry_count - 1]
                print(
                    f"[{now()}] Retrying BookTicker connection in {delay}s (attempt {retry_count}/{MAX_RETRIES})..."
                )
                await asyncio.sleep(delay)
            else:
                print(
                    f"[{now()}] [ERROR] BookTicker max retries ({MAX_RETRIES}) reached. Giving up."
                )
                raise
        except asyncio.TimeoutError as e:
            retry_count += 1
            print(f"[{now()}] [ERROR] BookTicker connection timeout: {e}")
            if retry_count < MAX_RETRIES:
                delay = RETRY_DELAYS[retry_count - 1]
                print(
                    f"[{now()}] Retrying BookTicker connection in {delay}s (attempt {retry_count}/{MAX_RETRIES})..."
                )
                await asyncio.sleep(delay)
            else:
                print(
                    f"[{now()}] [ERROR] BookTicker max retries ({MAX_RETRIES}) reached. Giving up."
                )
                raise
        except Exception as e:
            print(
                f"[{now()}] [ERROR] Unexpected error in stream_bookticker_shared: {type(e).__name__}: {e}"
            )
            raise


async def stream_kline_shared(
    symbol: str, interval: str, kline_dict: dict, use_utc8: bool = False
):
    """
    Stream real-time kline (candlestick) data for a symbol and interval.
    Updates kline_dict in-place with the full 'k' sub-dict from Binance WS.
    Includes retry logic with exponential backoff for connection failures.

    :param symbol: Binance trading symbol
    :param interval: Kline interval (e.g., '1m', '5m', '1h')
    :param kline_dict: Dict to be updated in-place with kline data
    :param use_utc8: Whether to use UTC+8 timezone
    """
    if use_utc8:
        stream_name = f"{symbol.lower()}@kline_{interval}@+08:00"
    else:
        stream_name = f"{symbol.lower()}@kline_{interval}"
    url = f"{WS_STREAM_URL}/{stream_name}"
    retry_count = 0

    while retry_count < MAX_RETRIES:
        try:
            print(f"[{now()}] Connecting to Binance kline stream: {url}")
            async with websockets.connect(
                url, ping_interval=20, close_timeout=CONNECTION_TIMEOUT
            ) as ws:
                print(f"[{now()}] Connected to Binance Kline stream.")
                retry_count = 0  # Reset on successful connection

                async for message in ws:
                    data = json.loads(message)
                    k = data.get("k", {})
                    kline_dict.clear()  # Clean out any old keys
                    kline_dict.update(k)  # 1:1 update from live payload
        except websockets.exceptions.ConnectionClosedError as e:
            retry_count += 1
            print(
                f"[{now()}] [ERROR] Kline WebSocket connection closed: {e.code} - {e.reason}"
            )
            if retry_count < MAX_RETRIES:
                delay = RETRY_DELAYS[retry_count - 1]
                print(
                    f"[{now()}] Retrying Kline connection in {delay}s (attempt {retry_count}/{MAX_RETRIES})..."
                )
                await asyncio.sleep(delay)
            else:
                print(
                    f"[{now()}] [ERROR] Kline max retries ({MAX_RETRIES}) reached. Giving up."
                )
                raise
        except asyncio.TimeoutError as e:
            retry_count += 1
            print(f"[{now()}] [ERROR] Kline connection timeout: {e}")
            if retry_count < MAX_RETRIES:
                delay = RETRY_DELAYS[retry_count - 1]
                print(
                    f"[{now()}] Retrying Kline connection in {delay}s (attempt {retry_count}/{MAX_RETRIES})..."
                )
                await asyncio.sleep(delay)
            else:
                print(
                    f"[{now()}] [ERROR] Kline max retries ({MAX_RETRIES}) reached. Giving up."
                )
                raise
        except Exception as e:
            print(
                f"[{now()}] [ERROR] Unexpected error in stream_kline_shared: {type(e).__name__}: {e}"
            )
            raise
