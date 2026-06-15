# -*- coding: utf-8 -*-
"""
마감 시황 스타일 마감시황 - 데이터 수집기
pykrx 기반. 기존 코드 일절 수정 없음.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

try:
    from pykrx import stock as krx
    PYKRX_OK = True
except ImportError:
    PYKRX_OK = False
    print("[WARN] pykrx 미설치 → fallback 데이터 사용")


# ── 날짜 헬퍼 ──────────────────────────────────────────────
def _today_str() -> str:
    return datetime.now().strftime("%Y%m%d")


def _prev_bday(date_str: str) -> str:
    dt = datetime.strptime(date_str, "%Y%m%d")
    step = 1
    while True:
        prev = dt - timedelta(days=step)
        if prev.weekday() < 5:
            return prev.strftime("%Y%m%d")
        step += 1


# ── 섹터 인덱스 코드 (KRX 업종) ────────────────────────────
SECTOR_CODES = {
    "반도체": "1028",
    "전기전자": "1008",
    "운수장비": "1014",
    "조선": "1024",
    "금융": "1016",
    "건설": "1006",
    "의약품": "1009",
    "화학": "1011",
}


def fetch_close(date: str | None = None) -> dict[str, Any]:
    """마감 데이터 수집 메인 함수. date=YYYYMMDD (미입력시 오늘)."""
    today = date or _today_str()
    if not PYKRX_OK:
        return _fallback(today)
    try:
        return _from_pykrx(today)
    except Exception as exc:
        print(f"[WARN] pykrx 수집 실패: {exc} → fallback")
        return _fallback(today)


def _from_pykrx(today: str) -> dict[str, Any]:
    prev = _prev_bday(today)

    # ── 지수 ──
    def _index(code: str, d: str) -> float:
        df = krx.get_index_ohlcv_by_date(d, d, code)
        return float(df["종가"].iloc[-1]) if not df.empty else 0.0

    kospi_close  = _index("1001", today)
    kospi_prev   = _index("1001", prev)
    kosdaq_close = _index("2001", today)
    kosdaq_prev  = _index("2001", prev)

    kospi_chg  = (kospi_close  / kospi_prev  - 1) * 100 if kospi_prev  else 0.0
    kosdaq_chg = (kosdaq_close / kosdaq_prev - 1) * 100 if kosdaq_prev else 0.0

    # ── 투자자 수급 (억원) ──
    iv = krx.get_market_trading_value_by_date(today, today, "KOSPI")
    individual = foreign = institution = 0
    if not iv.empty:
        row = iv.iloc[-1]
        for col in iv.columns:
            c = str(col).replace(" ", "")
            if "개인" in c:
                individual = int(row[col] / 1_000_000)
            elif "외국인" in c and "합계" in c:
                foreign = int(row[col] / 1_000_000)
            elif "기관" in c and "합계" in c:
                institution = int(row[col] / 1_000_000)

    # ── 상승/하락 종목 수 (KOSPI) ──
    up = down = 0
    try:
        tickers = krx.get_market_ticker_list(today, market="KOSPI")
        for t in tickers[:300]:
            df = krx.get_market_ohlcv_by_date(today, today, t)
            if not df.empty:
                chg = float(df["등락률"].iloc[-1])
                if chg > 0:
                    up += 1
                elif chg < 0:
                    down += 1
    except Exception:
        pass

    # ── 섹터 등락 ──
    sector_returns: list[dict] = []
    for name, code in SECTOR_CODES.items():
        try:
            s_now  = _index(code, today)
            s_prev = _index(code, prev)
            if s_now and s_prev:
                sector_returns.append({
                    "sector": name,
                    "change": round((s_now / s_prev - 1) * 100, 2),
                })
        except Exception:
            pass
    sector_returns.sort(key=lambda x: x["change"], reverse=True)

    # ── OHLCV (장중 흐름 근사) ──
    def _ohlcv(code: str) -> dict:
        df = krx.get_index_ohlcv_by_date(today, today, code)
        if df.empty:
            return {}
        r = df.iloc[-1]
        return {
            "open": float(r["시가"]),
            "high": float(r["고가"]),
            "low":  float(r["저가"]),
            "close": float(r["종가"]),
        }

    return {
        "date": today,
        "kospi": {
            "close": round(kospi_close, 2),
            "prev":  round(kospi_prev, 2),
            "chg_pct": round(kospi_chg, 2),
            **_ohlcv("1001"),
        },
        "kosdaq": {
            "close": round(kosdaq_close, 2),
            "prev":  round(kosdaq_prev, 2),
            "chg_pct": round(kosdaq_chg, 2),
            **_ohlcv("2001"),
        },
        "investor": {
            "individual": individual,
            "foreign":    foreign,
            "institution": institution,
        },
        "breadth": {"up": up, "down": down},
        "sector_returns": sector_returns,
    }


def _fallback(today: str) -> dict[str, Any]:
    return {
        "date": today,
        "kospi":  {"close": 7822.24, "prev": 7498.00, "chg_pct": 4.32,
                   "open": 7600.0, "high": 7850.0, "low": 7580.0},
        "kosdaq": {"close": 1207.34, "prev": 1199.22, "chg_pct": 0.68,
                   "open": 1195.0, "high": 1212.0, "low": 1190.0},
        "investor": {"individual": 28710, "foreign": -35055, "institution": 6193},
        "breadth": {"up": 147, "down": 738},
        "sector_returns": [
            {"sector": "반도체",  "change": 6.2},
            {"sector": "조선",    "change": 4.1},
            {"sector": "운수장비","change": 3.5},
            {"sector": "화학",    "change": -0.8},
            {"sector": "건설",    "change": -1.2},
        ],
    }
