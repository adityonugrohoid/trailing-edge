"""Trailing Edge Trading Bot - Main Entry Point"""

import asyncio
import math
import sys
import threading
from datetime import datetime, timedelta, timezone

import websockets

from trailingedge.auth.manager import send_session_logon

# Load configuration
from trailingedge.config import (
    BASE_ASSET,
    BUFFER,
    DONCHIAN_GAIN_MULTIPLIER,
    DONCHIAN_SHIFT,
    DONCHIAN_WINDOW,
    FEE,
    GAIN_SCALE_FRAC_BASE,
    GAIN_SCALE_FRAC_QUOTE,
    HARD_STOP_THRESHOLD_FRAC,
    KLINE_INTERVAL,
    LOOP_SLEEP_SEC,
    LOT_SIZE,
    MIN_FACTOR,
    MIN_GAIN_TRIGGER_FRAC_BASE,
    MIN_GAIN_TRIGGER_FRAC_QUOTE,
    MIN_NOTIONAL,
    MIN_QTY,
    PRICE_TICK,
    QUOTE_ASSET,
    ROLLING_KLINES_MAXLEN,
    START_FACTOR,
    SYMBOL,
)
from trailingedge.indicators.donchian import compute_donchian_channels
from trailingedge.logging_config import get_logger, setup_logging
from trailingedge.notifications.telegram import broadcast_telegram_message
from trailingedge.websocket.account import subscribe_user_stream
from trailingedge.websocket.account_stream import (
    account_ws_receiver,
    get_balance_from_snapshot,
)
from trailingedge.websocket.market_fetch import fetch_kline_historical_custom_limit
from trailingedge.websocket.market_stream import (
    stream_bookticker_shared,
    stream_kline_shared,
)
from trailingedge.websocket.orders import (
    cancel_all_orders,
    order_replace,
)

# Bot identification
BOT_MARK = "Trailing Edge Bot v1.0"


# --- State ---
class TrailingState:
    def __init__(self):
        # Inventory states
        self.live_bal_free = {BASE_ASSET: 0.0, QUOTE_ASSET: 0.0}
        self.live_bal_locked = {BASE_ASSET: 0.0, QUOTE_ASSET: 0.0}
        self.live_bal_total = {BASE_ASSET: 0.0, QUOTE_ASSET: 0.0}

        # Anchor/highs/regime states
        self.anchor_value = None
        self.high_value = None
        self.current_regime = None
        self.prev_regime = None

        # Order fill flags
        self.maker_exit_armed = False
        self.hard_stop_armed = False

        # --- For hard stop and re-entry logic ---
        self.donchian_gate_active = False
        self.last_donchian_regime = None  # "BASE" or "QUOTE"

        # --- Hotkey flag
        self.manual_exit_triggered = False  # <-- hotkey arm flag

    def reset_for_regime_flip(self, current_value):
        """
        Reset all arming/anchor states after a regime flip or ATR gate exit.

        Called when:
        - Regime changes (BASE → QUOTE or QUOTE → BASE)
        - Donchian gate deactivates and trading resumes

        Resets:
        - anchor_value: Sets new baseline for gain/loss calculations
        - high_value: Resets high water mark for trailing stop
        - maker_exit_armed: Disarms any pending maker exit orders
        - hard_stop_armed: Disarms hard stop loss triggers

        Args:
            current_value: New anchor/high value to set (in value_unit)
        """
        self.anchor_value = current_value
        self.high_value = current_value
        self.maker_exit_armed = False
        self.hard_stop_armed = False


