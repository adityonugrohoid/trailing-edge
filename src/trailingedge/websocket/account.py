"""
Binance WebSocket Account Session Utility

Handles account info, commission, open orders, and user data stream.
"""

import asyncio
import csv
import json
from datetime import datetime, timedelta, timezone

from trailingedge.auth.manager import get_server_timestamp, send_session_logon

WS_URL = "wss://ws-api.binance.com:443/ws-api/v3"

# --- Test Config (for __main__ only) ---
SYMBOL = "ETHFDUSD"
OUTPUT_TRADES_CSV = f"output/{SYMBOL.lower()}_mytrades.csv"
UTC_OFFSET = 7  # +7 for Jakarta/Singapore


def now():
    from datetime import datetime

    return datetime.now().strftime("%H:%M:%S.%f")[:-3]


async def fetch_exchange_info(ws, symbol="BTCFDUSD"):
    payload = {
        "id": "exchange_info",
        "method": "exchangeInfo",
        "params": {"symbols": [symbol]},
    }
    await ws.send(json.dumps(payload))
    response = await ws.recv()
    return json.loads(response)


async def fetch_account_status(ws):
    payload = {
        "id": "account_status",
        "method": "account.status",
        "params": {"timestamp": get_server_timestamp(), "omitZeroBalances": True},
    }
    await ws.send(json.dumps(payload))
    response = await ws.recv()
    return json.loads(response)


async def fetch_account_commission(ws, symbol="BTCFDUSD"):
    payload = {
        "id": "account_commission",
        "method": "account.commission",
        "params": {"symbol": symbol, "timestamp": get_server_timestamp()},
    }
    await ws.send(json.dumps(payload))
    response = await ws.recv()
    return json.loads(response)


async def fetch_open_orders(ws, symbol="BTCFDUSD"):
    payload = {
        "id": "open_orders",
        "method": "openOrders.status",
        "params": {"symbol": symbol, "timestamp": get_server_timestamp()},
    }
    await ws.send(json.dumps(payload))
    response = await ws.recv()
    return json.loads(response)


async def subscribe_user_stream(ws):
    payload = {"id": "subscribe_user_stream", "method": "userDataStream.subscribe"}
    await ws.send(json.dumps(payload))
    response = await ws.recv()
    return json.loads(response)


async def fetch_account_trade_history(
    ws,
    symbol,
    start_time=None,
    end_time=None,
    order_id=None,
    from_id=None,
    limit=500,
    recv_window=None,
):
    payload = {
        "id": "account_trade_history",
        "method": "myTrades",
        "params": {
            "symbol": symbol,
            "timestamp": get_server_timestamp(),
            **({"orderId": order_id} if order_id is not None else {}),
            **({"startTime": start_time} if start_time is not None else {}),
            **({"endTime": end_time} if end_time is not None else {}),
            **({"fromId": from_id} if from_id is not None else {}),
            **({"limit": limit} if limit is not None else {}),
            **({"recvWindow": recv_window} if recv_window is not None else {}),
        },
    }
    await ws.send(json.dumps(payload))
    response = await ws.recv()
    return json.loads(response)


if __name__ == "__main__":
    import websockets

    async def main():
        async with websockets.connect(WS_URL) as ws:
            print(
                f"\n[00] Connected to Binance WS-API (Account Session) [SYMBOL={SYMBOL}]"
            )

            # 1. Authenticate via session.logon (Ed25519)
            logon_response = await send_session_logon(ws)
            if logon_response.get("status") != 200:
                print("Logon failed.")
                return
            print(f"\n[01] Logon Response:\n{json.dumps(logon_response, indent=2)}")

            # 2. Fetch Account Status
            print("\n[02] Fetching account status...")
            result_status = await fetch_account_status(ws)
            print(json.dumps(result_status, indent=2))

            # 3. Fetch Account Commission
            print(f"\n[03] Fetching commission ({SYMBOL})...")
            result_comm = await fetch_account_commission(ws, symbol=SYMBOL)
            print(json.dumps(result_comm, indent=2))

            # 4. Fetch Account Trade History (recent fills only, no start/end)
            print(f"\n[04] Fetching account trade history ({SYMBOL}, recent fills)...")
            result_trades = await fetch_account_trade_history(
                ws, symbol=SYMBOL, limit=10
            )
            print(json.dumps(result_trades, indent=2))

            # 5. --- Save to CSV file with readable time_hms ---
            trades = result_trades.get("result", [])
            if trades:
                fieldnames = [
                    "symbol",
                    "id",
                    "orderId",
                    "orderListId",
                    "price",
                    "qty",
                    "quoteQty",
                    "commission",
                    "commissionAsset",
                    "time",
                    "isBuyer",
                    "isMaker",
                    "isBestMatch",
                    "time_hms",
                ]
                with open(OUTPUT_TRADES_CSV, "w", newline="", encoding="utf-8") as f:
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    writer.writeheader()
                    for row in trades:
                        ts = int(row["time"]) // 1000
                        dt = datetime.fromtimestamp(ts, tz=timezone.utc) + timedelta(
                            hours=UTC_OFFSET
                        )
                        row["time_hms"] = dt.strftime("%Y-%m-%d %H:%M:%S")
                        writer.writerow(row)
                print(
                    f"[05] Trade history saved to {OUTPUT_TRADES_CSV} (CSV, ready for Google Sheets)"
                )
            else:
                print("[05] No trade data to save.")

            print("\n[== END OF TEST ==]")

    asyncio.run(main())
