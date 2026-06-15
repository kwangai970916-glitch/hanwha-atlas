"""클라우드(데이터센터 IP)에서 동작하는 무키 일봉 OHLCV 소스.

pykrx/KRX 는 클라우드 데이터센터 IP에서 차단(전종목/지수/펀더멘털 빈값·KeyError)되므로,
일봉 OHLCV 는 아래 순서로 취득한다. 모두 데이터센터에서 실측 동작 확인됨:
  1) 네이버 fchart  fchart.stock.naver.com/sise.nhn  (EUC-KR XML, 120봉 0.3s)
  2) 네이버 siseJson api.finance.naver.com/siseJson.naver (EUC-KR, 숫자배열)
  3) yfinance .KS/.KQ (글로벌, 한국 종목 정규화)

반환 스키마: [{"time":"YYYY-MM-DD","open","high","low","close","volume"}] (날짜 오름차순)
candles / backtest / idea_engine 가 공유한다.
"""
from __future__ import annotations

import datetime as dt
import re
from typing import Dict, List

import requests

_HEADERS = {"User-Agent": "Mozilla/5.0", "Referer": "https://finance.naver.com/"}
_TIMEOUT = 8

# 지수 심볼 매핑 (네이버 fchart 는 'KOSPI'/'KOSDAQ' 심볼을 지원)
_INDEX_NAVER = {"^KS11": "KOSPI", "^KQ11": "KOSDAQ", "KOSPI": "KOSPI", "KOSDAQ": "KOSDAQ"}
_INDEX_YAHOO = {"^KS11": "^KS11", "^KQ11": "^KQ11", "KOSPI": "^KS11", "KOSDAQ": "^KQ11"}

# 코드별 야후 접미사(.KS/.KQ) 해석 캐시 — 첫 조회 후 재사용
_SUFFIX_CACHE: Dict[str, str] = {}


def _is_code(symbol: str) -> bool:
    return bool(re.fullmatch(r"\d{6}", symbol or ""))


def _naver_fchart(symbol: str, count: int) -> List[Dict]:
    """네이버 fchart (EUC-KR XML). <item data="YYYYMMDD|O|H|L|C|V"/>."""
    url = (f"https://fchart.stock.naver.com/sise.nhn?symbol={symbol}"
           f"&timeframe=day&count={int(count)}&requestType=0")
    r = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT)
    out: List[Dict] = []
    for raw in re.findall(r'<item data="([^"]+)"', r.text):
        p = raw.split("|")
        if len(p) < 6:
            continue
        d = p[0]
        if len(d) < 8 or not d[:8].isdigit():
            continue
        try:
            out.append({
                "time": f"{d[:4]}-{d[4:6]}-{d[6:8]}",
                "open": float(p[1]), "high": float(p[2]), "low": float(p[3]),
                "close": float(p[4]), "volume": float(p[5] or 0),
            })
        except Exception:
            continue
    return out


def _naver_sisejson(code: str, start: str, end: str) -> List[Dict]:
    """네이버 siseJson (EUC-KR). [["YYYYMMDD",O,H,L,C,V,외인],...] 첫 행은 헤더."""
    import ast
    url = (f"https://api.finance.naver.com/siseJson.naver?symbol={code}"
           f"&requestType=1&startTime={start}&endTime={end}&timeframe=day")
    r = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT)
    r.encoding = "euc-kr"
    try:
        rows = ast.literal_eval(r.text.strip())
    except Exception:
        return []
    out: List[Dict] = []
    for row in rows:
        if not isinstance(row, (list, tuple)) or len(row) < 6:
            continue
        d = str(row[0])
        if len(d) < 8 or not d[:8].isdigit():  # 헤더행 skip
            continue
        try:
            out.append({
                "time": f"{d[:4]}-{d[4:6]}-{d[6:8]}",
                "open": float(row[1]), "high": float(row[2]), "low": float(row[3]),
                "close": float(row[4]), "volume": float(row[5] or 0),
            })
        except Exception:
            continue
    return out


def to_yahoo_ticker(symbol: str) -> str:
    """KR 6자리 코드 -> 야후 티커(.KS/.KQ). 지수는 ^KS11/^KQ11. 그 외는 그대로."""
    if symbol in _INDEX_YAHOO:
        return _INDEX_YAHOO[symbol]
    if _is_code(symbol):
        return symbol + _SUFFIX_CACHE.get(symbol, ".KS")
    return symbol


def _yfinance_ohlcv(symbol: str, count: int) -> List[Dict]:
    import yfinance as yf
    period = "2y" if count > 250 else ("1y" if count > 130 else ("6mo" if count > 60 else "3mo"))
    if symbol in _INDEX_YAHOO:
        candidates = [_INDEX_YAHOO[symbol]]
    elif _is_code(symbol):
        # 캐시된 접미사 우선, 없으면 .KS → .KQ 순서로 시도
        first = _SUFFIX_CACHE.get(symbol, ".KS")
        candidates = [symbol + first] + [symbol + s for s in (".KS", ".KQ") if symbol + s != symbol + first]
    else:
        candidates = [symbol]
    for tk in candidates:
        try:
            h = yf.Ticker(tk).history(period=period)
            if h is None or h.empty:
                continue
            if _is_code(symbol):
                _SUFFIX_CACHE[symbol] = ".KQ" if tk.endswith(".KQ") else ".KS"
            out: List[Dict] = []
            for idx, row in h.iterrows():
                try:
                    out.append({
                        "time": str(idx)[:10],
                        "open": float(row["Open"]), "high": float(row["High"]),
                        "low": float(row["Low"]), "close": float(row["Close"]),
                        "volume": float(row.get("Volume", 0) or 0),
                    })
                except Exception:
                    continue
            if out:
                return out
        except Exception:
            continue
    return []


def daily_ohlcv(symbol: str, count: int = 260) -> List[Dict]:
    """일봉 OHLCV(오름차순). 네이버 fchart → siseJson → yfinance 폴백.

    symbol: KR 6자리 코드, 지수(^KS11/^KQ11/KOSPI/KOSDAQ), 또는 야후 티커.
    count : 최근 거래일 수(봉 개수). 실패 시 빈 리스트.
    """
    naver_sym = _INDEX_NAVER.get(symbol, symbol)
    # 1) fchart (종목·지수 모두 지원)
    try:
        rows = _naver_fchart(naver_sym, count)
        if len(rows) >= 2:
            return rows
    except Exception:
        pass
    # 2) siseJson (종목 코드만)
    if _is_code(symbol):
        try:
            end = dt.date.today()
            start = end - dt.timedelta(days=int(count * 1.6) + 10)
            rows = _naver_sisejson(symbol, start.strftime("%Y%m%d"), end.strftime("%Y%m%d"))
            if len(rows) >= 2:
                return rows
        except Exception:
            pass
    # 3) yfinance
    try:
        return _yfinance_ohlcv(symbol, count)
    except Exception:
        return []
