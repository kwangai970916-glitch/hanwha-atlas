# -*- coding: utf-8 -*-
"""
한화손보 운용본부 — 장전 시황 리포트 실행기
실행 시각: 매일 07:00 (Windows 작업 스케줄러 등록 권장)

파이프라인:
  1. 미국 마감 데이터 수집 (fetch_us_market_data + yfinance)
  2. Claude API → 한화손보 형식 분석 텍스트 생성 (hanwha_report_text)
  3. Playwright → PNG 렌더링 (hanwha_report_renderer)
  4. 텔레그램 발송 (send_telegram_tele)

필요 환경변수 (.env):
  ANTHROPIC_API_KEY, TELEGRAM_TELE_BOT_TOKEN,
  TELEGRAM_CHAT_ID, TELEGRAM_TEST_CHAT_ID
"""
from __future__ import annotations

import argparse
import io
import os
import sys
from datetime import datetime
from pathlib import Path

# ── 인코딩 픽스 ──────────────────────────────────────────────────────────
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

# ── 실행 경로를 스크립트 폴더로 고정 ────────────────────────────────────
HERE = Path(__file__).resolve().parent
os.chdir(HERE)

from report_config import load_env_file, get_env, require_env
from hanwha_report_text import generate_report_sections
# PNG 렌더러는 playwright 의존 — 미설치 환경(서버 배포)에서는 PNG 생략하고
# 텍스트 리포트(sections)만 생성한다.
try:
    from hanwha_report_renderer import render_hanwha_report
except Exception as _render_err:
    render_hanwha_report = None
    print(f"[WARN] PNG 렌더러 비활성({_render_err}) → PNG 생략 모드")

load_env_file()


# ── 데이터 수집 ───────────────────────────────────────────────────────────
def _collect_premarket_data() -> dict:
    """장전 데이터: 미국 마감 지수 + 금리/환율 + 심리지표."""
    data: dict = {
        "date":       datetime.now().strftime("%Y.%m.%d"),
        "us_indices": {},
        "rates":      {},
        "sentiment":  {},
        "kr_indices": {},
        "events":     [],
    }

    # 1) 미국 지수 (fetch_us_market_data.py 재사용)
    try:
        from fetch_us_market_data import fetch_us_market_data
        raw = fetch_us_market_data()
        for idx in raw.get("indices", []):
            name = idx.get("name", "")
            chg  = float(idx.get("change", 0))
            data["us_indices"][name] = {
                "close":      float(idx.get("close", 0)),
                "change":     chg,
                "change_str": f"{chg:+.2f}%",
            }
        # 미국 개별주 무버 + 간밤 내러티브 — 메인 스토리 합성용(숫자 나열 방지의 핵심 재료)
        data["us_movers"] = (raw.get("top_gainers") or [])[:8]
        if raw.get("analysis_text"):
            data["us_narrative"] = str(raw["analysis_text"])[:1400]
        print(f"[장전] 미국 지수/무버 수집 완료 (지수 {len(data['us_indices'])}개, 무버 {len(data['us_movers'])}개)")
    except Exception as e:
        # 임의 수치 주입 금지 — 비우면 프롬프트가 '데이터 없음'으로 표기하고
        # LLM이 '데이터 부족으로 판단 유보'를 명시하도록 설계되어 있다.
        print(f"[WARN] 미국 지수 수집 실패: {e} → 데이터 없음으로 표기")
        data["us_indices"] = {}

    # 2) 금리 / 환율 / VIX (yfinance) — period 5d로 빈 응답 방지
    try:
        import yfinance as yf

        def _last_close(ticker: str) -> float | None:
            for period in ("5d", "1mo"):
                try:
                    h = yf.Ticker(ticker).history(period=period)
                    if not h.empty:
                        return float(h["Close"].dropna().iloc[-1])
                except Exception:
                    pass
            return None

        us10y  = _last_close("^TNX")
        dxy    = _last_close("DX-Y.NYB")
        usdkrw = _last_close("USDKRW=X")
        vix    = _last_close("^VIX")
        # 국내 지수 직전 종가 — grounding 핵심(이게 없으면 LLM 이 코스피 레벨을 학습통념으로 환각).
        kospi_lvl  = _last_close("^KS11")
        kosdaq_lvl = _last_close("^KQ11")
        if kospi_lvl:  data["kr_indices"]["kospi"]  = {"close": round(kospi_lvl, 2)}
        if kosdaq_lvl: data["kr_indices"]["kosdaq"] = {"close": round(kosdaq_lvl, 2)}

        if us10y:  data["rates"]["us10y"]   = round(us10y, 3)
        if dxy:    data["rates"]["dxy"]     = round(dxy,   2)
        if usdkrw: data["rates"]["usdkrw"]  = round(usdkrw, 1)
        if vix:
            data["sentiment"]["vix"]    = round(vix, 2)
        print("[장전] 금리/환율/VIX 수집 완료")
    except Exception as e:
        print(f"[WARN] yfinance 수집 실패: {e}")

    # 2-1) yfinance가 못 채운 매크로는 네이버 금융 폴백으로 보완
    try:
        missing = [k for k in ("us10y", "dxy", "usdkrw") if not data["rates"].get(k)]
        if not data["sentiment"].get("vix"):
            missing.append("vix")
        if missing:
            from naver_macro import fetch_macro_fallback
            nm = fetch_macro_fallback(missing)
            for k in ("us10y", "dxy", "usdkrw"):
                if k in nm:
                    data["rates"][k] = nm[k]
            if "vix" in nm:
                data["sentiment"]["vix"] = nm["vix"]
            if nm:
                print(f"[장전] 네이버 매크로 폴백 보완: {sorted(nm)}")
    except Exception as e:
        print(f"[WARN] 네이버 매크로 폴백 실패: {e}")
    if data["rates"].get("usdkrw"):
        data["sentiment"]["usdkrw"] = data["rates"]["usdkrw"]

    # 3) Fear & Greed Index (alternative.me)
    try:
        import requests as _req
        fg_resp = _req.get("https://api.alternative.me/fng/?limit=1", timeout=8)
        if fg_resp.ok:
            fg_val = int(fg_resp.json()["data"][0]["value"])
            data["sentiment"]["fear_greed"] = fg_val
            print(f"[장전] Fear & Greed: {fg_val}")
    except Exception as e:
        print(f"[WARN] Fear&Greed 수집 실패: {e}")

    return data