def now():
    """Return current local time for logs, always in YYYY-MM-DD HH:MM:SS."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def clip(value: float | None, step: float | None) -> float:
    """
    Rounds value DOWN to nearest step.
    Always safe for positive value; if value is None or zero, returns zero.
    """
    if value is None or step is None or step == 0:
        return 0.0
    return (int(value / step)) * step


def fmt(value: float | None, precision: int = 8) -> str:
    """
    Format numbers for printing/Telegram/log output (default: 8 decimals).
    Returns 'None' if value is None or not a float/int.
    """
    try:
        if value is None:
            return "None"
        return f"{float(value):.{precision}f}"
    except Exception:
        return str(value)  # fallback for non-numeric input


def fmt_ts(ms: int | None, tz_offset: int = 7) -> str:
    """Converts ms to YYYY-MM-DD HH:MM (UTC+7 default)."""
    if ms is None:
        return "None"
    dt = datetime.fromtimestamp(ms / 1000, tz=timezone.utc) + timedelta(hours=tz_offset)
    return dt.strftime("%Y-%m-%d %H:%M")


def ts_dbg(ts):
    """Debug timestamp formatter (converts ms to readable datetime in UTC+7)."""
    if ts is None:
        return "None"
    return datetime.fromtimestamp(ts / 1000, tz=timezone(timedelta(hours=7))).strftime(
        "%Y-%m-%d %H:%M:%S"
    )


def normalize_historical_kline_row(row, symbol, interval):
    """
    Convert 1 saved historical kline list (from REST/WS batch) into a Binance WS 'k' dict.
    """
    return {
        "t": int(row[0]),  # open time
        "T": int(row[6]),  # close time
        "s": symbol,
        "i": interval,
        "f": 0,  # Unknown in batch; set to 0 or None
        "L": 0,  # Unknown in batch; set to 0 or None
        "o": str(row[1]),
        "c": str(row[4]),
        "h": str(row[2]),
        "l": str(row[3]),
        "v": str(row[5]),
        "n": int(row[8]),
        "x": True,
        "q": str(row[7]),
        "V": str(row[9]),
        "Q": str(row[10]),
        "B": str(row[11]),
    }


def normalize_historical_klines(rows, symbol, interval):
    """
    Converts a list of historical kline rows to list of dicts (as Binance WS 'k' format).
    """
    return [normalize_historical_kline_row(r, symbol, interval) for r in rows]


def debug_print_last_klines(klines, label="Last klines"):
    """
    Debug utility to print last 4 klines with timestamps and close prices.

    Args:
        klines: List of kline dictionaries
        label: Label prefix for the output
    """
    n = 4
    if not klines:
        print(f"{label}: (none)")
        return
    last_few = klines[-n:]
    msg = f"{label}:"
    for k in last_few:
        tstr = datetime.fromtimestamp(
            k["T"] / 1000, tz=timezone(timedelta(hours=7))
        ).strftime("%H:%M:%S")
        msg += f" [{tstr} x={k.get('x')} c={k['c']}]"
    print(msg)


def calc_deep_jumpstart_params(bid, ask):
    """
    Calculate deep out-of-market order parameters for jumpstart balance initialization.

    Creates orders at -10% bid (buy) and +10% ask (sell) to trigger account balance
    snapshot updates without risk of immediate fill. These orders are immediately
    cancelled after being placed.

    Args:
        bid: Current best bid price
        ask: Current best ask price

    Returns:
        Tuple of (deep_buy_price, buy_qty, deep_sell_price, sell_qty)
    """
    deep_buy_price = clip(bid * 0.90, PRICE_TICK)
    deep_sell_price = clip(ask * 1.10, PRICE_TICK)

    min_buy_qty = math.ceil((MIN_NOTIONAL / deep_buy_price) / LOT_SIZE) * LOT_SIZE
    buy_qty = max(MIN_QTY, min_buy_qty)
    min_sell_qty = math.ceil((MIN_NOTIONAL / deep_sell_price) / LOT_SIZE) * LOT_SIZE
    sell_qty = max(MIN_QTY, min_sell_qty)
    return deep_buy_price, buy_qty, deep_sell_price, sell_qty


def detect_regime(
    bal: dict[str, float], bid: float, ask: float, debug: bool = False
) -> str | None:
    """
    Detect trading regime based on tradable inventory.

    Determines whether the bot can trade based on available balances:
    - BASE regime: Holding base asset (e.g., ETH), can sell
    - QUOTE regime: Holding quote asset (e.g., FDUSD), can buy
    - None: Insufficient funds to trade in either direction

    Args:
        bal: Dictionary with asset balances {BASE_ASSET: float, QUOTE_ASSET: float}
        bid: Current bid price
        ask: Current ask price
        debug: If True, returns (None, reason_str) when regime is None

    Returns:
        'BASE' if can sell base asset
        'QUOTE' if can buy base asset with quote
        None if insufficient funds (or tuple with reason if debug=True)

    Conditions for BASE:
        - base_amt >= MIN_QTY AND
        - base_amt * bid >= MIN_NOTIONAL

    Conditions for QUOTE:
        - quote_amt >= MIN_NOTIONAL AND
        - quote_amt / ask (clipped to LOT_SIZE) >= MIN_QTY
    """
    base_amt = float(bal[BASE_ASSET])
    quote_amt = float(bal[QUOTE_ASSET])
    can_sell_base = base_amt >= MIN_QTY and (base_amt * bid) >= MIN_NOTIONAL
    can_buy_base = quote_amt >= MIN_NOTIONAL and (
        clip(quote_amt / ask, LOT_SIZE) >= MIN_QTY
    )
    if can_sell_base:
        return "BASE"
    elif can_buy_base:
        return "QUOTE"
    else:
        if debug:
            reason = []
            if base_amt < MIN_QTY:
                reason.append("Base asset below min qty")
            if (base_amt * bid) < MIN_NOTIONAL:
                reason.append("Base notional below min")
            if quote_amt < MIN_NOTIONAL:
                reason.append("Quote asset below min notional")
            if clip(quote_amt / ask, LOT_SIZE) < MIN_QTY:
                reason.append("Quote to base min qty fail")
            return None, "; ".join(reason)
        return None


def value_drop_frac(current_value: float | None, anchor: float | None) -> float:
    """Calculate fractional drop from anchor value."""
    if anchor and current_value is not None:
        return (anchor - current_value) / anchor
    return 0


async def wait_for_market_snapshot(
    snapshot, required_keys, label="", timeout=10.0, poll=0.05
):
    """
    Wait until all required_keys exist and are non-None in snapshot dict.
    Keys are assumed flat strings, e.g. ["bid_price", "ask_price"].
    """
    waited = 0
    while True:
        ready = all(snapshot.get(k) is not None for k in required_keys)
        if ready:
            print(f"[{now()}] {label} snapshot ready.")
            return
        await asyncio.sleep(poll)
        waited += poll
        if waited >= timeout:
            raise TimeoutError(
                f"{label} snapshot did not initialize in {timeout} seconds! Required: {required_keys}"
            )


async def wait_for_account_snapshot(
    snapshot, required_key_paths, label="", timeout=10.0, poll=0.05
):
    """
    Wait until all nested key paths exist and are non-None in snapshot dict.
    required_key_paths: list of tuples, e.g. [("BTC", "free"), ("BTC", "locked"), ("BTC", "total")]
    """

    def exists(snap, key_path):
        d = snap
        for k in key_path:
            if d is None or k not in d:
                return False
            d = d[k]
        return d is not None

    waited = 0
    while True:
        ready = all(exists(snapshot, kp) for kp in required_key_paths)
        if ready:
            print(f"[{now()}] {label} snapshot ready.")
            return
        await asyncio.sleep(poll)
        waited += poll
        if waited >= timeout:
            raise TimeoutError(
                f"{label} snapshot did not initialize in {timeout} seconds! Required: {required_key_paths}"
            )


async def cancel_tasks(tasks):
    """
    Cancel all asyncio tasks and wait for them to complete.

    Args:
        tasks: List of asyncio.Task objects to cancel
    """
    for t in tasks:
        t.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)


async def prompt_continue(tasks, msg="Continue? (Y/N): "):
    """
    Prompt user for confirmation before continuing.

    Provides a safety check point where user can review settings and abort if needed.
    On 'N' response, cancels all running tasks and exits gracefully.

    Uses asyncio-compatible input handling to avoid blocking the event loop.

    Args:
        tasks: List of asyncio.Task objects to cancel if user declines
        msg: Prompt message to display

    Returns:
        True if user confirms (Y), exits program if user declines (N)
    """
    while True:
        # Use asyncio to run the blocking input in a thread executor
        loop = asyncio.get_event_loop()
        resp = await loop.run_in_executor(None, lambda: input(msg).strip().lower())

        if resp == "y":
            return True
        elif resp == "n":
            print("Exiting by user request.")
            await cancel_tasks(tasks)
            sys.exit(0)
        else:
            print("Please enter Y or N.")


def install_hotkey_listener(state, hotkey="x"):
    """
    Cross-platform non-blocking stdin listener. Type the hotkey + Enter to arm exit.
    Works on both Windows and POSIX systems using threading.
    Example: press 'x' then Enter.

    Automatically disabled when running as a systemd service (no TTY).
    """
    # Check if we have a real terminal (not running as systemd service)
    if not sys.stdin.isatty():
        print(f"[{now()}] Hotkey listener disabled (no TTY - running as service)")
        return

    def stdin_reader_thread():
        """Background thread to read stdin continuously."""
        while True:
            try:
                line = sys.stdin.readline().strip().lower()
                if line == hotkey:
                    state.manual_exit_triggered = True
                    print(f"[{now()}] [HOTKEY] Manual maker-exit ARMED by '{hotkey}'")
            except Exception as e:
                print(f"[{now()}] [HOTKEY] stdin read error: {e}")
                break

    # Start daemon thread for stdin reading (works on all platforms)
    thread = threading.Thread(target=stdin_reader_thread, daemon=True)
    thread.start()
    print(
        f"[{now()}] Hotkey listener active (cross-platform). Type '{hotkey}' then Enter to arm exit."
    )


# --- Main Trading Loop ---
async def main_trading_loop(ws):
    """
    Main trading loop for dynamic trailing stop-loss strategy.

    Flow:
    1. Initialize: Fetch historical klines, compute baseline Donchian channels
    2. Setup: Subscribe to user data stream, start market data streams (BookTicker, Kline)
    3. Jumpstart: Place deep orders to trigger balance snapshot updates
    4. Loop: Continuous trading logic
       a. Update balances and market data from snapshots
       b. Maintain rolling kline window for indicator calculations
       c. Compute Donchian channels for gating logic
       d. Detect regime (BASE holding vs QUOTE holding)
       e. Calculate dynamic min gain threshold (max of: static fraction, fee+buffer, Donchian-based)
       f. Handle regime flips: reset anchor/high, send Telegram notification
       g. Update high water mark and calculate trailing callback
       h. Hard stop logic: Donchian gate activation on threshold breach
       i. Persistent maker exit: Place limit orders on callback trigger or manual hotkey
       j. Print diagnostics and sleep

    Key Features:
    - Regime detection: Automatically switches between BASE (inventory) and QUOTE (cash) modes
    - Trailing Take Profit: Dynamic callback based on exponential decay from start to min factor
    - Donchian gating: Blocks re-entry after hard stop until price crosses mid-channel
    - Manual override: Hotkey support for operator intervention

    Args:
        ws: Authenticated WebSocket connection to Binance API
    """
    # === SECTION: Fetch, Normalize Historical Klines, and Baseline ATR ===
    historical_klines = await fetch_kline_historical_custom_limit(
        ws,
        SYMBOL,
        interval=KLINE_INTERVAL,
        total_candles=ROLLING_KLINES_MAXLEN,
        time_zone="0",
    )

    normalized_hist_klines = normalize_historical_klines(
        historical_klines, SYMBOL, KLINE_INTERVAL
    )
    print(
        f"[{now()}] Normalized {len(normalized_hist_klines)} historical klines to stream-compatible dict."
    )

    start_kline = normalized_hist_klines[0]
    end_kline = normalized_hist_klines[-1]
    print(
        f"[{now()}] Start: {fmt_ts(start_kline['t'])} | End: {fmt_ts(end_kline['T'])}"
    )

    # At startup: fill with normalized historical klines (already aligned to stream structure)
    rolling_klines = list(
        normalized_hist_klines[-ROLLING_KLINES_MAXLEN:]
    )  # Defensive slice
    print(f"[{now()}] Rolling klines initialized with {len(rolling_klines)} entries.")

    # --- Baseline Donchian calculation (on historical, normalized klines) ---
    donchian_upper, donchian_lower, donchian_mid = compute_donchian_channels(
        normalized_hist_klines,
        window=DONCHIAN_WINDOW,
        shift=DONCHIAN_SHIFT,
        row_format="dict",  # normalized_hist_klines is a list of dicts
    )
    print(
        f"[{now()}] Baseline Donchian: window={DONCHIAN_WINDOW}, shift={DONCHIAN_SHIFT} | "
        f"Last upper={donchian_upper[-1]:.4f}, lower={donchian_lower[-1]:.4f}, mid={donchian_mid[-1]:.4f}"
    )

    # === SECTION: Subscribe, Start Streams, and Market Data Snapshot Readiness ===
    await subscribe_user_stream(ws)
    print(f"[{now()}] userDataStream subscribed.")

    account_snapshot = {}
    _account_task = asyncio.create_task(account_ws_receiver(ws, account_snapshot))

    book_snapshot = {}
    _book_task = asyncio.create_task(stream_bookticker_shared(SYMBOL, book_snapshot))

    kline_snapshot = {}
    _kline_task = asyncio.create_task(stream_kline_shared(SYMBOL, "1m", kline_snapshot))

    try:
        await wait_for_market_snapshot(
            book_snapshot, ["bid_price", "ask_price"], label="BookTicker", timeout=10
        )
        print(
            f"[{now()}] Bid={book_snapshot['bid_price']} | Ask={book_snapshot['ask_price']}"
        )
        bid = book_snapshot["bid_price"]
        ask = book_snapshot["ask_price"]

        await wait_for_market_snapshot(
            kline_snapshot,
            ["o", "c"],  # Official 'k' keys: open, close (both as strings)
            label="Kline",
            timeout=10,
        )
        print(f"[{now()}] Open={kline_snapshot['o']} | Close={kline_snapshot['c']}")
        print(f"[{now()}] Live kline_snapshot raw: {kline_snapshot}")

    except TimeoutError as e:
        print(f"[{now()}] [ERROR] {e}")
        sys.exit(1)

    # === SECTION: Jumpstart Orders and Account Balance Snapshot Readiness ===
    deep_buy_price, buy_qty, deep_sell_price, sell_qty = calc_deep_jumpstart_params(
        bid, ask
    )
    print(
        f"[{now()}] Deep Buy Price: {deep_buy_price:.2f} | Deep Sell Price: {deep_sell_price:.2f}"
    )
    print(
        f"[{now()}] Minimum Buy Qty: {buy_qty:.8f} {BASE_ASSET} | Minimum Sell Qty: {sell_qty:.8f} {BASE_ASSET}"
    )

    client_id_buy = "JUMPSTART_BUY"
    client_id_sell = "JUMPSTART_SELL"

    await order_replace(
        ws,
        SYMBOL,
        "BUY",
        deep_buy_price,
        buy_qty,
        clientOrderId=client_id_buy,
        origClientOrderId=client_id_buy,
    )
    await asyncio.sleep(1)

    await order_replace(
        ws,
        SYMBOL,
        "SELL",
        deep_sell_price,
        sell_qty,
        clientOrderId=client_id_sell,
        origClientOrderId=client_id_sell,
    )
    await asyncio.sleep(1)

    await cancel_all_orders(ws, symbol=SYMBOL)
    await asyncio.sleep(1)

    print(
        f"[{now()}] Sent both deep post-only limit-makers and openOrders.cancelAll for jumpstart balance push."
    )

    try:
        await wait_for_account_snapshot(
            account_snapshot,
            [
                (BASE_ASSET, "free"),
                (BASE_ASSET, "locked"),
                (BASE_ASSET, "total"),
                (QUOTE_ASSET, "free"),
                (QUOTE_ASSET, "locked"),
                (QUOTE_ASSET, "total"),
            ],
            label="Account",
            timeout=15,
        )
        # Get reduced snapshot and print it (uses your existing helper)
        reduced = get_balance_from_snapshot(account_snapshot, BASE_ASSET, QUOTE_ASSET)
        print(f"[{now()}] Balances: {reduced}")

    except TimeoutError as e:
        print(f"[{now()}] [ERROR] {e}")
        sys.exit(1)

    # --- State ---
    state = TrailingState()

    # --- Hotkey ---
    install_hotkey_listener(state, hotkey="x")  # choose your hotkey

    # --- Start Main Trading Loop ---
    print(f"\n[{now()}] All systems ready. Starting main trading loop...")
    print(f"[{now()}] Press Ctrl-C to stop the bot gracefully.\n")

    # --- Main regime/trailing logic loop ---
    while True:
        # ====================================================================================================================================================
        # 1. Account & market data snapshot
        # ====================================================================================================================================================

        # --- Account & Market Data ---
        balances = get_balance_from_snapshot(account_snapshot, BASE_ASSET, QUOTE_ASSET)
        state.live_bal_free = balances["free"]
        state.live_bal_locked = balances["locked"]
        state.live_bal_total = balances["total"]
        # print(f"[{now()}] DEBUG Live Balances | Free: {state.live_bal_free} | Locked: {state.live_bal_locked} | Total: {state.live_bal_total}")

        bid = book_snapshot.get("bid_price")
        ask = book_snapshot.get("ask_price")
        if bid is None or ask is None:
            await asyncio.sleep(0.1)
            continue
        # print(f"[{now()}] DEBUG BookTicker Bid: {bid} | Ask: {ask}")

        # ====================================================================================================================================================
        # 2. Rolling kline window management
        # ====================================================================================================================================================

        # --- Rolling Kline Window Management ---
        current_kline = dict(kline_snapshot)

        if not rolling_klines:
            rolling_klines.append(current_kline)
            # print(f"[{now()}] (INIT) Rolling klines: appended kline T={ts_dbg(current_kline['T'])} (len={len(rolling_klines)})")
            # debug_print_last_klines(rolling_klines)
        else:
            last_kline = rolling_klines[-1]
            if current_kline["T"] > last_kline["T"]:
                # --- ALWAYS pop if at window maxlen before appending new forming kline ---
                if len(rolling_klines) >= ROLLING_KLINES_MAXLEN:
                    _ = rolling_klines.pop(0)
                    # print(f"[{now()}] (POP) Popped oldest kline T={ts_dbg(popped['T'])} (len={len(rolling_klines)})")
                rolling_klines.append(current_kline)
                # print(f"[{now()}] (ADVANCE) Appended new kline T={ts_dbg(current_kline['T'])} (x={current_kline.get('x')}) (len={len(rolling_klines)})")
                # debug_print_last_klines(rolling_klines)
            else:
                rolling_klines[-1] = current_kline  # Update forming kline in place
                # print(f"[{now()}] (UPDATE) Updated forming kline T={ts_dbg(current_kline['T'])} (x={current_kline.get('x')}) (len={len(rolling_klines)})")
                # debug_print_last_klines(rolling_klines)

        # ====================================================================================================================================================
        # 3. Donchian calculation & gating
        # ====================================================================================================================================================

        # --- Donchian channel (live, from merged kline stream) ---
        donchian_upper, donchian_lower, donchian_mid = compute_donchian_channels(
            rolling_klines,
            window=DONCHIAN_WINDOW,
            shift=DONCHIAN_SHIFT,
            row_format="dict",  # rolling_klines is a list of dicts (Binance stream format)
        )

        last_upper = donchian_upper[-1]
        last_lower = donchian_lower[-1]
        last_mid = donchian_mid[-1]
        donchian_width = last_upper - last_lower

        # print(f"[{now()}] Donchian: upper={last_upper:.4f}, lower={last_lower:.4f}, mid={last_mid:.4f} (window={DONCHIAN_WINDOW}, shift={DONCHIAN_SHIFT})")

        # --- Donchian Gating Logic ---
        last_close = float(current_kline["c"])
        if not hasattr(state, "donchian_gate_active"):
            state.donchian_gate_active = False
            state.last_donchian_regime = None

        # 1. Detect hard stop triggering (e.g., asset value drops threshold)
        #    (assume you set state.donchian_gate_active = True and state.last_donchian_regime = regime when hard stop fires)
        # 2. BLOCK trading if Donchian gate is active (except for required exit/settlement actions)

        if state.donchian_gate_active:
            # Wait for the appropriate mid-cross to reset
            if state.last_donchian_regime == "BASE":
                # For hard stop SELL: require close > mid for re-entry
                if last_close > last_mid:
                    # Calculate current value for re-anchoring
                    reset_value = state.live_bal_total[BASE_ASSET] * bid
                    # print(f"[{now()}] Donchian gate reset: close {last_close:.4f} > mid {last_mid:.4f} (BASE exit)")
                    logger = get_logger()
                    logger.info(
                        f"Donchian gate RESET: close {last_close:.4f} > mid {last_mid:.4f} (BASE exit), re-anchoring to {reset_value:.4f}"
                    )
                    state.donchian_gate_active = False
                    state.last_donchian_regime = None
                    # re-anchor here!
                    state.anchor_value = reset_value
                    state.high_value = reset_value
            elif state.last_donchian_regime == "QUOTE":
                # For hard stop BUY: require close < mid for re-entry
                if last_close < last_mid:
                    # Calculate current value for re-anchoring
                    reset_value = (
                        (state.live_bal_total[QUOTE_ASSET] / ask) if ask > 0 else 0
                    )
                    # print(f"[{now()}] Donchian gate reset: close {last_close:.4f} < mid {last_mid:.4f} (QUOTE exit)")
                    logger = get_logger()
                    logger.info(
                        f"Donchian gate RESET: close {last_close:.4f} < mid {last_mid:.4f} (QUOTE exit), re-anchoring to {reset_value:.4f}"
                    )
                    state.donchian_gate_active = False
                    state.last_donchian_regime = None
                    # re-anchor here!
                    state.anchor_value = reset_value
                    state.high_value = reset_value

            # While in Donchian gate, skip order/trading logic

        skip_trading = state.donchian_gate_active

        # ====================================================================================================================================================
        # 4. Regime detection & value calculation (regime, current_value, anchor, etc.)
        # ====================================================================================================================================================

        # --- Regime Detection & Value Calculation ---
        prev_regime = state.current_regime
        regime = detect_regime(state.live_bal_total, bid, ask)
        state.current_regime = regime

        if regime == "BASE":
            current_value = state.live_bal_total[BASE_ASSET] * bid
            value_unit = QUOTE_ASSET
            gain_scale_frac = GAIN_SCALE_FRAC_BASE
        elif regime == "QUOTE":
            current_value = (state.live_bal_total[QUOTE_ASSET] / ask) if ask > 0 else 0
            value_unit = BASE_ASSET
            gain_scale_frac = GAIN_SCALE_FRAC_QUOTE
        else:
            await asyncio.sleep(0.1)
            continue

        # --- Always set anchor immediately after current_value ---
        anchor = state.anchor_value if state.anchor_value is not None else current_value

        # ====================================================================================================================================================
        # 5. Min gain threshold calculations (fixed + Donchian + max())
        # ====================================================================================================================================================

        # --- Min Gain Trigger by Static Fraction ---
        min_gain_trigger_frac = (
            MIN_GAIN_TRIGGER_FRAC_BASE
            if regime == "BASE"
            else MIN_GAIN_TRIGGER_FRAC_QUOTE
        )
        min_gain_static = anchor * min_gain_trigger_frac

        # --- Min Gain Trigger by Fee + Buffer ---
        min_gain_fee_buffer = anchor * (FEE + BUFFER)

        # --- Min Gain Trigger by Donchian Channel Width ---
        if regime == "BASE":
            # Profit required equals: (ETH held) × (price range in FDUSD) × multiplier
            min_gain_donchian = (
                state.live_bal_total[BASE_ASSET]
                * donchian_width
                * DONCHIAN_GAIN_MULTIPLIER
            )
        elif regime == "QUOTE":
            # Profit required equals: (FDUSD held) × (price range) × multiplier, converted to ETH via the anchored ask and new ask.
            # This gives the exact incremental ETH gained if ask drops by donchian_width.
            if ask > 0 and (ask - donchian_width) > 0:
                min_gain_donchian = (
                    state.live_bal_total[QUOTE_ASSET]
                    * donchian_width
                    * DONCHIAN_GAIN_MULTIPLIER
                ) / (ask * (ask - donchian_width))
            else:
                min_gain_donchian = 0.0
        else:
            min_gain_donchian = 0.0

        # --- Choose the strictest (highest) minimum gain requirement ---
        min_gain_for_trigger = max(
            min_gain_static, min_gain_fee_buffer, min_gain_donchian
        )

        # ====================================================================================================================================================
        # 6. Regime flip block (reset_for_regime_flip, compounding, telegram, etc.)
        # ====================================================================================================================================================

        # --- Regime Flip Handling ---
        if regime != prev_regime and regime is not None:
            state.reset_for_regime_flip(current_value)
            # print(f"[{now()}] Regime flip: {prev_regime} → {regime} | Anchor/high reset to {fmt(current_value)}")
            logger = get_logger()
            logger.info(
                f"Regime flip: {prev_regime} → {regime} | Anchor/high reset to {fmt(current_value)} | Symbol: {SYMBOL}"
            )

            # --- Compose comprehensive Telegram regime flip message ---
            def fmt_bal(asset):
                snap = account_snapshot.get(asset, {})
                return (
                    f"{asset}\n"
                    f"  Free:   {snap.get('free', 0.0):.8f}\n"
                    f"  Locked: {snap.get('locked', 0.0):.8f}"
                )

            price_lines = f"Bid: {bid:.2f}   Ask: {ask:.2f}\n"
            donchian_lines = (
                f"Donchian Channel (W={DONCHIAN_WINDOW}, Shift={DONCHIAN_SHIFT}):\n"
                f"  Upper: {last_upper:.4f}\n"
                f"  Lower: {last_lower:.4f}\n"
                f"  Mid:   {last_mid:.4f}\n"
                f"  Width: {donchian_width:.4f}\n"
                f"Dynamic Min Gain: {min_gain_for_trigger:.8f} "
                f"({value_unit}) [Donchian x {DONCHIAN_GAIN_MULTIPLIER:.2f}]\n"
                f"Donchian Gate State: {'ACTIVE' if state.donchian_gate_active else 'INACTIVE'}"
            )

            msg_lines = [
                f"{'🟥' if regime == 'BASE' else '🟩' if regime == 'QUOTE' else ''} Regime Flip: {regime}",
                f"Symbol: {SYMBOL}",
                f"Time: {now()}",
                f"Anchor: {state.anchor_value:.8f} {value_unit}",
                price_lines,
                "All Balances:",
                f"```{fmt_bal(BASE_ASSET)}```",
                f"```{fmt_bal(QUOTE_ASSET)}```",
                "",
                donchian_lines,
                "",
            ]

            msg = "\n".join(msg_lines)
            broadcast_telegram_message(msg)

        # ====================================================================================================================================================
        # 7. Update anchor/high/gain/drawdown/callback
        # ====================================================================================================================================================

        # --- Update Anchor, High, Gain/Drawdown, Callback Factor ---
        anchor = state.anchor_value if state.anchor_value is not None else current_value
        high = state.high_value if state.high_value is not None else anchor

        gain = high - anchor
        drawdown = high - current_value

        gain_scale = anchor * gain_scale_frac
        callback_factor = max(MIN_FACTOR, START_FACTOR / (1 + gain / gain_scale))
        callback = gain * callback_factor

        # --- High Water Update ---
        if current_value > (state.high_value or 0):
            state.high_value = current_value

        # ====================================================================================================================================================
        # 8. Hard Stop Logic (Donchian Gate) and Persistent Maker Exit
        # ====================================================================================================================================================

        # 1. Donchian hard stop trigger (ALWAYS RUNS)
        if value_drop_frac(current_value, anchor) >= HARD_STOP_THRESHOLD_FRAC:
            if not state.donchian_gate_active:
                state.donchian_gate_active = True
                state.last_donchian_regime = regime
                state.hard_stop_armed = True
                print(f"[{now()}] Donchian hard stop triggered: regime={regime}")
                logger = get_logger()
                logger.warning(
                    f"Donchian hard stop triggered: regime={regime}, value_drop={value_drop_frac(current_value, anchor):.4%}, threshold={HARD_STOP_THRESHOLD_FRAC:.4%}"
                )
            # (For BASE, persistent exit proceeds in order block below. For QUOTE, just pause/restrict until Donchian mid-cross.)

        # 2. BASE regime: persistently drain BASE while Donchian gate is up (ALWAYS RUNS)
        if (
            regime == "BASE"
            and state.donchian_gate_active
            and state.live_bal_total[BASE_ASSET] >= MIN_QTY
            and (state.live_bal_total[BASE_ASSET] * bid) >= MIN_NOTIONAL
        ):
            if not state.hard_stop_armed:
                print(
                    f"[{now()}] HARD STOP ARMED (Donchian): Will persistently exit BASE at best bid with MAKER order."
                )
            state.hard_stop_armed = True

        if state.hard_stop_armed and regime == "BASE":
            qty = clip(state.live_bal_total[BASE_ASSET], LOT_SIZE)
            notional = qty * bid
            if qty >= MIN_QTY and notional >= MIN_NOTIONAL:
                await order_replace(
                    ws,
                    SYMBOL,
                    "SELL",
                    bid,
                    qty,
                    clientOrderId="HARD_STOP_SELL",
                    origClientOrderId="HARD_STOP_SELL",
                )
                print(
                    f"[{now()}] HARD_STOP LIMIT_MAKER SELL SENT | Qty: {qty:.8f} | Price: {bid:.2f}"
                )
                logger = get_logger()
                logger.warning(
                    f"Hard stop SELL order sent: Qty={qty:.8f}, Price={bid:.2f}, Notional={notional:.2f}"
                )

        # 3. QUOTE regime: just pause trading (no order to send)
        elif (
            regime == "QUOTE"
            and state.donchian_gate_active
            and state.live_bal_total[QUOTE_ASSET] >= MIN_NOTIONAL
        ):
            if not state.hard_stop_armed:
                print(
                    f"[{now()}] HARD STOP ARMED (Donchian): QUOTE regime Donchian gate entered. Will pause trading."
                )
            state.hard_stop_armed = True

        # 4. Normal trading: skip if Donchian gate is active
        if not skip_trading:
            # --- Persistent Maker Exit on Callback OR Hotkey ---
            if not state.maker_exit_armed and (
                (gain > min_gain_for_trigger and drawdown >= callback)
                or state.manual_exit_triggered  # <-- hotkey override
            ):
                state.maker_exit_armed = True
                if state.manual_exit_triggered:  # reset the one-shot trigger
                    state.manual_exit_triggered = False
                    print(f"[{now()}] [HOTKEY] Maker-exit armed by operator")

            if state.maker_exit_armed:
                side = "BUY" if regime == "QUOTE" else "SELL"
                if side == "BUY":
                    max_spend = state.live_bal_total[QUOTE_ASSET]
                    qty = clip((max_spend / ask), LOT_SIZE)
                    price = ask
                    client_id = "BUY"
                else:
                    qty = clip(state.live_bal_total[BASE_ASSET], LOT_SIZE)
                    price = bid
                    client_id = "SELL"

                notional = qty * price
                if qty >= MIN_QTY and notional >= MIN_NOTIONAL:
                    await order_replace(
                        ws,
                        SYMBOL,
                        side,
                        price,
                        qty,
                        clientOrderId=client_id,
                        origClientOrderId=client_id,
                    )
                    print(
                        f"[{now()}] LIMIT_MAKER {side} SENT | Qty: {qty:.8f} | Price: {price:.2f}"
                    )
                    logger = get_logger()
                    logger.info(
                        f"Maker exit {side} order sent: Qty={qty:.8f}, Price={price:.2f}, Notional={notional:.2f}, Regime={regime}"
                    )

        # ====================================================================================================================================================
        # 9. Print running state and diagnostics
        # ====================================================================================================================================================

        value_drop = anchor - current_value
        value_drop_frac_pct = 100 * value_drop / anchor if anchor > 0 else 0
        hard_stop_thresh_pct = 100 * HARD_STOP_THRESHOLD_FRAC

        # --- Print running state ---
        print("\n" + "=" * 60)
        print(f"[{now()}] Regime: {regime} | Symbol: {SYMBOL}")
        print(f"  Bid:  {bid:.8f}   Ask: {ask:.8f}")
        print(
            f"  Free:  {state.live_bal_free[BASE_ASSET]:.8f} {BASE_ASSET} | {state.live_bal_free[QUOTE_ASSET]:.2f} {QUOTE_ASSET}"
        )
        print(
            f"  Total: {state.live_bal_total[BASE_ASSET]:.8f} {BASE_ASSET} | {state.live_bal_total[QUOTE_ASSET]:.2f} {QUOTE_ASSET}"
        )
        print(f"  Anchor:    {fmt(state.anchor_value)}")
        print(
            f"  Current:   {fmt(current_value)} ({value_unit}) | "
            f"Drop from anchor: {fmt(value_drop)} ({value_drop_frac_pct:.4f}%) "
            f"[Hard Stop Thresh: {HARD_STOP_THRESHOLD_FRAC:.5f} ({hard_stop_thresh_pct:.4f}%)]"
        )
        print(f"  High:      {fmt(state.high_value)}")
        print("-" * 60)
        # --- Donchian Diagnostics ---
        print(f"  Donchian Channel (W={DONCHIAN_WINDOW}, Shift={DONCHIAN_SHIFT}):")
        print(
            f"    Upper: {last_upper:.4f} | Lower: {last_lower:.4f} | Mid: {last_mid:.4f} | Width: {donchian_width:.4f}"
        )
        print(
            f"    Donchian Gain Mult: {DONCHIAN_GAIN_MULTIPLIER:.3f} | Donchian Gate: {'ACTIVE' if state.donchian_gate_active else 'INACTIVE'}"
        )
        print(
            f"    Last Donchian Regime: {state.last_donchian_regime if hasattr(state, 'last_donchian_regime') else 'N/A'}"
        )
        print("-" * 60)
        print(
            f"  Gain: {fmt(gain)} | Gain Scale: {fmt(gain_scale)} | Gain/Gain Scale: {(gain / gain_scale):.4f}"
            if gain_scale
            else "N/A"
        )
        print(
            f"  Min Gain for Trigger: {fmt(min_gain_for_trigger)} | "
            f"Min Gain (anchor): {fmt(state.anchor_value * min_gain_trigger_frac)} | "
            f"Min Gain (fee + buffer): {fmt(state.anchor_value * (FEE + BUFFER))} | "
            f"Min Gain (Donchian): {fmt(min_gain_donchian)}"
        )
        print(f"  Callback:  {fmt(callback)} (Callback Factor: {callback_factor:.5f})")
        print(f"  Drawdown:  {fmt(drawdown)}")
        print("-" * 60)

        # ====================================================================================================================================================
        # ====================================================================================================================================================
        # ====================================================================================================================================================

        # --- Mode: bypass trading logic (set this True to skip trading actions this tick) ---
        # bypass_trading_blocks = True  # <---- Set this to True if you want to skip these blocks

        # --- BYPASSABLE BLOCKS START ---
        # if not bypass_trading_blocks:
        # --- BYPASSABLE BLOCKS END ---

        await asyncio.sleep(LOOP_SLEEP_SEC)


async def run_with_reconnect():
    """
    Main entry point with automatic reconnection logic.

    Validates configuration, sets up logging, and runs the main trading loop
    with automatic reconnection on WebSocket disconnections. Handles Ctrl-C
    gracefully for clean shutdown.

    Reconnection behavior:
    - Validates config before each connection attempt
    - Authenticates to Binance WebSocket API
    - Automatically reconnects with 5-second delays on connection loss
    - Logs all connection events and errors
    """
    # Validate configuration before starting
    from trailingedge.config_validator import ConfigValidationError, validate_all_config

    try:
        validate_all_config()
    except ConfigValidationError as e:
        print(f"[FATAL] Configuration validation failed:\n{e}")
        sys.exit(1)

    # Setup logging
    logger = setup_logging()
    logger.info("=== Trailing Edge Trading Bot Starting ===")

    retry_wait = 5
    while True:
        try:
            print(f"[{now()}] Connecting to Binance WebSocket API...")
            logger.info("Connecting to Binance WebSocket API...")
            async with websockets.connect(
                "wss://ws-api.binance.com:443/ws-api/v3"
            ) as ws:
                logon_response = await send_session_logon(ws)
                if logon_response.get("status") != 200:
                    print(f"[{now()}] Logon failed: {logon_response}")
                    logger.error(f"Authentication failed: {logon_response}")
                    return
                print(f"[{now()}] Authenticated to Binance WS API.")
                logger.info("Successfully authenticated to Binance WS API")
                await main_trading_loop(ws)
        except KeyboardInterrupt:
            print(
                f"\n[{now()}] [SHUTDOWN] Ctrl-C detected. Shutting down gracefully..."
            )
            logger.info("Shutdown requested by user (Ctrl-C)")
            return
        except websockets.exceptions.ConnectionClosedError as e:
            print(f"[{now()}] [WS ERROR] Code={e.code} Reason={e.reason}")
            logger.error(
                f"WebSocket connection closed: Code={e.code} Reason={e.reason}"
            )
        except Exception as e:
            print(f"[{now()}] [ERROR] WebSocket error or connection lost: {e}")
            logger.error(f"WebSocket error or connection lost: {type(e).__name__}: {e}")
        print(f"[{now()}] Attempting to reconnect in {retry_wait} seconds...")
        logger.info(f"Attempting to reconnect in {retry_wait} seconds...")
        await asyncio.sleep(retry_wait)


def main():
    """Entry point for console_scripts and __main__."""
    try:
        asyncio.run(run_with_reconnect())
    except KeyboardInterrupt:
        print(f"\n[{now()}] Bot stopped by user.")
        sys.exit(0)


if __name__ == "__main__":
    main()
