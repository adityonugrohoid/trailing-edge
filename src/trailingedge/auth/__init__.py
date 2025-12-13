"""Authentication module for Binance WebSocket API using Ed25519."""

from .manager import (
    build_session_logon_request,
    get_server_timestamp,
    load_ed25519_private_key,
    send_session_logon,
    sign_ed25519_message,
)

__all__ = [
    "load_ed25519_private_key",
    "sign_ed25519_message",
    "get_server_timestamp",
    "build_session_logon_request",
    "send_session_logon",
]
