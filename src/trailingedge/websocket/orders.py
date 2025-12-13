"""
Binance Spot order placement utilities via WebSocket API.

Handles limit, market, OCO orders and mass-cancel operations.
"""

import json
import uuid

from trailingedge.auth.manager import get_server_timestamp


async def place_limit_order(ws, symbol, side, price, qty):
    """Place a limit order."""
    payload = {
        "id": "order_place",
        "method": "order.place",
        "params": {
            "symbol": symbol,
            "side": side,
            "type": "LIMIT",
            "timeInForce": "GTC",
            "price": f"{price:.8f}",
            "quantity": f"{qty:.8f}",
            "timestamp": get_server_timestamp(),
        },
    }
    await ws.send(json.dumps(payload))


async def place_market_order(ws, symbol, side, qty):
    """Place a market order."""
    payload = {
        "id": "order_place_market",
        "method": "order.place",
        "params": {
            "symbol": symbol,
            "side": side,
            "type": "MARKET",
            "quantity": f"{qty:.8f}",
            "timestamp": get_server_timestamp(),
        },
    }
    await ws.send(json.dumps(payload))


async def cancel_all_orders(ws, symbol="BTCFDUSD"):
    """Cancel all open orders for a symbol."""
    payload = {
        "id": "cancel_all",
        "method": "openOrders.cancelAll",
        "params": {"symbol": symbol, "timestamp": get_server_timestamp()},
    }
    await ws.send(json.dumps(payload))


async def place_oco_order(ws, symbol, side, quantity, limit_price, stop_price):
    """
    Place an OCO (One Cancels the Other) order with:
        - LIMIT_MAKER at limit_price (TP)
        - STOP_LOSS at stop_price (fallback, market order)
    """
    payload = {
        "id": str(uuid.uuid4()),
        "method": "orderList.place.oco",
        "params": {
            "symbol": symbol,
            "side": side,
            "quantity": float(quantity),
            "aboveType": "LIMIT_MAKER",
            "abovePrice": f"{limit_price:.8f}",
            "aboveTimeInForce": "GTC",
            "belowType": "STOP_LOSS",
            "belowStopPrice": f"{stop_price:.8f}",
            "timestamp": get_server_timestamp(),
        },
    }
    await ws.send(json.dumps(payload))


async def order_replace(ws, symbol, side, price, qty, clientOrderId, origClientOrderId):
    """
    Stateless cancel+replace LIMIT_MAKER order via WebSocket v3.
    This is post-only by design.
    """
    payload = {
        "id": clientOrderId,
        "method": "order.cancelReplace",
        "params": {
            "symbol": symbol,
            "cancelReplaceMode": "ALLOW_FAILURE",
            "cancelOrigClientOrderId": origClientOrderId,
            "side": side,
            "type": "LIMIT_MAKER",
            "price": f"{price:.8f}",
            "quantity": f"{qty:.8f}",
            "newClientOrderId": clientOrderId,
            "timestamp": get_server_timestamp(),
        },
    }
    await ws.send(json.dumps(payload))
