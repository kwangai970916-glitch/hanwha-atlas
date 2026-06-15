# -*- coding: utf-8 -*-
"""Generate a one-page domestic market close dashboard.

Safe default: generate the PNG only. Use --send-test to send only to
TELEGRAM_TEST_CHAT_ID. This script intentionally has no production room send
flag to avoid accidental uploads to the group chat.
"""

from __future__ import annotations

import argparse
import io
import os
import sys
from datetime import datetime

if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
if sys.stderr.encoding != "utf-8":
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

import auto_data_fetcher
import close_report_renderer
import send_telegram_tele


def run_close_dashboard(send_test: bool = False) -> str | None:
    print("==================================================")
    print("금일장 요약 대시보드 생성 시작")
    print(f"현재 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("==================================================")

    base_dir = os.path.dirname(os.path.abspath(__file__))
    today_str = datetime.now().strftime("%Y%m%d")
    output_dir = os.path.join(base_dir, "output", today_str)
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "tele_close_dashboard.png")

    try:
        report_data = auto_data_fetcher.get_complete_report_data(
            history_path=os.path.join(base_dir, "adr_history.json")
        )
        image_path = close_report_renderer.render_close_dashboard(report_data, output_path)
        print(f"[SUCCESS] 대시보드 생성 완료: {image_path}")

        if send_test:
            print("[SEND] 개인 테스트 채팅방으로만 발송합니다.")
            send_telegram_tele.send_close_test_report(image_path)
        else:
            print("[SAFE] 텔레그램 발송 생략. 개인 테스트 발송은 --send-test 사용.")

        return image_path
    except Exception as exc:
        print(f"[ERROR] 금일장 요약 대시보드 생성 실패: {exc}")
        return None


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Domestic market close dashboard generator")
    parser.add_argument(
        "--send-test",
        action="store_true",
        help="Send generated dashboard only to TELEGRAM_TEST_CHAT_ID.",
    )
    args = parser.parse_args()
    run_close_dashboard(send_test=args.send_test)