# ── 텔레그램 발송 ─────────────────────────────────────────────────────────
def _send(png_path: str, sections: dict, test_only: bool) -> None:
    try:
        import requests
        token   = require_env("TELEGRAM_TELE_BOT_TOKEN")
        chat_id = (
            get_env("TELEGRAM_TEST_CHAT_ID")
            if test_only
            else require_env("TELEGRAM_CHAT_ID")
        )
        caption = (
            f"🏢 한화손보 운용본부 | 장전 시황\n"
            f"{datetime.now():%Y-%m-%d %H:%M} 기준\n\n"
            f"{sections.get('title','')}"
        )
        with open(png_path, "rb") as f:
            resp = requests.post(
                f"https://api.telegram.org/bot{token}/sendPhoto",
                data={"chat_id": chat_id, "caption": caption},
                files={"photo": f},
                timeout=30,
            )
        if resp.ok:
            print(f"[장전] 텔레그램 발송 완료 → chat_id={chat_id}")
        else:
            print(f"[WARN] 텔레그램 응답 오류: {resp.status_code} {resp.text[:120]}")
    except Exception as e:
        print(f"[WARN] 텔레그램 발송 실패: {e}")


# ── 메인 ──────────────────────────────────────────────────────────────────
def main(send: bool = False, test_only: bool = True) -> None:
    print("=" * 52)
    print(f"[장전] 한화손보 운용본부 시황 리포트 시작")
    print(f"[장전] {datetime.now():%Y-%m-%d %H:%M:%S}")
    print("=" * 52)

    # 1. 데이터 수집
    market_data = _collect_premarket_data()

    # 2. Claude API 텍스트 생성
    print("[장전] Claude API 분석 텍스트 생성 중...")
    sections = generate_report_sections("premarket", market_data)
    print(f"[장전] 제목: {sections.get('title')} / 스탠스: {sections.get('stance')}")

    # 3. Playwright PNG 렌더링
    if render_hanwha_report is None:
        png_path = ""
        print("[장전] PNG 렌더러 비활성 → 텍스트 리포트만 생성")
    else:
        print("[장전] PNG 렌더링 중...")
        png_path = render_hanwha_report("premarket", sections, market_data)
        print(f"[장전] 저장 완료: {png_path}")

    # 4. 텔레그램 발송 (opt-in)
    if send:
        _send(png_path, sections, test_only=test_only)
    else:
        print("[장전] 텔레그램 발송 생략 (--send 옵션 없음)")

    print("[장전] 완료.")
    return png_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="한화손보 장전 시황 리포트")
    parser.add_argument("--send", action="store_true", help="텔레그램 발송")
    parser.add_argument("--live", action="store_true", help="실채널 발송 (기본: 테스트 채팅방)")
    args = parser.parse_args()
    main(send=args.send, test_only=not args.live)
