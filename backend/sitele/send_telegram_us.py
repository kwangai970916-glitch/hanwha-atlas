# -*- coding: utf-8 -*-
"""Telegram sender for the US market report image.

Secrets are intentionally not stored in source code. Set these in `.env` or
Windows environment variables:
- TELEGRAM_US_BOT_TOKEN
- TELEGRAM_CHAT_ID
- TELEGRAM_TEST_CHAT_ID
"""

from __future__ import annotations

import os
import sys

import requests

from report_config import get_env, require_env
from send_telegram_tele import prepare_caption_and_followups

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def _bot_token() -> str:
    return require_env("TELEGRAM_US_BOT_TOKEN")


def _default_chat_id() -> str:
    return require_env("TELEGRAM_CHAT_ID")


def _test_chat_id() -> str:
    test_id = get_env("TELEGRAM_TEST_CHAT_ID")
    if test_id:
        return test_id

    # Backward-compatible safe fallback: older .env files only had
    # TELEGRAM_CHAT_ID, often as "personal,group".  During testing, choose the
    # first non-group chat id instead of sending to every configured room.
    default_ids = _split_chat_ids(get_env("TELEGRAM_CHAT_ID", ""))
    for cid in default_ids:
        if not cid.startswith("-"):
            print("[WARN] TELEGRAM_TEST_CHAT_ID missing; using first private TELEGRAM_CHAT_ID only.")
            return cid

    raise RuntimeError(
        "Required environment variable TELEGRAM_TEST_CHAT_ID is missing and "
        "no private chat id was found in TELEGRAM_CHAT_ID."
    )


def _split_chat_ids(value):
    if isinstance(value, str):
        return [cid.strip() for cid in value.split(",") if cid.strip()]
    if isinstance(value, list):
        return [str(cid).strip() for cid in value if str(cid).strip()]
    return [str(value).strip()]


def _chunks(text: str, limit: int = 4096):
    text = text or ""
    return [text[i:i + limit] for i in range(0, len(text), limit)]


def send_us_message(text, chat_id=None):
    """Send text follow-ups with the US Telegram bot, not the domestic bot."""
    token = _bot_token()
    target_ids = _split_chat_ids(chat_id or _test_chat_id())
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    success_all = True
    for cid in target_ids:
        for chunk in _chunks(text):
            response = requests.post(url, data={"chat_id": cid, "text": chunk}, timeout=90)
            response.raise_for_status()
            result = response.json()
            if not result.get("ok"):
                print(f"[ERROR] Telegram US message API error ({cid}): {result.get('description')}")
                success_all = False
    return success_all


def send_us_market_photo(photo_path, caption=None, chat_id=None, test_only: bool = True):
    """Send a single generated US market PNG.

    Safe default while testing: send only to TELEGRAM_TEST_CHAT_ID. Pass
    test_only=False for the production chat room.
    """
    if not os.path.exists(photo_path):
        print(f"[ERROR] Image to send does not exist: {photo_path}")
        return False

    token = _bot_token()
    target_ids = _split_chat_ids(chat_id or (_test_chat_id() if test_only else _default_chat_id()))
    url = f"https://api.telegram.org/bot{token}/sendPhoto"
    caption_text, followups = prepare_caption_and_followups(caption or "")

    success_all = True
    for cid in target_ids:
        print(f"[INFO] Telegram image send request (CHAT_ID: {cid}): {photo_path}")
        try:
            with open(photo_path, "rb") as f:
                files = {"photo": (os.path.basename(photo_path), f, "image/png")}
                data = {"chat_id": cid, "caption": caption_text if caption_text else ""}
                response = requests.post(url, data=data, files=files, timeout=90)
                response.raise_for_status()
                result = response.json()

            if result.get("ok"):
                print(f"[SUCCESS] Telegram US report sent (CHAT_ID: {cid})")
            else:
                print(f"[ERROR] Telegram API error ({cid}): {result.get('description')}")
                success_all = False
            for msg in followups:
                success_all = send_us_message(msg, chat_id=cid) and success_all
        except Exception as exc:
            print(f"[ERROR] Telegram send failed ({cid}): {exc}")
            success_all = False

    return success_all


if __name__ == "__main__":
    base_dir = os.path.dirname(os.path.abspath(__file__))
    test_img = os.path.join(base_dir, "us_market_summary.png")
    print("Manual send test...")
    send_us_market_photo(test_img, caption="[TEST] US market report")
