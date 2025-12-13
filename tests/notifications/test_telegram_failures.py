"""
Integration tests for Telegram notification failure handling.
"""

from unittest.mock import MagicMock, patch

import requests


def test_telegram_missing_bot_token():
    """Test that send_telegram_message fails gracefully when bot token is missing."""
    from trailingedge.notifications.telegram import send_telegram_message

    with patch("trailingedge.notifications.telegram.TELEGRAM_BOT_TOKEN", None):
        result = send_telegram_message("Test message")
        assert result is False


def test_telegram_missing_chat_id():
    """Test that send_telegram_message fails gracefully when chat ID is missing."""
    from trailingedge.notifications.telegram import send_telegram_message

    with patch("trailingedge.notifications.telegram.TELEGRAM_BOT_TOKEN", "test_token"):
        with patch("trailingedge.notifications.telegram.TELEGRAM_CHAT_ID", None):
            result = send_telegram_message("Test message")
            assert result is False


def test_telegram_network_timeout():
    """Test that send_telegram_message handles network timeouts."""
    from trailingedge.notifications.telegram import send_telegram_message

    def mock_post_timeout(*args, **kwargs):
        raise requests.exceptions.Timeout("Connection timed out")

    with patch("trailingedge.notifications.telegram.TELEGRAM_BOT_TOKEN", "test_token"):
        with patch("trailingedge.notifications.telegram.TELEGRAM_CHAT_ID", "12345"):
            with patch(
                "trailingedge.notifications.telegram.requests.post",
                side_effect=mock_post_timeout,
            ):
                result = send_telegram_message("Test message")
                assert result is False


def test_telegram_http_error():
    """Test that send_telegram_message handles HTTP errors (non-200 status)."""
    from trailingedge.notifications.telegram import send_telegram_message

    mock_response = MagicMock()
    mock_response.status_code = 400
    mock_response.text = "Bad Request"

    with patch("trailingedge.notifications.telegram.TELEGRAM_BOT_TOKEN", "test_token"):
        with patch("trailingedge.notifications.telegram.TELEGRAM_CHAT_ID", "12345"):
            with patch(
                "trailingedge.notifications.telegram.requests.post",
                return_value=mock_response,
            ):
                result = send_telegram_message("Test message")
                assert result is False


def test_telegram_success():
    """Test that send_telegram_message succeeds with valid credentials."""
    from trailingedge.notifications.telegram import send_telegram_message

    mock_response = MagicMock()
    mock_response.status_code = 200

    with patch("trailingedge.notifications.telegram.TELEGRAM_BOT_TOKEN", "test_token"):
        with patch("trailingedge.notifications.telegram.TELEGRAM_CHAT_ID", "12345"):
            with patch(
                "trailingedge.notifications.telegram.requests.post",
                return_value=mock_response,
            ):
                result = send_telegram_message("Test message")
                assert result is True


def test_broadcast_to_multiple_recipients():
    """Test that broadcast_telegram_message sends to multiple recipients."""
    from trailingedge.notifications.telegram import broadcast_telegram_message

    mock_response = MagicMock()
    mock_response.status_code = 200

    call_count = []

    def mock_post(*args, **kwargs):
        call_count.append(1)
        return mock_response

    with patch("trailingedge.notifications.telegram.TELEGRAM_BOT_TOKEN", "test_token"):
        with patch(
            "trailingedge.notifications.telegram.TELEGRAM_GROUP_CHAT_ID_1", "chat1"
        ):
            with patch(
                "trailingedge.notifications.telegram.TELEGRAM_GROUP_CHAT_ID_2", "chat2"
            ):
                with patch(
                    "trailingedge.notifications.telegram.requests.post",
                    side_effect=mock_post,
                ):
                    result = broadcast_telegram_message("Test broadcast")
                    # Should send to 2 recipients
                    assert result == 2
                    assert len(call_count) == 2


def test_broadcast_partial_failure():
    """Test that broadcast continues even if one recipient fails."""
    from trailingedge.notifications.telegram import broadcast_telegram_message

    mock_success = MagicMock()
    mock_success.status_code = 200

    mock_failure = MagicMock()
    mock_failure.status_code = 400

    responses = [mock_failure, mock_success]

    def mock_post(*args, **kwargs):
        return responses.pop(0)

    with patch("trailingedge.notifications.telegram.TELEGRAM_BOT_TOKEN", "test_token"):
        with patch(
            "trailingedge.notifications.telegram.TELEGRAM_GROUP_CHAT_ID_1", "chat1"
        ):
            with patch(
                "trailingedge.notifications.telegram.TELEGRAM_GROUP_CHAT_ID_2", "chat2"
            ):
                with patch(
                    "trailingedge.notifications.telegram.requests.post",
                    side_effect=mock_post,
                ):
                    result = broadcast_telegram_message("Test broadcast")
                    # Should succeed for 1 out of 2
                    assert result == 1
