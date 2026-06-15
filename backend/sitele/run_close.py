# -*- coding: utf-8 -*-
"""
한화손보 운용본부 — 장마감 시황 리포트 실행기
실행 시각: 매일 16:30 (Windows 작업 스케줄러 등록 권장)

파이프라인:
  1. pykrx 종가 데이터 수집 (kang_close_data)
  2. 미국 선물 / 심리지표 보완 (yfinance)
  3. Claude API → 한화손보 형식 분석 텍스트 생성 (hanwha_report_text)
  4. Playwright → PNG 렌더링 (hanwha_report_renderer)
  5. 텔레그램 발송 (opt-in)
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

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
def _collect_close_data() -> dict:
    """장마감 데이터.

    소스 우선순위:
      ① auto_data_fetcher(네이버 실시간) — KOSPI/KOSDAQ 지수·섹터·등락·뉴스·무버
      ② kang_close_data(pykrx 당일 종가) — 투자자 수급(외인/기관/개인) 보조
      ③ yfinance — 미국 선물·USD/KRW 보조 (실패 시 None)
      ④ VKOSPI — 네이버 polling (장중 실시간, 마감 후 stale 캐시)
    """
    now = datetime.now()

    # ── ① auto_data_fetcher (PRIMARY — 네이버 실시간) ─────────────────
    try:
        import auto_data_fetcher as adf
        raw = adf.get_complete_report_data()
        print("[장마감] auto_data_fetcher 실시간 수집 성공")
    except Exception as e:
        print(f"[WARN] auto_data_fetcher 수집 실패: {e}")
        raw = {}

    # 지수: 네이버 실시간 우선
    mi = raw.get("marketIndices", {})
    kp = mi.get("kospi", {})
    kq = mi.get("kosdaq", {})

    def _idx(d: dict) -> dict:
        c = float(d.get("index", d.get("close", 0)) or 0)
        ch = float(d.get("change", 0) or 0)
        prev = round(c / (1 + ch / 100), 2) if (ch != -100 and c) else 0.0
        return {"close": round(c, 2), "prev": prev, "chg_pct": round(ch, 2)}

    kospi  = _idx(kp)
    kosdaq = _idx(kq)

    # 섹터, 등락종목수, 무버, 뉴스 — 전부 네이버
    sectors = [
        {"sector": s["sector"], "change": round(float(s["change"]), 2)}
        for s in raw.get("sectorReturns", []) if "sector" in s and "change" in s
    ]
    sectors.sort(key=lambda x: x["change"], reverse=True)

    breadth = {
        "up":   int(raw.get("kospiAdvance",  0)),
        "down": int(raw.get("kospiDecline",  0)),
    }

    gainers = [
        {"name": m.get("name", ""), "change": round(float(m.get("change", 0)), 2), "close": int(m.get("close", 0))}
        for m in raw.get("topGainers", [])[:5]
    ]
    losers = [
        {"name": m.get("name", ""), "change": round(float(m.get("change", 0)), 2), "close": int(m.get("close", 0))}
        for m in raw.get("topLosers", [])[:5]
    ]
    top_movers = {"gainers": gainers, "losers": losers}
    news = [
        n.get("title", "") if isinstance(n, dict) else str(n)
        for n in raw.get("newsHeadlines", [])[:6]
    ]

    print(f"[장마감] KOSPI {kospi['close']:,.2f} ({kospi['chg_pct']:+.2f}%), KOSDAQ {kosdaq['close']:,.2f} ({kosdaq['chg_pct']:+.2f}%)")
    print(f"[장마감] 상승 {breadth['up']} / 하락 {breadth['down']} 종목 | 뉴스 {len(news)}건")

    # ── ② kang_close_data (투자자 수급 보조) ──────────────────────────
    investor = {"individual": 0, "foreign": 0, "institution": 0}
    try:
        import kang_close_data as kcd
        kang = kcd.fetch_close()
        inv = kang.get("investor")
        if inv and any(inv.values()):
            investor = inv
            print(f"[장마감] pykrx 수급: 외인 {investor.get('foreign',0)}억 / 기관 {investor.get('institution',0)}억")
        # 지수가 네이버에서 못 왔으면 pykrx로 보완
        if not kospi["close"] and kang.get("kospi"):
            kp2 = kang["kospi"]
            kospi  = {"close": float(kp2.get("close",0)), "prev": float(kp2.get("prev",0)), "chg_pct": float(kp2.get("chg_pct",0))}
        if not sectors and kang.get("sector_returns"):
            sectors = kang["sector_returns"]
        if not breadth["up"] and kang.get("breadth"):
            breadth = kang["breadth"]
    except Exception as e:
        print(f"[WARN] kang_close_data 수집 실패(수급 없음): {e}")

    # ── GICS 11 대분류 섹터 (홈탭 히트맵과 동일 소스로 통일) ──────────────
    try:
        import sys as _s
        _be = str(Path(__file__).resolve().parents[1])
        if _be not in _s.path:
            _s.path.insert(0, _be)
        from app.price_service import get_market_heatmap
        _hm = get_market_heatmap()
        _gics = [{"sector": s["sector"], "change": s["change"]} for s in (_hm.get("sectors") or []) if s.get("sector")]
        if _gics:
            _gics.sort(key=lambda x: x["change"], reverse=True)
            sectors = _gics
            print(f"[장마감] GICS 11 대분류 섹터 {len(_gics)}개 적용")
    except Exception as e:
        print(f"[WARN] GICS 11 섹터 수집 실패(기존 섹터 유지): {e}")

    # ── ③ yfinance 미국 선물/환율 (보조) ─────────────────────────────
    us_futures: dict = {}
    sentiment:  dict = {}
    try:
        import yfinance as yf
        def _lc(t: str):
            for period in ("5d", "1mo"):
                try:
                    h = yf.Ticker(t).history(period=period)
                    if not h.empty:
                        return float(h["Close"].dropna().iloc[-1])
                except Exception:
                    pass
            return None
        nq_fut = _lc("NQ=F")
        es_fut = _lc("ES=F")
        usdkrw = _lc("USDKRW=X")
        vix    = _lc("^VIX")
        if nq_fut: us_futures["나스닥100 선물"] = f"{nq_fut:,.0f}"
        if es_fut: us_futures["S&P500 선물"]   = f"{es_fut:,.0f}"
        if usdkrw: sentiment["usdkrw"] = round(usdkrw, 1)
        if vix:    sentiment["vix"]    = round(vix, 2)
    except Exception as e:
        print(f"[WARN] yfinance 실패: {e}")

    # ── 원/달러·VIX 네이버 폴백 (yfinance 실패/누락 대비) ──────────────
    try:
        import requests as _rq, re as _re
        if not sentiment.get("usdkrw"):
            h = _rq.get("https://finance.naver.com/marketindex/",
                        headers={"User-Agent": "Mozilla/5.0"}, timeout=8)
            h.encoding = "euc-kr"
            m = _re.search(r'USD.*?<span class="value">([\d,.]+)</span>', h.text, _re.S)
            if m:
                sentiment["usdkrw"] = float(m.group(1).replace(",", ""))
                print(f"[장마감] 원/달러(네이버): {sentiment['usdkrw']}")
        if not sentiment.get("vix"):
            v = _rq.get("https://polling.finance.naver.com/api/realtime/worldstock/index/.VIX",
                        headers={"User-Agent": "Mozilla/5.0", "Referer": "https://finance.naver.com/"}, timeout=8)
            ds = (v.json().get("datas") or [])
            if ds:
                cp = ds[0].get("closePrice") or ds[0].get("closePriceRaw")
                if cp:
                    sentiment["vix"] = round(float(str(cp).replace(",", "")), 2)
                    print(f"[장마감] VIX(네이버): {sentiment['vix']}")
    except Exception as e:
        print(f"[WARN] 원/달러·VIX 네이버 폴백 실패: {e}")

    # ── ④ VKOSPI (네이버 polling → pykrx 일봉 종가 순차 시도) ────────
    try:
        import sys as _sys, datetime as _dt
        _be = str(Path(__file__).resolve().parents[1] / "app")
        if _be not in _sys.path:
            _sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from app.price_service import get_index as _get_index
        vkospi_q = _get_index("VKOSPI")
        if vkospi_q.get("price"):
            sentiment["vkospi"] = round(float(vkospi_q["price"]), 2)
            print(f"[장마감] VKOSPI(polling): {sentiment['vkospi']}")
        else:
            # 장외 시간 → pykrx 최근 일봉 종가 fallback
            try:
                from pykrx import stock as _pykrx
                _today = _dt.date.today().strftime("%Y%m%d")
                _from  = (_dt.date.today() - _dt.timedelta(days=10)).strftime("%Y%m%d")
                _df = _pykrx.get_index_ohlcv(_from, _today, "VKOSPI")
                if not _df.empty:
                    # pykrx 컬럼명 인코딩 문제 → iloc로 종가(3번째 컬럼) 직접 접근
                    _vk = float(_df.iloc[-1, 3])   # 시가·고가·저가·종가·거래량 순
                    sentiment["vkospi"] = round(_vk, 2)
                    print(f"[장마감] VKOSPI(pykrx fallback): {sentiment['vkospi']}")
            except Exception as _e2:
                print(f"[WARN] VKOSPI pykrx fallback 실패: {_e2}")
    except Exception as e:
        print(f"[WARN] VKOSPI 수집 실패: {e}")

    # ── Fear & Greed ──────────────────────────────────────────────────
    try:
        import requests as _req
        fg = _req.get("https://api.alternative.me/fng/?limit=1", timeout=8)
        if fg.ok:
            sentiment["fear_greed"] = int(fg.json()["data"][0]["value"])
            print(f"[장마감] Fear & Greed: {sentiment['fear_greed']}")
    except Exception as e:
        print(f"[WARN] Fear&Greed 수집 실패: {e}")

    # ── 지수 일중 흐름 (fchart 분봉 → 일봉 폴백) — KOSPI/KOSDAQ 선그래프용 ──
    index_chart = {}
    try:
        import requests as _rq, xml.etree.ElementTree as _ET
        def _idx_series(sym, prev):
            for tf, cnt in (("minute", 220), ("day", 60)):
                try:
                    r = _rq.get("https://fchart.stock.naver.com/sise.nhn",
                                params={"symbol": sym, "timeframe": tf, "count": cnt, "requestType": 0},
                                headers={"User-Agent": "Mozilla/5.0", "Referer": "https://finance.naver.com/"}, timeout=8)
                    root = _ET.fromstring(r.text)
                    closes = []
                    for it in root.iter("item"):
                        p = it.attrib.get("data", "").split("|")
                        if len(p) >= 5:
                            try: closes.append(round(float(p[4]), 2))
                            except Exception: pass
                    if len(closes) >= 5:
                        return {"points": closes if tf == "minute" else closes[-60:],
                                "intraday": tf == "minute", "prev": prev}
                except Exception:
                    continue
            return None
        ks = _idx_series("KOSPI", kospi.get("prev"))
        kq = _idx_series("KOSDAQ", kosdaq.get("prev"))
        if ks: index_chart["kospi"] = ks
        if kq: index_chart["kosdaq"] = kq
        print(f"[장마감] 지수 흐름: KOSPI {'분봉' if ks and ks['intraday'] else '일봉' if ks else '없음'} / KOSDAQ {'분봉' if kq and kq['intraday'] else '일봉' if kq else '없음'}")
    except Exception as e:
        print(f"[WARN] 지수 흐름 수집 실패: {e}")

    return {
        "date": now.strftime("%Y.%m.%d"),
        "kr_indices": {
            "kospi":  {"close": kospi["close"], "prev": kospi["prev"], "chg_pct": kospi["chg_pct"]},
            "kosdaq": {"close": kosdaq["close"], "prev": kosdaq["prev"], "chg_pct": kosdaq["chg_pct"]},
        },
        "investor":       investor,
        "breadth":        breadth,
        "sectors":        sectors,
        "sector_returns": sectors,
        "us_futures":     us_futures,
        "sentiment":      sentiment,
        "top_movers":     top_movers,
        "news":           news,
        "events_tomorrow": [],
        "index_chart":    index_chart,
    }


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
            f"🏢 한화손보 운용본부 | 장마감 시황\n"
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
            print(f"[장마감] 텔레그램 발송 완료 → chat_id={chat_id}")
        else:
            print(f"[WARN] 텔레그램 응답 오류: {resp.status_code} {resp.text[:120]}")
    except Exception as e:
        print(f"[WARN] 텔레그램 발송 실패: {e}")


# ── 메인 ──────────────────────────────────────────────────────────────────
def main(send: bool = False, test_only: bool = True) -> None:
    print("=" * 52)
    print(f"[장마감] 한화손보 운용본부 시황 리포트 시작")
    print(f"[장마감] {datetime.now():%Y-%m-%d %H:%M:%S}")
    print("=" * 52)

    market_data = _collect_close_data()
    kospi_close = market_data["kr_indices"]["kospi"]["close"]
    kospi_chg   = market_data["kr_indices"]["kospi"]["chg_pct"]
    print(f"[장마감] KOSPI {kospi_close:,.2f} ({kospi_chg:+.2f}%)")

    print("[장마감] Claude API 분석 텍스트 생성 중...")
    sections = generate_report_sections("close", market_data)
    print(f"[장마감] 제목: {sections.get('title')} / 스탠스: {sections.get('stance')}")

    if render_hanwha_report is None:
        png_path = ""
        print("[장마감] PNG 렌더러 비활성 → 텍스트 리포트만 생성")
    else:
        print("[장마감] PNG 렌더링 중...")
        png_path = render_hanwha_report("close", sections, market_data)
        print(f"[장마감] 저장 완료: {png_path}")

    if send:
        _send(png_path, sections, test_only=test_only)
    else:
        print("[장마감] 텔레그램 발송 생략 (--send 옵션 없음)")

    print("[장마감] 완료.")
    return png_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="한화손보 장마감 시황 리포트")
    parser.add_argument("--send", action="store_true", help="텔레그램 발송")
    parser.add_argument("--live", action="store_true", help="실채널 발송 (기본: 테스트 채팅방)")
    args = parser.parse_args()
    main(send=args.send, test_only=not args.live)
