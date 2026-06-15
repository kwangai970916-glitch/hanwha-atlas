# -*- coding: utf-8 -*-
"""Telegram sender for the domestic market report.

Secrets are intentionally not stored in source code. Set these in `.env` or
Windows environment variables:
- TELEGRAM_TELE_BOT_TOKEN
- TELEGRAM_CHAT_ID
- TELEGRAM_TEST_CHAT_ID
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime

import requests

from report_config import require_env

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

TELEGRAM_CAPTION_LIMIT = 1024
TELEGRAM_MESSAGE_LIMIT = 4096


def _bot_token() -> str:
    return require_env("TELEGRAM_TELE_BOT_TOKEN")


def _chat_id() -> str:
    return require_env("TELEGRAM_CHAT_ID")


def _test_chat_id() -> str:
    return require_env("TELEGRAM_TEST_CHAT_ID")


def _split_chat_ids(value):
    if isinstance(value, str):
        return [cid.strip() for cid in value.split(",") if cid.strip()]
    if isinstance(value, list):
        return [str(cid).strip() for cid in value if str(cid).strip()]
    return [str(value).strip()] if value else []


def _chunks(text: str, limit: int):
    text = text or ""
    return [text[i:i + limit] for i in range(0, len(text), limit)]


def prepare_caption_and_followups(text: str):
    """Return a Telegram-safe image caption plus follow-up messages.

    Telegram photo/media captions are limited to 1024 chars. Instead of
    silently cutting content, keep the first 1024 chars as caption and return
    the remainder split into normal 4096-char text messages.
    """
    text = text or ""
    caption = text[:TELEGRAM_CAPTION_LIMIT]
    remainder = text[TELEGRAM_CAPTION_LIMIT:]
    return caption, _chunks(remainder, TELEGRAM_MESSAGE_LIMIT)


def send_message(text, chat_id=None):
    token = _bot_token()
    target_ids = _split_chat_ids(chat_id or _chat_id())
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    success_all = True
    for cid in target_ids:
        for chunk in _chunks(text, TELEGRAM_MESSAGE_LIMIT):
            response = requests.post(url, data={"chat_id": cid, "text": chunk}, timeout=90)
            response.raise_for_status()
            result = response.json()
            if not result.get("ok"):
                print(f"[ERROR] Telegram message API error ({cid}): {result.get('description')}")
                success_all = False
    return success_all


def send_photo(file_path, caption=None, chat_id=None):
    """Send a single PNG file to Telegram. Long captions continue as messages."""
    token = _bot_token()
    target_ids = _split_chat_ids(chat_id or _chat_id())
    url = f"https://api.telegram.org/bot{token}/sendPhoto"
    caption_text, followups = prepare_caption_and_followups(caption or "")
    success_all = True

    for cid in target_ids:
        with open(file_path, "rb") as f_handle:
            files = {"photo": (os.path.basename(file_path), f_handle, "image/png")}
            data = {"chat_id": cid}
            if caption_text:
                data["caption"] = caption_text
            response = requests.post(url, data=data, files=files, timeout=120)

        response.raise_for_status()
        result = response.json()
        if not result.get("ok"):
            print(f"[ERROR] Telegram photo API error ({cid}): {result.get('description')}")
            success_all = False
        for msg in followups:
            success_all = send_message(msg, chat_id=cid) and success_all
    return success_all


def send_media_group(file_paths, caption=None, chat_id=None):
    """Send multiple PNG files as a Telegram media group. Long caption continues as messages."""
    token = _bot_token()
    target_ids = _split_chat_ids(chat_id or _chat_id())
    url = f"https://api.telegram.org/bot{token}/sendMediaGroup"
    caption_text, followups = prepare_caption_and_followups(caption or "")
    success_all = True

    for cid in target_ids:
        media = []
        files = {}
        opened_files = []
        try:
            for i, fp in enumerate(file_paths):
                attach_name = f"photo{i}"
                entry = {"type": "photo", "media": f"attach://{attach_name}"}
                if i == 0 and caption_text:
                    entry["caption"] = caption_text
                media.append(entry)

                f_handle = open(fp, "rb")
                opened_files.append(f_handle)
                files[attach_name] = (os.path.basename(fp), f_handle, "image/png")

            data = {"chat_id": cid, "media": json.dumps(media, ensure_ascii=False)}
            response = requests.post(url, data=data, files=files, timeout=120)
            response.raise_for_status()
            result = response.json()
            if not result.get("ok"):
                print(f"[ERROR] Telegram media API error ({cid}): {result.get('description')}")
                success_all = False
            for msg in followups:
                success_all = send_message(msg, chat_id=cid) and success_all
        finally:
            for f in opened_files:
                f.close()
    return success_all


def send_morning_tele_report(output_dir, test_only: bool = True):
    """Send today's three generated domestic report images.

    Safe default while testing: send only to TELEGRAM_TEST_CHAT_ID. Pass
    test_only=False only for the production chat room.
    """
    today = datetime.now().strftime("%Y-%m-%d")
    pages = ["tele_report_page1.png", "tele_report_page2.png", "tele_report_page3.png"]
    file_paths = []

    for page_name in pages:
        file_path = os.path.join(output_dir, page_name)
        if os.path.exists(file_path):
            file_paths.append(file_path)
        else:
            print(f"[WARN] Missing report image: {page_name}")

    if not file_paths:
        print("[ERROR] No report images exist to send.")
        return False

    chat_id = _test_chat_id() if test_only else _chat_id()
    mode = "private TEST" if test_only else "production"
    print(f"[INFO] Telegram media group send start ({today}, {mode}) - {len(file_paths)} files")
    try:
        return bool(send_media_group(file_paths, caption=f"?? ?? ???? ({today})", chat_id=chat_id))
    except Exception as exc:
        print(f"[ERROR] Telegram send failed: {exc}")
        return False


def send_close_test_report(image_path):
    """Send the close dashboard to the private test chat only."""
    today = datetime.now().strftime("%Y-%m-%d")
    if not os.path.exists(image_path):
        print(f"[ERROR] Close dashboard image does not exist: {image_path}")
        return False

    print(f"[INFO] Telegram private test send start ({today}) - {image_path}")
    try:
        ok = send_photo(
            image_path,
            caption=f"??? ?? ???? TEST ({today})",
            chat_id=_test_chat_id(),
        )
        if ok:
            print("[SUCCESS] Telegram private test send complete")
        return bool(ok)
    except Exception as exc:
        print(f"[ERROR] Telegram private test send failed: {exc}")
        return False


if __name__ == "__main__":
    base_dir = os.path.dirname(os.path.abspath(__file__))
    today_str = datetime.now().strftime("%Y%m%d")
    output_dir = os.path.join(base_dir, "output", today_str)
    print(f"Manual send test target folder: {output_dir}")
    send_morning_tele_report(output_dir, test_only=True)
