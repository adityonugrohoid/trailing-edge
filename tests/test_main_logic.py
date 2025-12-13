# Mock config constants used in detect_regime
# We need to patch them because they are imported into main.py
from unittest.mock import patch

import pytest

from trailingedge.main import clip, detect_regime


@pytest.fixture
def mock_config():
    with (
        patch("trailingedge.main.MIN_QTY", 0.0001),
        patch("trailingedge.main.MIN_NOTIONAL", 5.0),
        patch("trailingedge.main.LOT_SIZE", 0.0001),
        patch("trailingedge.main.BASE_ASSET", "ETH"),
        patch("trailingedge.main.QUOTE_ASSET", "FDUSD"),
    ):
        yield


def test_clip():
    """Test the clip (round down) function."""
    assert clip(1.23456, 0.01) == 1.23
    assert clip(1.23999, 0.01) == 1.23
    assert clip(105, 10) == 100
    assert clip(None, 1) == 0.0


def test_detect_regime_base(mock_config):
    """Test detection of BASE regime (holding ETH)."""
    # 1.0 ETH, 0 FDUSD. Price 3000.
    # Notional = 3000 > 5.0 (MIN_NOTIONAL)
    balances = {"ETH": 1.0, "FDUSD": 0.0}
    regime = detect_regime(balances, bid=3000.0, ask=3001.0)
    assert regime == "BASE"


def test_detect_regime_quote(mock_config):
    """Test detection of QUOTE regime (holding FDUSD)."""
    # 0 ETH, 3000 FDUSD.
    balances = {"ETH": 0.0, "FDUSD": 3000.0}
    regime = detect_regime(balances, bid=3000.0, ask=3001.0)
    assert regime == "QUOTE"


def test_detect_regime_none(mock_config):
    """Test detection of insufficient funds (None regime)."""
    # 0.00001 ETH (too small), 1.0 FDUSD (too small)
    balances = {"ETH": 0.00001, "FDUSD": 1.0}
    regime = detect_regime(balances, bid=3000.0, ask=3001.0)
    assert regime is None
