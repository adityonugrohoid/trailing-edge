"""
Configuration Validator for Trailing Edge Trading Bot

Validates all configuration parameters and environment variables on startup.
Ensures the bot has valid settings before connecting to exchanges.
"""

import os
from pathlib import Path

from trailingedge import config


class ConfigValidationError(Exception):
    """Raised when configuration validation fails."""

    pass


def validate_trading_pair_config():
    """Validate trading pair configuration parameters."""
    errors = []

    if config.MIN_QTY <= 0:
        errors.append(f"MIN_QTY must be > 0, got {config.MIN_QTY}")

    if config.MIN_NOTIONAL <= 0:
        errors.append(f"MIN_NOTIONAL must be > 0, got {config.MIN_NOTIONAL}")

    if config.LOT_SIZE <= 0:
        errors.append(f"LOT_SIZE must be > 0, got {config.LOT_SIZE}")

    if config.PRICE_TICK <= 0:
        errors.append(f"PRICE_TICK must be > 0, got {config.PRICE_TICK}")

    if config.MIN_PRICE < 0:
        errors.append(f"MIN_PRICE must be >= 0, got {config.MIN_PRICE}")

    if errors:
        raise ConfigValidationError(
            "Trading pair configuration errors:\n"
            + "\n".join(f"  - {e}" for e in errors)
        )


def validate_trailing_config():
    """Validate trailing stop configuration parameters."""
    errors = []

    if not (0 <= config.START_FACTOR <= 1):
        errors.append(
            f"START_FACTOR must be between 0 and 1, got {config.START_FACTOR}"
        )

    if not (0 <= config.MIN_FACTOR <= 1):
        errors.append(f"MIN_FACTOR must be between 0 and 1, got {config.MIN_FACTOR}")

    if config.START_FACTOR < config.MIN_FACTOR:
        errors.append(
            f"START_FACTOR ({config.START_FACTOR}) must be >= MIN_FACTOR ({config.MIN_FACTOR})"
        )

    if config.GAIN_SCALE_FRAC_BASE < 0:
        errors.append(
            f"GAIN_SCALE_FRAC_BASE must be >= 0, got {config.GAIN_SCALE_FRAC_BASE}"
        )

    if config.GAIN_SCALE_FRAC_QUOTE < 0:
        errors.append(
            f"GAIN_SCALE_FRAC_QUOTE must be >= 0, got {config.GAIN_SCALE_FRAC_QUOTE}"
        )

    if config.MIN_GAIN_TRIGGER_FRAC_BASE < 0:
        errors.append(
            f"MIN_GAIN_TRIGGER_FRAC_BASE must be >= 0, got {config.MIN_GAIN_TRIGGER_FRAC_BASE}"
        )

    if config.MIN_GAIN_TRIGGER_FRAC_QUOTE < 0:
        errors.append(
            f"MIN_GAIN_TRIGGER_FRAC_QUOTE must be >= 0, got {config.MIN_GAIN_TRIGGER_FRAC_QUOTE}"
        )

    if config.HARD_STOP_THRESHOLD_FRAC < 0:
        errors.append(
            f"HARD_STOP_THRESHOLD_FRAC must be >= 0, got {config.HARD_STOP_THRESHOLD_FRAC}"
        )

    if errors:
        raise ConfigValidationError(
            "Trailing configuration errors:\n" + "\n".join(f"  - {e}" for e in errors)
        )


def validate_fee_and_buffer():
    """Validate fee and buffer settings."""
    errors = []

    if config.FEE < 0:
        errors.append(f"FEE must be >= 0, got {config.FEE}")

    if config.BUFFER < 0:
        errors.append(f"BUFFER must be >= 0, got {config.BUFFER}")

    if errors:
        raise ConfigValidationError(
            "Fee/buffer configuration errors:\n" + "\n".join(f"  - {e}" for e in errors)
        )


