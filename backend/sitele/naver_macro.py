# naver_macro.py
"""네이버 금융 무인증 API 매크로 폴백.

yfinance가 차단/레이트리밋으로 전멸하면 장전·장중 시황의 매크로 데이터
(환율·VIX·미10년물·DXY)가 통째로 비어 리포트 품질이 급락한다.
네이버 금융 공개 엔드포인트를 2차 소스로 사용해 그 구멍을 메운다.

- USDKRW / DXY : m.stock.naver.com front-api marketIndex (category=exchange)
- 미 10년물    : 동일 (category=bond, US10YT=RR)
- VIX          : api.stock.naver.com/index/.VIX/basic

전 항목 best-effort — 실패한 키는 결과 dict에서 빠진다(예외 전파 없음).
"""
from __future__ import annotations

from typing import Optional

_HEADERS = {"User-Agent": "Mozilla/5.0"}
_MARKET_INDEX_URL = "https://m.stock.naver.com/front-api/marketIndex/productDetail"
_WORLD_INDEX_URL = "https://api.stock.naver.com/index/{symbol}/basic"


def _num(s) -> Optional[float]:
    try:
        v = float(str(s).replace(",", ""))
        return v if v > 0 else None
    except (TypeError, ValueError):
        return None


def _market_index(category: str, reuters_code: str) -> Optional[float]:
    try:
        import requests

        r = requests.get(
            _MARKET_INDEX_URL,
            params={"category": category, "reutersCode": reuters_code},
            headers=_HEADERS, timeout=8,
        )
        if r.ok:
            return _num((r.json().get("result") or {}).get("closePrice"))
    except Exception:
        pass
    return None


def _world_index(symbol: str) -> Optional[float]:
    try:
        import requests

        r = requests.get(_WORLD_INDEX_URL.format(symbol=symbol), headers=_HEADERS, timeout=8)
        if r.ok:
            return _num(r.json().get("closePrice"))
    except Exception:
        pass
    return None


def fetch_macro_fallback(keys: Optional[list] = None) -> dict:
    """요청한 키({'usdkrw','dxy','us10y','vix'} 부분집합)만 조회해 성공분만 반환.

    keys=None 이면 4종 전부 시도. 호출 횟수를 줄이기 위해 필요한 키만 넘길 것.
    """
    want = set(keys) if keys else {"usdkrw", "dxy", "us10y", "vix"}
    out: dict = {}
    if "usdkrw" in want:
        v = _market_index("exchange", "FX_USDKRW")
        if v:
            out["usdkrw"] = round(v, 1)
    if "dxy" in want:
        v = _market_index("exchange", ".DXY")
        if v:
            out["dxy"] = round(v, 2)
    if "us10y" in want:
        v = _market_index("bond", "US10YT=RR")
        if v:
            out["us10y"] = round(v, 3)
    if "vix" in want:
        v = _world_index(".VIX")
        if v:
            out["vix"] = round(v, 2)
    return out
