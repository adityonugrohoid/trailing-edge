"""
Telegram Notification System

Handles secure outbound messaging using Telegram Bot API.
Supports Markdown-formatted messages for trade alerts, errors, and status notifications.
Supports sending to single, group, or multiple recipients.
"""

import logging
import os

import requests
from dotenv import load_dotenv

logger = logging.getLogger("trailingedge")

# Load environment variables from project root
load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")  # Personal chat
TELEGRAM_GROUP_CHAT_ID_GLOBAL = os.getenv(
    "TELEGRAM_GROUP_CHAT_ID_GLOBAL"
)  # Group chat global
TELEGRAM_GROUP_CHAT_ID_1 = os.getenv("TELEGRAM_GROUP_CHAT_ID_1")  # Group chat 1
TELEGRAM_GROUP_CHAT_ID_2 = os.getenv("TELEGRAM_GROUP_CHAT_ID_2")  # Group chat 2


def send_telegram_message(
    message: str, chat_id: str = None, return_response: bool = False
):
    """
    Send a formatted message to Telegram using the configured bot and chat ID.
    Optionally override the chat ID for group or alternate recipients.
    If return_response=True, returns the raw response object for debug/testing.
    """
    if not TELEGRAM_BOT_TOKEN:
        print("[Telegram] Missing bot token.")
        logger.error("Telegram: Missing bot token")
        return False

    target_chat_id = chat_id if chat_id else TELEGRAM_CHAT_ID
    if not target_chat_id:
        print("[Telegram] No target chat ID.")
        logger.error("Telegram: No target chat ID")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": target_chat_id, "text": message, "parse_mode": "Markdown"}

    try:
        response = requests.post(url, data=payload, timeout=5)
        if return_response:
            return response
        if response.status_code != 200:
            logger.warning(
                f"Telegram notification failed: {response.status_code} - {response.text}"
            )
        return response.status_code == 200
    except Exception as e:
        if return_response:
            return e
        print(f"[Telegram Error] {e}")
        logger.error(f"Telegram notification error: {type(e).__name__}: {e}")
        return False


def broadcast_telegram_message(
    message: str, chat_id_list=None, return_response: bool = False
):
    """
    Broadcast a message to multiple Telegram chat IDs (private, group, etc).
    If chat_id_list is None, uses TELEGRAM_CHAT_ID and group IDs from .env if present.
    If return_response=True, returns a list of response objects.
    Returns the number of successful deliveries (or list of responses if return_response=True).
    """
    if chat_id_list is None:
        chat_id_list = []
        # if TELEGRAM_GROUP_CHAT_ID_GLOBAL: chat_id_list.append(TELEGRAM_GROUP_CHAT_ID_GLOBAL)
        if TELEGRAM_GROUP_CHAT_ID_1:
            chat_id_list.append(TELEGRAM_GROUP_CHAT_ID_1)
        if TELEGRAM_GROUP_CHAT_ID_2:
            chat_id_list.append(TELEGRAM_GROUP_CHAT_ID_2)

    count = 0
    responses = []
    for cid in chat_id_list:
        if cid:
            resp = send_telegram_message(
                message, chat_id=cid, return_response=return_response
            )
            if return_response:
                responses.append(resp)
            elif resp:
                count += 1
    return responses if return_response else count


# Internal test
if __name__ == "__main__":
    print("\n[Internal Test] Broadcasting to all configured recipients...")
    resp_list = broadcast_telegram_message(
        "📢 *Trailing Edge Bot Broadcast Test* — Multi-recipient alert.",
        return_response=True,
    )
    for idx, resp in enumerate(resp_list, 1):
        if hasattr(resp, "status_code"):
            print(f"[Test Result] Broadcast #{idx}: {resp.status_code} | {resp.text}")
        else:
            print(f"[Test Result] Broadcast #{idx} Error: {resp}")
