"""
Integration tests for trading state transitions and regime changes.
"""

from unittest.mock import patch

import pytest

from trailingedge.main import TrailingState, detect_regime


@pytest.fixture
def mock_config():
    """Mock configuration constants."""
    with (
        patch("trailingedge.main.MIN_QTY", 0.0001),
        patch("trailingedge.main.MIN_NOTIONAL", 5.0),
        patch("trailingedge.main.LOT_SIZE", 0.0001),
        patch("trailingedge.main.BASE_ASSET", "ETH"),
        patch("trailingedge.main.QUOTE_ASSET", "FDUSD"),
    ):
        yield


def test_regime_transition_base_to_quote(mock_config):
    """Test transition from BASE to QUOTE regime."""
    # Start in BASE regime (holding ETH)
    balances_base = {"ETH": 1.0, "FDUSD": 0.0}
    regime = detect_regime(balances_base, bid=3000.0, ask=3001.0)
    assert regime == "BASE"

    # Transition to QUOTE regime (now holding FDUSD)
    balances_quote = {"ETH": 0.0, "FDUSD": 3000.0}
    regime = detect_regime(balances_quote, bid=3000.0, ask=3001.0)
    assert regime == "QUOTE"


def test_regime_transition_quote_to_base(mock_config):
    """Test transition from QUOTE to BASE regime."""
    # Start in QUOTE regime
    balances_quote = {"ETH": 0.0, "FDUSD": 3000.0}
    regime = detect_regime(balances_quote, bid=3000.0, ask=3001.0)
    assert regime == "QUOTE"

    # Transition to BASE regime
    balances_base = {"ETH": 1.0, "FDUSD": 0.0}
    regime = detect_regime(balances_base, bid=3000.0, ask=3001.0)
    assert regime == "BASE"


def test_regime_transition_full_cycle(mock_config):
    """Test complete cycle: BASE → QUOTE → BASE."""
    # Start BASE
    bal1 = {"ETH": 1.0, "FDUSD": 0.0}
    assert detect_regime(bal1, 3000.0, 3001.0) == "BASE"

    # → QUOTE
    bal2 = {"ETH": 0.0, "FDUSD": 3000.0}
    assert detect_regime(bal2, 3000.0, 3001.0) == "QUOTE"

    # → BASE again
    bal3 = {"ETH": 1.0, "FDUSD": 0.0}
    assert detect_regime(bal3, 3000.0, 3001.0) == "BASE"


def test_state_reset_for_regime_flip():
    """Test that TrailingState resets properly on regime flip."""
    state = TrailingState()

    # Setup initial state
    state.anchor_value = 100.0
    state.high_value = 120.0
    state.maker_exit_armed = True
    state.hard_stop_armed = True

    # Reset on regime flip
    new_value = 150.0
    state.reset_for_regime_flip(new_value)

    # Verify all values reset
    assert state.anchor_value == 150.0
    assert state.high_value == 150.0
    assert state.maker_exit_armed is False
    assert state.hard_stop_armed is False


def test_donchian_gate_activation():
    """Test Donchian gate activation and deactivation."""
    state = TrailingState()

    # Initially inactive
    assert state.donchian_gate_active is False
    assert state.last_donchian_regime is None

    # Activate gate (simulating hard stop trigger)
    state.donchian_gate_active = True
    state.last_donchian_regime = "BASE"
    state.hard_stop_armed = True

    assert state.donchian_gate_active is True
    assert state.last_donchian_regime == "BASE"
    assert state.hard_stop_armed is True

    # Deactivate gate (simulating Donchian mid-cross)
    state.donchian_gate_active = False
    state.last_donchian_regime = None

    assert state.donchian_gate_active is False
    assert state.last_donchian_regime is None


def test_hard_stop_arming_and_disarming():
    """Test hard stop arming and disarming logic."""
    state = TrailingState()

    # Initially not armed
    assert state.hard_stop_armed is False

    # Arm hard stop
    state.hard_stop_armed = True
    assert state.hard_stop_armed is True

    # Reset disarms hard stop
    state.reset_for_regime_flip(100.0)
    assert state.hard_stop_armed is False


def test_anchor_high_value_updates():
    """Test anchor and high value updates during regime operations."""
    state = TrailingState()

    # Initial values are None
    assert state.anchor_value is None
    assert state.high_value is None

    # Set initial anchor/high on regime flip
    state.reset_for_regime_flip(100.0)
    assert state.anchor_value == 100.0
    assert state.high_value == 100.0

    # High value should update when current exceeds it
    state.high_value = 120.0
    assert state.high_value == 120.0
    assert state.anchor_value == 100.0  # Anchor stays

    # Reset brings both back to new value
    state.reset_for_regime_flip(150.0)
    assert state.anchor_value == 150.0
    assert state.high_value == 150.0


def test_maker_exit_arming():
    """Test maker exit arming and disarming."""
    state = TrailingState()

    # Initially not armed
    assert state.maker_exit_armed is False

    # Arm maker exit (simulating callback trigger)
    state.maker_exit_armed = True
    assert state.maker_exit_armed is True

    # Reset disarms maker exit
    state.reset_for_regime_flip(100.0)
    assert state.maker_exit_armed is False


def test_manual_exit_trigger():
    """Test manual exit trigger flag (hotkey)."""
    state = TrailingState()

    # Initially not triggered
    assert state.manual_exit_triggered is False

    # Simulate hotkey press
    state.manual_exit_triggered = True
    assert state.manual_exit_triggered is True

    # After processing, it should be reset
    state.manual_exit_triggered = False
    assert state.manual_exit_triggered is False


def test_regime_none_with_insufficient_funds(mock_config):
    """Test that regime is None when funds are insufficient."""
    # Too little of both assets
    balances = {"ETH": 0.00001, "FDUSD": 1.0}
    regime = detect_regime(balances, bid=3000.0, ask=3001.0)
    assert regime is None

    # With debug=True, get reason
    regime, reason = detect_regime(balances, bid=3000.0, ask=3001.0, debug=True)
    assert regime is None
    assert "below min" in reason.lower()
