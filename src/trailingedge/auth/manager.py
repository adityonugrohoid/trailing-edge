"""
Trailing Edge Trading Bot - Ed25519 Authentication Manager

Handles private key loading, message signing, timestamp, and session logon
for Binance WebSocket API authentication.
"""

import base64
import json
import os
import time

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from dotenv import load_dotenv

# Load environment variables from project root
load_dotenv()

API_KEY = os.getenv("BINANCE_ED25519_API_KEY")
PRIV_KEY_PATH = os.getenv("BINANCE_ED25519_PRIV_PATH")


def load_ed25519_private_key() -> Ed25519PrivateKey:
    """
    Load Ed25519 private key from PEM file defined in .env.
    """
    if not PRIV_KEY_PATH:
        raise ValueError("BINANCE_ED25519_PRIV_PATH not set in .env")
    with open(PRIV_KEY_PATH, "rb") as f:
        key_data = f.read()
    return serialization.load_pem_private_key(key_data, password=None)


def sign_ed25519_message(message: str) -> str:
    """
    Sign a message with Ed25519 and return a base64-encoded signature.
    """
    private_key: Ed25519PrivateKey = load_ed25519_private_key()
    signature = private_key.sign(message.encode("utf-8"))
    return base64.b64encode(signature).decode("utf-8")


def get_server_timestamp() -> int:
    """
    Return current UNIX timestamp in milliseconds.
    """
    return int(time.time() * 1000)


def build_session_logon_request() -> dict:
    """
    Construct a session.logon request dictionary for Binance WebSocket authentication.
    """
    ts = get_server_timestamp()
    payload = f"apiKey={API_KEY}&timestamp={ts}"
    signature = sign_ed25519_message(payload)
    return {
        "id": "session_logon",
        "method": "session.logon",
        "params": {"apiKey": API_KEY, "timestamp": ts, "signature": signature},
    }


async def send_session_logon(ws) -> dict:
    """
    Send a session.logon request via the provided WebSocket connection.
    Returns the parsed response as a dictionary.
    """
    request = build_session_logon_request()
    await ws.send(json.dumps(request))
    response = await ws.recv()
    return json.loads(response)
