from __future__ import annotations
import datetime as dt
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict, List, Optional, Tuple

# 외부 시세 호출(yfinance/네이버/pykrx)은 개별적으로 1~3초 걸리고 서로 독립적이라
# 순차 실행 시 콜드캐시에서 홈탭이 수십 초 걸린다. 공용 스레드풀로 병렬 fetch 한다.
_POOL = ThreadPoolExecutor(max_workers=12, thread_name_prefix="mkt")


def _parallel(jobs: List[Tuple[str, Callable[[], Any]]]) -> Dict[str, Any]:
    """[(key, thunk), ...] 를 동시에 실행해 {key: result} 반환. 개별 실패는 None."""
    results: Dict[str, Any] = {}
    futs = {_POOL.submit(fn): key for key, fn in jobs}
    for fut in futs:
        key = futs[fut]
        try:
            results[key] = fut.result()
        except Exception:
            results[key] = None
    return results

# ---------------------------------------------------------------------------
# 가벼운 TTL + last-valid 캐시
# ---------------------------------------------------------------------------

_cache: Dict[str, Dict[str, Any]] = {}   # ticker -> {"value": {...}, "ts": epoch}
_cache_lock = threading.Lock()
_TTL = 60  # 해외/장외성 데이터라 60초 캐시


def _cache_get(ticker: str, allow_stale: bool = False) -> Optional[dict]:
    with _cache_lock:
        ent = _cache.get(ticker)
        if not ent:
            return None
        if allow_stale or (time.time() - ent["ts"] <= _TTL):
            return ent["value"]
    return None


def _cache_set(ticker: str, value: dict) -> None:
    with _cache_lock:
        _cache[ticker] = {"value": value, "ts": time.time()}


def _yf(ticker: str, period: str = "5d") -> dict:
    """yfinance 종가/전일대비. 실패/빈값이면 last-valid 캐시로 폴백, 그래도 없으면 {}.

    period 를 5d→1mo 로 자동 확장하여 주말/장외 빈값을 줄인다.
    """
    cached = _cache_get(ticker)
    if cached is not None:
        return cached

    try:
        import requests
        from urllib.parse import quote

        rng = "1mo" if period == "1mo" else "5d"
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{quote(ticker, safe='')}?range={rng}&interval=1d"
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=6)
        js = r.json() if r.ok else {}
        result = (js.get("chart", {}).get("result") or [None])[0]
        quote_data = ((result or {}).get("indicators", {}).get("quote") or [{}])[0]
        closes = [float(x) for x in (quote_data.get("close") or []) if x is not None]
        meta_price = (result or {}).get("meta", {}).get("regularMarketPrice")
        if closes or meta_price is not None:
            cur = float(meta_price) if meta_price is not None else closes[-1]
            if len(closes) >= 2:
                prev = closes[-2] if meta_price is not None else closes[-2]
                if meta_price is None:
                    prev = closes[-2]
                elif len(closes) >= 2:
                    # Yahoo's last close often already represents the live/current
                    # session, so compare regularMarketPrice to the previous bar.
                    prev = closes[-2]
                chg = (cur - prev) / prev * 100 if prev else 0
                out = {"close": round(cur, 4), "chg_1d": round(chg, 2)}
            else:
                out = {"close": round(cur, 4), "chg_1d": None}
            _cache_set(ticker, out)
            return out
    except Exception:
        pass

    for per in (period, "1mo"):
        try:
            import yfinance as yf
            h = yf.Ticker(ticker).history(period=per)
            if h.empty or "Close" not in h:
                continue
            closes = h["Close"].dropna()
            if closes.empty:
                continue
            cur = float(closes.iloc[-1])
            if len(closes) >= 2:
                prev = float(closes.iloc[-2])
                chg = (cur - prev) / prev * 100 if prev else 0
                out = {"close": round(cur, 4), "chg_1d": round(chg, 2)}
            else:
                out = {"close": round(cur, 4), "chg_1d": None}
            _cache_set(ticker, out)
            return out
        except Exception:
            continue

    # 모든 시도 실패 → 만료된 last-valid 라도 반환 (절대 공백 최소화)
    stale = _cache_get(ticker, allow_stale=True)
    if stale is not None:
        return stale
    return {}


