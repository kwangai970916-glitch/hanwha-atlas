"""시황 깊이 보강용 시장 내부 지표.

- breadth_snapshot(): 상승/하락/보합 종목 수 + 편차(=상승-하락) — 시장 폭(쏠림/확산) 판단.
- sector_rotation(): 상세 섹터별 최근 N일 시총가중 수익률 랭킹 — '업종 키맞추기/순환매' 판단.

모두 클라우드에서 동작하는 무키 소스(_get_kospi_market_rows + 네이버 fchart OHLCV)만 사용한다.
전부 best-effort: 실패 시 빈 dict 반환(호출측이 graceful degrade).
"""
from __future__ import annotations

from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Tuple


def breadth_snapshot() -> Dict[str, Any]:
    """KOSPI 전종목 상승/하락/보합 수 + 편차. (쏠림 vs 확산 판단의 핵심 지표)"""
    try:
        from .price_service import _get_kospi_market_rows
        rows = _get_kospi_market_rows()
        if not rows or len(rows) < 50:
            return {}
        up = sum(1 for r in rows if (r.get("change") or 0) > 0.05)
        down = sum(1 for r in rows if (r.get("change") or 0) < -0.05)
        total = len(rows)
        return {"advancers": up, "decliners": down, "flat": total - up - down,
                "total": total, "diff": up - down}
    except Exception:
        return {}


def sector_rotation(windows: Tuple[int, ...] = (5, 20),
                    top_sectors: int = 12, stocks_per: int = 4) -> Dict[str, List[Dict[str, Any]]]:
    """상세 섹터별 최근 N거래일 시총가중 수익률 랭킹.

    시총 상위 섹터(top_sectors)의 대표주(stocks_per)만 네이버 fchart OHLCV 로 받아
    cap-weighted N일 수익률을 산출 → 업종 로테이션/키맞추기 근거. (bounded: ~48 호출, 병렬)
    """
    try:
        from .price_service import _get_kospi_market_rows
        from .ohlcv_sources import daily_ohlcv
        rows = _get_kospi_market_rows()
        if not rows or len(rows) < 50:
            return {}

        groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for r in rows:
            sec = (r.get("sector") or "").strip()
            cap = r.get("market_cap")
            if not sec or sec in ("KOSPI", "기타") or not cap or cap <= 0:
                continue
            groups[sec].append(r)
        if not groups:
            return {}

        sec_by_cap = sorted(
            groups.items(),
            key=lambda kv: sum(m.get("market_cap") or 0 for m in kv[1]), reverse=True
        )[:top_sectors]

        tasks: List[Tuple[str, Dict[str, Any]]] = []
        for sec, members in sec_by_cap:
            top = sorted(members, key=lambda m: m.get("market_cap") or 0, reverse=True)[:stocks_per]
            for m in top:
                tasks.append((sec, m))

        need = max(windows)

        def _fetch(t: Tuple[str, Dict[str, Any]]):
            sec, m = t
            try:
                bars = daily_ohlcv(str(m["symbol"]), count=need + 6)
                closes = [b["close"] for b in bars if b.get("close")]
            except Exception:
                closes = []
            return sec, (m.get("market_cap") or 0), closes

        closes_by: Dict[str, List[Tuple[float, List[float]]]] = defaultdict(list)
        with ThreadPoolExecutor(max_workers=10) as ex:
            for sec, cap, closes in ex.map(_fetch, tasks):
                if len(closes) > need:
                    closes_by[sec].append((cap, closes))

        result: Dict[str, List[Dict[str, Any]]] = {}
        for w in windows:
            ranked: List[Dict[str, Any]] = []
            for sec, lst in closes_by.items():
                num = den = 0.0
                for cap, cl in lst:
                    if len(cl) > w and cl[-1 - w]:
                        ret = (cl[-1] / cl[-1 - w] - 1.0) * 100.0
                        num += ret * cap
                        den += cap
                if den:
                    ranked.append({"sector": sec, "return": round(num / den, 2)})
            ranked.sort(key=lambda x: x["return"], reverse=True)
            if ranked:
                result[f"{w}d"] = ranked
        return result
    except Exception:
        return {}
