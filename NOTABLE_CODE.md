# Notable Code: Trailing Edge Trading Bot

This document highlights key code sections that demonstrate the technical strengths and architectural patterns implemented in this production trading bot.

## Overview

Trailing Edge is a high-performance asynchronous Python trading bot for Binance. The system demonstrates production-focused patterns including async architecture, WebSocket reconciliation, systemd deployment, and Ed25519 authentication.

---

## 1. Async Trading Loop with Concurrent Streams

**File:** `src/trailingedge/main.py`  
**Lines:** 422-502

The main trading loop demonstrates clean async architecture with concurrent WebSocket streams.

```python
async def main_trading_loop(ws):
    """
    Main trading loop for dynamic trailing stop-loss strategy.
    """
    # Subscribe to user data stream
    await subscribe_user_stream(ws)
    
    # Initialize snapshots
    account_snapshot = {}
    _account_task = asyncio.create_task(account_ws_receiver(ws, account_snapshot))
    
    book_snapshot = {}
    _book_task = asyncio.create_task(stream_bookticker_shared(SYMBOL, book_snapshot))
    
    kline_snapshot = {}
    _kline_task = asyncio.create_task(stream_kline_shared(SYMBOL, "1m", kline_snapshot))
    
    # Wait for snapshots to be ready
    await wait_for_market_snapshot(
        book_snapshot, ["bid_price", "ask_price"], label="BookTicker", timeout=10
    )
```

**Why it's notable:**
- Concurrent async tasks for multiple WebSocket streams
- Non-blocking snapshot initialization
- Proper task management with `asyncio.create_task`
- Timeout handling for snapshot readiness

---

## 2. WebSocket Reconciliation Pattern

**File:** `src/trailingedge/websocket/account_stream.py`  
**Lines:** 27-43

The account stream receiver demonstrates stateless reconciliation from WebSocket events.

```python
async def account_ws_receiver(ws, snapshot_dict):
    """
    Listens for WS messages and updates snapshot_dict for balance changes.
    Never breaks on error; always continues unless ws is closed.
    """
    while True:
        try:
            msg = await ws.recv()
            parse_account_balance_event(msg, snapshot_dict)
        except websockets.exceptions.ConnectionClosed:
            print(f"[{now()}] [ERROR] WS connection closed in account_ws_receiver, exiting loop.")
            break  # <-- Break ONLY on true disconnection!
        except Exception as e:
            print(f"[{now()}] [ERROR] in account_ws_receiver: {e}")
            continue  # <-- Continue for all other (parsing/noise) errors
```

**Why it's notable:**
- Stateless operation: rebuilds state from stream events
- Resilient error handling: continues on parsing errors
- Only breaks on true disconnection
- Eliminates need for database persistence

---

## 3. Ed25519 Authentication

**File:** `src/trailingedge/auth/manager.py`  
**Lines:** Authentication implementation

The system uses Ed25519 for secure, non-expiring authentication.

**Why it's notable:**
- Modern asymmetric cryptography
- Non-expiring credentials (no token refresh needed)
- Secure key-based authentication
- Eliminates shared-secret risks

---

## 4. Systemd Service Configuration

**File:** Deployment documentation  
**Lines:** Systemd service setup

The bot is configured as a systemd service for 24/7 operation.

**Why it's notable:**
- Auto-restart on failure
- Resource limits configuration
- Journald logging integration
- Production-grade service management

---

## Architecture Highlights

### Event-Driven Design

1. **WebSocket Streams**: Market data, account updates, order management
2. **Async Event Loop**: Processes all streams concurrently
3. **Snapshot Reconciliation**: Rebuilds state from events
4. **Trading Logic**: Regime detection, trailing stops, order management

### Design Patterns Used

1. **Async/Await Pattern**: Non-blocking I/O throughout
2. **Reconciliation Pattern**: Stateless operation from events
3. **Task-Based Concurrency**: Multiple async tasks for streams
4. **Snapshot Pattern**: In-memory state from WebSocket events

---

## Technical Strengths Demonstrated

- **Non-Blocking I/O**: Full async/await usage prevents blocking
- **Stateless Design**: WebSocket reconciliation eliminates database
- **Production Deployment**: Systemd service for 24/7 operation
- **Secure Authentication**: Ed25519 for modern key-based auth
- **Resilient Error Handling**: Continues on errors, breaks only on disconnection