def _yf_bond_index(ticker: str, period: str = "5d") -> dict:
    """Yahoo yield-index ticker -> yield(%) and 1D change(bp).

    CBOE/Yahoo treasury tickers such as ^TNX/^TYX are quoted as yield*10
    (e.g. 46.2 means 4.62%).  For the bond table we present yield in % and
    the daily move in basis points, not percentage return.
    """
    ck = "bond-yf:" + ticker
    cached = _cache_get(ck)
    if cached is not None:
        return cached

    try:
        raw = _yf(ticker, period)
        if raw.get("close") is not None:
            # _yf returns the Yahoo quote value and percent change. Re-read chart to
            # calculate bp accurately from raw closes.
            import requests
            from urllib.parse import quote
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{quote(ticker, safe='')}?range=5d&interval=1d"
            r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=6)
            result = ((r.json() if r.ok else {}).get("chart", {}).get("result") or [None])[0]
            closes = [float(x) for x in (((result or {}).get("indicators", {}).get("quote") or [{}])[0].get("close") or []) if x is not None]
            meta_price = (result or {}).get("meta", {}).get("regularMarketPrice")
            if closes or meta_price is not None:
                cur_raw = float(meta_price) if meta_price is not None else closes[-1]
                cur = cur_raw
                chg_bp = ((cur_raw - closes[-2]) * 100.0) if len(closes) >= 2 else None
                out = {"close": round(cur, 4),
                       "chg_1d": round(chg_bp, 2) if chg_bp is not None else None,
                       "chg_unit": "bp"}
                _cache_set(ck, out)
                return out
    except Exception:
        pass

    for per in (period, "1mo"):
        try:
            import yfinance as yf
            h = yf.Ticker(ticker).history(period=per)
            if h.empty or "Close" not in h:
                continue
            closes = h["Close"].dropna()
            if closes.empty:
                continue
            cur_raw = float(closes.iloc[-1])
            cur = cur_raw
            if len(closes) >= 2:
                prev_raw = float(closes.iloc[-2])
                chg_bp = (cur_raw - prev_raw) * 100.0
                out = {"close": round(cur, 4), "chg_1d": round(chg_bp, 2), "chg_unit": "bp"}
            else:
                out = {"close": round(cur, 4), "chg_1d": None, "chg_unit": "bp"}
            _cache_set(ck, out)
            return out
        except Exception:
            continue

    stale = _cache_get(ck, allow_stale=True)
    if stale is not None:
        return stale
    return {}


# ---------------------------------------------------------------------------
# 한국 국고채 금리 (무키). yfinance ^KTB3Y/^KTB10Y 는 존재하지 않는 가짜 티커라
# 영구 None 이 되므로 제거. 아래 무키 경로로 실값을 취득한다.
#   1) 네이버 금융 일별시세 (IRR_GOVT03Y 등) — 국고채 3년 등 즉시 취득 가능
#   2) pykrx 장외 채권수익률 — KRX 접속 가능한 운영환경에서 10년 등 보충
# 어느 경로도 실패하면 해당 항목은 테이블에서 제거(가짜 None 금지).
# ---------------------------------------------------------------------------

import re as _re

# 네이버 금융 marketindexCd. 네이버는 국고채 3년만 제공(10년 미제공).
_NAVER_IRR = {
    "국고채 3Y": "IRR_GOVT03Y",
}
# pykrx 장외 채권수익률 인덱스 라벨(단일일자 조회시 행 인덱스).
_PYKRX_BOND = {
    "국고채 3Y":  "국고채 3년",
    "국고채 10Y": "국고채 10년",
    "국고채 30Y": "국고채 30년",
}

_TE_KR_BOND = {
    "국고채 10Y": "https://tradingeconomics.com/south-korea/government-bond-yield",
    "국고채 30Y": "https://tradingeconomics.com/south-korea/30-year-bond-yield",
}