def validate_donchian_config():
    """Validate Donchian channel configuration."""
    errors = []

    if config.DONCHIAN_WINDOW <= 0:
        errors.append(f"DONCHIAN_WINDOW must be > 0, got {config.DONCHIAN_WINDOW}")

    if config.DONCHIAN_SHIFT < 0:
        errors.append(f"DONCHIAN_SHIFT must be >= 0, got {config.DONCHIAN_SHIFT}")

    if config.DONCHIAN_GAIN_MULTIPLIER < 0:
        errors.append(
            f"DONCHIAN_GAIN_MULTIPLIER must be >= 0, got {config.DONCHIAN_GAIN_MULTIPLIER}"
        )

    if errors:
        raise ConfigValidationError(
            "Donchian configuration errors:\n" + "\n".join(f"  - {e}" for e in errors)
        )


def validate_kline_config():
    """Validate kline configuration."""
    errors = []

    valid_intervals = [
        "1s",
        "1m",
        "3m",
        "5m",
        "15m",
        "30m",
        "1h",
        "2h",
        "4h",
        "6h",
        "8h",
        "12h",
        "1d",
        "3d",
        "1w",
        "1M",
    ]
    if config.KLINE_INTERVAL not in valid_intervals:
        errors.append(
            f"KLINE_INTERVAL must be one of {valid_intervals}, got {config.KLINE_INTERVAL}"
        )

    if config.ROLLING_KLINES_MAXLEN <= 0:
        errors.append(
            f"ROLLING_KLINES_MAXLEN must be > 0, got {config.ROLLING_KLINES_MAXLEN}"
        )

    if errors:
        raise ConfigValidationError(
            "Kline configuration errors:\n" + "\n".join(f"  - {e}" for e in errors)
        )


def validate_environment_variables():
    """Validate that required environment variables are set."""
    from dotenv import load_dotenv

    # Load .env file
    load_dotenv()

    errors = []
    required_vars = [
        "BINANCE_ED25519_API_KEY",
        "BINANCE_ED25519_PRIV_PATH",
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_CHAT_ID",
    ]

    for var in required_vars:
        value = os.getenv(var)
        if not value:
            errors.append(f"Environment variable {var} is not set or empty")

    if errors:
        raise ConfigValidationError(
            "Environment variable errors:\n" + "\n".join(f"  - {e}" for e in errors)
        )


def validate_secrets_files():
    """Validate that required secrets files exist and are readable."""
    from dotenv import load_dotenv

    load_dotenv()

    errors = []
    priv_key_path = os.getenv("BINANCE_ED25519_PRIV_PATH")

    if not priv_key_path:
        errors.append("BINANCE_ED25519_PRIV_PATH environment variable not set")
    else:
        priv_key_file = Path(priv_key_path)
        if not priv_key_file.exists():
            errors.append(f"Private key file not found: {priv_key_path}")
        elif not priv_key_file.is_file():
            errors.append(f"Private key path is not a file: {priv_key_path}")
        elif not os.access(priv_key_file, os.R_OK):
            errors.append(f"Private key file is not readable: {priv_key_path}")

    if errors:
        raise ConfigValidationError(
            "Secrets file errors:\n" + "\n".join(f"  - {e}" for e in errors)
        )


def validate_all_config():
    """
    Run all configuration validators.
    Raises ConfigValidationError if any validation fails.
    """
    validators = [
        ("Trading Pair Config", validate_trading_pair_config),
        ("Trailing Config", validate_trailing_config),
        ("Fee/Buffer", validate_fee_and_buffer),
        ("Donchian Config", validate_donchian_config),
        ("Kline Config", validate_kline_config),
        ("Environment Variables", validate_environment_variables),
        ("Secrets Files", validate_secrets_files),
    ]

    print("[Config Validator] Starting configuration validation...")

    for name, validator in validators:
        try:
            validator()
            print(f"[Config Validator] ✓ {name} validated")
        except ConfigValidationError:
            print(f"[Config Validator] ✗ {name} validation failed")
            raise

    print("[Config Validator] ✓ All configuration validated successfully")
