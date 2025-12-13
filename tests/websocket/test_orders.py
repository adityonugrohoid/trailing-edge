import json
from unittest.mock import AsyncMock, patch

import pytest

from trailingedge.websocket.orders import place_limit_order, place_market_order


@pytest.mark.asyncio
async def test_place_limit_order():
    """Test that place_limit_order sends correct JSON payload."""
    mock_ws = AsyncMock()

    # Mock timestamp to get consistent output
    with patch(
        "trailingedge.websocket.orders.get_server_timestamp", return_value=1234567890
    ):
        await place_limit_order(mock_ws, "ETHFDUSD", "BUY", 3000.0, 0.1)

        # Verify send was called
        mock_ws.send.assert_called_once()

        # Verify payload content
        sent_json = mock_ws.send.call_args[0][0]
        payload = json.loads(sent_json)

        assert payload["method"] == "order.place"
        assert payload["params"]["symbol"] == "ETHFDUSD"
        assert payload["params"]["side"] == "BUY"
        assert payload["params"]["type"] == "LIMIT"
        assert payload["params"]["price"] == "3000.00000000"
        assert payload["params"]["quantity"] == "0.10000000"
        assert payload["params"]["timestamp"] == 1234567890


@pytest.mark.asyncio
async def test_place_market_order():
    """Test that place_market_order sends correct JSON payload."""
    mock_ws = AsyncMock()

    with patch(
        "trailingedge.websocket.orders.get_server_timestamp", return_value=1234567890
    ):
        await place_market_order(mock_ws, "BTCUSDT", "SELL", 0.5)

        mock_ws.send.assert_called_once()
        sent_json = mock_ws.send.call_args[0][0]
        payload = json.loads(sent_json)

        assert payload["method"] == "order.place"
        assert payload["params"]["type"] == "MARKET"
        assert payload["params"]["side"] == "SELL"
        assert payload["params"]["quantity"] == "0.50000000"