def _naver_bond(code: str) -> dict:
    """네이버 금융 일별 금리시세에서 최근가/전일대비(bp) 취득. 캐시/last-valid 폴백.

    표 구조: <td class="date">YYYY.MM.DD</td><td class="num">{수익률}</td> ...
    최근 2영업일 수익률 차이를 basis point로 계산한다.
    """
    ck = "naver:" + code
    cached = _cache_get(ck)
    if cached is not None:
        return cached
    try:
        import requests
        url = ("https://finance.naver.com/marketindex/interestDailyQuote.naver"
               "?marketindexCd=" + code)
        r = requests.get(
            url, timeout=8,
            headers={"User-Agent": "Mozilla/5.0",
                     "Referer": "https://finance.naver.com/marketindex/"},
        )
        r.encoding = "euc-kr"
        rows = _re.findall(
            r'<td class="date">\s*[\d.]+\s*</td>\s*<td class="num">([\d.]+)</td>',
            r.text,
        )
        vals = [float(x) for x in rows]
        if vals:
            cur = vals[0]
            if len(vals) >= 2 and vals[1]:
                chg = (cur - vals[1]) * 100
                out = {"close": round(cur, 4), "chg_1d": round(chg, 2), "chg_unit": "bp"}
            else:
                out = {"close": round(cur, 4), "chg_1d": None, "chg_unit": "bp"}
            _cache_set(ck, out)
            return out
    except Exception:
        pass
    stale = _cache_get(ck, allow_stale=True)
    if stale is not None:
        return stale
    return {}


def _pykrx_bond(label: str) -> dict:
    """pykrx 장외 채권수익률(단일일자). KRX 접속 가능한 환경에서만 실값.

    행 인덱스(label)별 수익률과 '대비'(전일대비 %p)를 취득. 변동은 bp로 표시한다.
    """
    ck = "pykrx:" + label
    cached = _cache_get(ck)
    if cached is not None:
        return cached
    try:
        import datetime as _dt
        from pykrx import bond as _kbond
        for back in range(0, 10):
            d = (_dt.date.today() - _dt.timedelta(days=back)).strftime("%Y%m%d")
            try:
                df = _kbond.get_otc_treasury_yields(d)
            except Exception:
                df = None
            if df is None or getattr(df, "empty", True):
                continue
            if label not in df.index:
                continue
            row = df.loc[label]
            cur = float(row["수익률"])
            try:
                diff = float(row["대비"])  # 전일대비 %p
                chg = diff * 100
            except Exception:
                chg = None
            out = {"close": round(cur, 4),
                   "chg_1d": round(chg, 2) if chg is not None else None,
                   "chg_unit": "bp"}
            _cache_set(ck, out)
            return out
    except Exception:
        pass
    stale = _cache_get(ck, allow_stale=True)
    if stale is not None:
        return stale
    return {}


def _tradingeconomics_bond(name: str) -> dict:
    """TradingEconomics 한국 국채 10Y/30Y 페이지에서 수익률과 전일대비 bp를 파싱."""
    url = _TE_KR_BOND.get(name)
    if not url:
        return {}
    ck = "te:" + name
    cached = _cache_get(ck)
    if cached is not None:
        return cached
    try:
        import requests
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=8)
        text = r.text
        m_val = _re.search(r'"value"\s*:\s*([0-9.]+)', text)
        if not m_val:
            return {}
        cur = float(m_val.group(1))
        desc = _re.search(r'<meta[^>]+name="description"[^>]+content="([^"]+)"', text, flags=_re.I)
        chg = None
        if desc:
            d = desc.group(1)
            m = _re.search(r'marking a\s*([0-9.]+)\s*percentage points\s*(increase|decrease)', d, flags=_re.I)
            if m:
                chg = float(m.group(1)) * 100.0
                if m.group(2).lower() == "decrease":
                    chg = -chg
        out = {
            "close": round(cur, 3),
            "chg_1d": round(chg, 2) if chg is not None else None,
            "chg_unit": "bp",
        }
        _cache_set(ck, out)
        return out
    except Exception:
        stale = _cache_get(ck, allow_stale=True)
        if stale is not None:
            return stale
        return {}


