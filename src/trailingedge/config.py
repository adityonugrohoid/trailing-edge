"""
Trading Bot Configuration

Configuration constants for the trailing-edge trading bot including:
- Trading pair settings
- Order constraints and filters
- Fee and buffer settings
- Trailing stop parameters
- Technical indicator configurations
"""

# --- Trading Pair Config ---
SYMBOL = "ETHFDUSD"
BASE_ASSET = "ETH"
QUOTE_ASSET = "FDUSD"

# --- Filters for constraints (ETHFDUSD) ---
LOT_SIZE = 0.0001  # stepSize for limit orders (LOT_SIZE filter)
MIN_QTY = 0.0001  # minQty (LOT_SIZE filter)
PRICE_TICK = 0.01  # tickSize (PRICE_FILTER)
MIN_PRICE = 0.01  # minPrice (PRICE_FILTER)
MIN_NOTIONAL = 5.0  # minNotional (NOTIONAL filter, applies to market+limit)

# --- Fees and Guard Buffer ---
FEE = 0.0000  # 0.0% fee (Binance spot zero maker fee for ETHFDUSD)
BUFFER = 0.0020  # 0.2% reference value


# --- Trailing Config ---
START_FACTOR = 0.5
MIN_FACTOR = 0.1
GAIN_SCALE_FRAC_BASE = 0.005
GAIN_SCALE_FRAC_QUOTE = 0.005

# --- Dynamic min gain trigger levels ---
MIN_GAIN_TRIGGER_FRAC_BASE = 0.01  # e.g. 0.01 for 1% base asset gain
MIN_GAIN_TRIGGER_FRAC_QUOTE = 0.01  # e.g. 0.01 for 1% quote asset gain

# --- Hard Stop Loss Config ---
HARD_STOP_THRESHOLD_FRAC = 0.005  # e.g. 0.005 for 0.5% stop loss
# Rationale: Risk 0.5% to make 1%+ = 2:1 reward ratio minimum

# --- Kline Config ---
KLINE_INTERVAL = "1m"
ROLLING_KLINES_MAXLEN = 1440  # Keep full day of 1m candles

# --- Donchian Config ---
DONCHIAN_WINDOW = 40  # 40 periods (was 20)
DONCHIAN_SHIFT = 2  # 2 periods shift (was 1)
# Rationale: Longer window = smoother channel, less reactive to short-term noise

# --- Donchian Gain Multiplier ---
DONCHIAN_GAIN_MULTIPLIER = 0.5  # Enable Donchian gating (was 0.0)
# Rationale: After hard stop, wait for 50% of Donchian channel width in gain
# before allowing re-entry. Prevents catching falling knives.

# --- Async Loop Config ---
LOOP_SLEEP_SEC = 1.0  # Main async loop sleep duration (in seconds)
