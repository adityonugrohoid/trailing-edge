from unittest.mock import MagicMock, patch

import pytest

from trailingedge.auth.manager import build_session_logon_request, sign_ed25519_message


# Mock the private key loading so we don't need a real key file
@pytest.fixture
def mock_private_key():
    with patch("trailingedge.auth.manager.load_ed25519_private_key") as mock_load:
        # Create a dummy key object that returns a fixed signature
        mock_key = MagicMock()
        mock_key.sign.return_value = b"fake_signature_bytes"
        mock_load.return_value = mock_key
        yield mock_load


def test_sign_ed25519_message(mock_private_key):
    """Test that message signing returns correct base64 string."""
    signature = sign_ed25519_message("test_message")
    # "fake_signature_bytes" in base64 is "ZmFrZV9zaWduYXR1cmVfYnl0ZXM="
    assert signature == "ZmFrZV9zaWduYXR1cmVfYnl0ZXM="


def test_build_session_logon_request(mock_private_key):
    """Test that logon request has correct structure and params."""
    with patch("trailingedge.auth.manager.API_KEY", "test_api_key"):
        with patch(
            "trailingedge.auth.manager.get_server_timestamp", return_value=1234567890
        ):
            request = build_session_logon_request()

            assert request["method"] == "session.logon"
            assert request["params"]["apiKey"] == "test_api_key"
            assert request["params"]["timestamp"] == 1234567890
            assert "signature" in request["params"]