def _kr_bond(name: str) -> dict:
    """한국 국고채 실값 취득: 네이버 우선, 실패시 pykrx 폴백. 둘 다 실패면 {}."""
    code = _NAVER_IRR.get(name)
    if code:
        d = _naver_bond(code)
        if d.get("close") is not None:
            return d
    label = _PYKRX_BOND.get(name)
    if label:
        d = _pykrx_bond(label)
        if d.get("close") is not None:
            return d
    d = _tradingeconomics_bond(name)
    if d.get("close") is not None:
        return d
    return {}


def get_market_table() -> dict:
    # 한국 국고채(무키 실값). 값이 없으면 행 자체를 추가하지 않음(가짜 None 금지).
    kr_bond_names = ["국고채 3Y", "국고채 10Y", "국고채 30Y"]
    # 미국채는 기존 yfinance 유지.
    ust_tickers = {
        "UST 2Y":  "^IRX",
        "UST 10Y": "^TNX",
        "UST 30Y": "^TYX",
    }
    eq_tickers = {
        "S&P 500":   "^GSPC",
        "Nasdaq 100":"^NDX",
        "Nikkei 225":"^N225",
        "Hang Seng": "^HSI",
        "CSI 300":   "000300.SS",
        "VIX":       "^VIX",
    }
    fx_tickers = {
        "USD/KRW": "USDKRW=X",
        "USD/JPY": "USDJPY=X",
        "DXY":     "DX-Y.NYB",
        "WTI":     "CL=F",
        "Gold":    "GC=F",
        "천연가스":  "NG=F",
    }

    # 모든 행을 한 번에 병렬 fetch (콜드캐시에서 sum→max 로 단축).
    jobs: List[Tuple[str, Callable[[], Any]]] = []
    jobs += [(f"krb:{n}", (lambda nm=n: _kr_bond(nm))) for n in kr_bond_names]
    jobs += [(f"ust:{n}", (lambda tk=t: _yf_bond_index(tk))) for n, t in ust_tickers.items()]
    jobs += [(f"eq:{n}", (lambda tk=t: _yf(tk))) for n, t in eq_tickers.items()]
    jobs += [(f"fx:{n}", (lambda tk=t: _yf(tk))) for n, t in fx_tickers.items()]
    res = _parallel(jobs)

    bonds = []
    for name in kr_bond_names:
        d = res.get(f"krb:{name}") or {}
        if d.get("close") is not None:
            bonds.append({"name": name, "value": round(float(d.get("close")), 3),
                          "chg_1d": d.get("chg_1d"), "chg_unit": "bp"})
    for name in ust_tickers:
        d = res.get(f"ust:{name}") or {}
        val = d.get("close")
        bonds.append({"name": name, "value": round(float(val), 3) if val is not None else None,
                      "chg_1d": d.get("chg_1d"), "chg_unit": "bp"})

    equities = []
    for name in eq_tickers:
        d = res.get(f"eq:{name}") or {}
        equities.append({"name": name, "value": d.get("close"), "chg_1d": d.get("chg_1d")})

    fx = []
    for name in fx_tickers:
        d = res.get(f"fx:{name}") or {}
        fx.append({"name": name, "value": d.get("close"), "chg_1d": d.get("chg_1d")})

    return {"bonds": bonds, "equities": equities, "fx": fx,
            "as_of": dt.datetime.now().isoformat()}


def warm_cache() -> None:
    """서버 부팅 직후 백그라운드에서 호출 — 시세 캐시를 미리 채워 첫 사용자 로딩을 단축."""
    try:
        get_market_table()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# KPI 헬퍼 (main.py /api/market/kpi 에서 재사용)
# ---------------------------------------------------------------------------

def get_yf_metric(ticker: str) -> dict:
    """단일 yfinance 지표 -> {value, change}. 캐시/폴백 적용. 빈값은 None."""
    d = _yf(ticker)
    return {"value": d.get("close"), "change": d.get("chg_1d")}
