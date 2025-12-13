"""
Integration tests for WebSocket reconnection logic with exponential backoff.

Note: These tests verify the retry logic structure without indefinite streaming.
"""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
import websockets
from websockets.frames import Close, CloseCode


@pytest.mark.asyncio
async def test_bookticker_reconnection_attempts():
    """Test that BookTicker stream attempts reconnection on ConnectionClosedError."""
    from trailingedge.websocket.market_stream import stream_bookticker_shared

    snapshot = {}
    call_count = [0]

    def mock_connect(*args, **kwargs):
        call_count[0] += 1
        # Always fail to test retry mechanism
        # Create proper Close frame to avoid deprecation warnings
        rcvd = Close(CloseCode.NORMAL_CLOSURE, "test")
        raise websockets.exceptions.ConnectionClosedError(rcvd, None)

    with patch(
        "trailingedge.websocket.market_stream.websockets.connect",
        side_effect=mock_connect,
    ):
        with patch(
            "trailingedge.websocket.market_stream.asyncio.sleep", new_callable=AsyncMock
        ):
            with pytest.raises(websockets.exceptions.ConnectionClosedError):
                await stream_bookticker_shared("ETHUSDT", snapshot)

    # Verify it attempted to connect 3 times (initial + 2 retries before giving up on 3rd)
    assert call_count[0] == 3  # Initial attempt + 2 retries


@pytest.mark.asyncio
async def test_max_retries_exceeded():
    """Test that stream gives up after max retries."""
    from trailingedge.websocket.market_stream import stream_bookticker_shared

    snapshot = {}

    # Always fail
    def mock_connect_always_fails(*args, **kwargs):
        # Create proper Close frame to avoid deprecation warnings
        rcvd = Close(CloseCode.NORMAL_CLOSURE, "test")
        raise websockets.exceptions.ConnectionClosedError(rcvd, None)

    with patch(
        "trailingedge.websocket.market_stream.websockets.connect",
        side_effect=mock_connect_always_fails,
    ):
        with patch(
            "trailingedge.websocket.market_stream.asyncio.sleep", new_callable=AsyncMock
        ):
            with pytest.raises(websockets.exceptions.ConnectionClosedError):
                await stream_bookticker_shared("ETHUSDT", snapshot)


@pytest.mark.asyncio
async def test_exponential_backoff_delays():
    """Test that retry delays follow exponential backoff pattern."""
    from trailingedge.websocket.market_stream import stream_bookticker_shared

    snapshot = {}
    sleep_delays = []

    # Mock sleep to capture delays
    async def mock_sleep(delay):
        sleep_delays.append(delay)

    # Always fail to test all retries
    def mock_connect_always_fails(*args, **kwargs):
        # Create proper Close frame to avoid deprecation warnings
        rcvd = Close(CloseCode.NORMAL_CLOSURE, "test")
        raise websockets.exceptions.ConnectionClosedError(rcvd, None)

    with patch(
        "trailingedge.websocket.market_stream.websockets.connect",
        side_effect=mock_connect_always_fails,
    ):
        with patch(
            "trailingedge.websocket.market_stream.asyncio.sleep", side_effect=mock_sleep
        ):
            with pytest.raises(websockets.exceptions.ConnectionClosedError):
                await stream_bookticker_shared("ETHUSDT", snapshot)

    # Verify exponential backoff: [2, 4] seconds (only 2 retries before giving up)
    # Note: After initial failure, it retries twice with delays [2, 4] before final attempt
    assert len(sleep_delays) >= 2
    assert sleep_delays[0] == 2
    assert sleep_delays[1] == 4


@pytest.mark.asyncio
async def test_connection_timeout_handling():
    """Test that connection timeouts are handled properly."""
    from trailingedge.websocket.market_stream import stream_kline_shared

    kline_dict = {}
    timeout_count = [0]

    def mock_connect_timeout(*args, **kwargs):
        timeout_count[0] += 1
        if timeout_count[0] <= 1:
            raise asyncio.TimeoutError("Connection timed out")
        # After timeout, raise a different error to stop the loop
        # Create proper Close frame to avoid deprecation warnings
        rcvd = Close(CloseCode.NORMAL_CLOSURE, "test")
        raise websockets.exceptions.ConnectionClosedError(rcvd, None)

    with patch(
        "trailingedge.websocket.market_stream.websockets.connect",
        side_effect=mock_connect_timeout,
    ):
        with patch(
            "trailingedge.websocket.market_stream.asyncio.sleep", new_callable=AsyncMock
        ):
            with pytest.raises(websockets.exceptions.ConnectionClosedError):
                await stream_kline_shared("ETHUSDT", "1m", kline_dict)

    # Verify it handled timeout and retried
    assert timeout_count[0] >= 1
