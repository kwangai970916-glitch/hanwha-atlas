"""통합 시세 서비스 (KR 준실시간 + 견고한 폴백).

설계 원칙:
  1) KR 1차 소스: 네이버 폴링 API (polling.finance.naver.com) — 장중 준실시간.
       - 종목: /api/realtime/domestic/stock/{code}
       - 지수: /api/realtime/domestic/index/{KOSPI|KOSDAQ}
       실측한 JSON 구조에 맞춰 파싱:
         지수 datas[0]: closePriceRaw / compareToPreviousClosePriceRaw(부호有) / fluctuationsRatioRaw(부호有)
         종목 datas[0]: closePrice(콤마문자열,장중=현재가) / compareToPreviousClosePrice(절댓값) /
                        compareToPreviousPrice.name(RISING|FALLING|STEADY) / fluctuationsRatio(부호有)
  2) 폴백: 네이버 실패/차단 시 pykrx. 당일이 비면 최근 영업일로 최대 7일 역행하여 마지막 종가 확보.
  3) TTL 메모리 캐시 (장중 ~20초, 그 외 더 길게)로 속도 개선 + 외부 호출 최소화.
  4) 절대 공백 금지: 모든 경로 실패 시에도 최후 캐시값(만료된 것이라도) 반환 시도.

공개 함수:
  get_index(name) -> {symbol, display, price, change, change_pct, source, ...} | None-안전 dict
  get_quote(code) -> {symbol, display, price, change, change_pct, source, ...}
  get_quotes(codes) -> {code: quote}
  get_ticks() -> main.py 의 _fetch_pykrx_ticks 대체용 (KOSPI/KOSDAQ + 주요 10종목)
"""
from __future__ import annotations

import datetime as dt
import html as _html
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

# ---------------------------------------------------------------------------
# 상수
# ---------------------------------------------------------------------------

_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
_HEADERS = {
    "User-Agent": _UA,
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://finance.naver.com/",
}
_NAVER_STOCK = "https://polling.finance.naver.com/api/realtime/domestic/stock/{code}"
_NAVER_INDEX = "https://polling.finance.naver.com/api/realtime/domestic/index/{name}"

_HTTP_TIMEOUT = 6

# 주요 10 종목 (main.py 기존 목록과 동일)
WATCH_STOCKS: List[tuple[str, str, str]] = [
    ("005930", "삼성전자", "반도체"),
    ("000660", "SK하이닉스", "반도체"),
    ("005380", "현대차", "자동차"),
    ("000270", "기아", "자동차"),
    ("012450", "한화에어로", "방산"),
    ("042660", "한화오션", "조선"),
    ("009540", "HD한국조선해양", "조선"),
    ("034020", "두산에너빌리티", "전력기기"),
    ("105560", "KB금융", "금융"),
    ("055550", "신한지주", "금융"),
]

WATCH_SECTOR_MAP: Dict[str, str] = {code: sector for code, _, sector in WATCH_STOCKS}
WATCH_NAME_MAP: Dict[str, str] = {code: name for code, name, _ in WATCH_STOCKS}
def _resolve_sector_map_file() -> Path:
    """섹터맵 파일 경로. 배포 이미지에 동봉되도록 backend/app/data 를 우선하고,
    없으면 로컬 개발용 루트 /data 를 쓴다. 둘 다 없으면 동봉 경로(쓰기용)를 반환."""
    bundled = Path(__file__).resolve().parent / "data" / "kospi_sector_map.json"   # backend/app/data (Docker COPY backend/ 로 포함)
    if bundled.exists():
        return bundled
    legacy = Path(__file__).resolve().parents[2] / "data" / "kospi_sector_map.json"  # 루트/data (로컬 전용)
    return legacy if legacy.exists() else bundled


_SECTOR_MAP_FILE = _resolve_sector_map_file()

# 지수: 우리 심볼 -> (네이버 index name, pykrx 코드, 표시명)
INDEX_MAP: Dict[str, Dict[str, str]] = {
    "KOSPI":   {"naver": "KOSPI",   "pykrx": "1001", "display": "KOSPI",   "symbol": "^KS11"},
    "KOSDAQ":  {"naver": "KOSDAQ",  "pykrx": "2001", "display": "KOSDAQ",  "symbol": "^KQ11"},
    # VKOSPI — 코스피200 변동성지수. 네이버 polling이 장중에 실시간 제공.
    # 장 마감/외장시 polling은 빈 응답 → stale 캐시 폴백(전일 종가).
    "VKOSPI":  {"naver": "VKOSPI",  "pykrx": "",     "display": "VKOSPI",  "symbol": "VKOSPI"},
}

# ---------------------------------------------------------------------------
# TTL 메모리 캐시 (스레드 안전)
# ---------------------------------------------------------------------------

_cache: Dict[str, Dict[str, Any]] = {}      # key -> {"value": dict, "ts": epoch}
_cache_lock = threading.Lock()


def _is_market_hours() -> bool:
    """한국 정규장(평일 09:00~15:40 KST) 여부. 서버 TZ 가정 없이 KST로 환산."""
    now = dt.datetime.utcnow() + dt.timedelta(hours=9)  # KST
    if now.weekday() >= 5:  # 토(5)/일(6)
        return False
    hm = now.hour * 100 + now.minute
    return 850 <= hm <= 1600  # 장 전후 여유 포함


def _ttl() -> int:
    return 20 if _is_market_hours() else 120


def _cache_get(key: str, allow_stale: bool = False) -> Optional[Dict[str, Any]]:
    with _cache_lock:
        ent = _cache.get(key)
        if not ent:
            return None
        if allow_stale:
            return ent["value"]
        if time.time() - ent["ts"] <= _ttl():
            return ent["value"]
    return None


def _cache_set(key: str, value: Dict[str, Any]) -> None:
    with _cache_lock:
        _cache[key] = {"value": value, "ts": time.time()}


# ---------------------------------------------------------------------------
# 파싱 헬퍼
# ---------------------------------------------------------------------------

def _to_float(s: Any) -> Optional[float]:
    if s is None:
        return None
    try:
        return float(str(s).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def _sign_from_name(direction: Optional[dict]) -> int:
    """compareToPreviousPrice 객체로부터 +1/-1/0 부호 도출."""
    if not isinstance(direction, dict):
        return 1
    name = str(direction.get("name", "")).upper()
    code = str(direction.get("code", ""))
    if name == "FALLING" or code in ("4", "5"):  # 4=하한, 5=하락
        return -1
    if name in ("STEADY", "UNCHANGED") or code == "3":
        return 0
    return 1  # RISING/UPPER/기본


# ---------------------------------------------------------------------------
# 네이버 1차 소스
# ---------------------------------------------------------------------------

def _naver_index(name: str) -> Optional[Dict[str, Any]]:
    try:
        url = _NAVER_INDEX.format(name=name)
        r = requests.get(url, headers=_HEADERS, timeout=_HTTP_TIMEOUT)
        if r.status_code != 200:
            return None
        datas = r.json().get("datas") or []
        if not datas:
            return None
        d = datas[0]
        price = _to_float(d.get("closePriceRaw") or d.get("closePrice"))
        change = _to_float(d.get("compareToPreviousClosePriceRaw")
                           or d.get("compareToPreviousClosePrice"))
        change_pct = _to_float(d.get("fluctuationsRatioRaw") or d.get("fluctuationsRatio"))
        if price is None:
            return None
        # 종목과 달리 index Raw 필드는 부호를 이미 포함하지만, 혹시 절댓값일 때 대비
        if change is not None:
            sign = _sign_from_name(d.get("compareToPreviousPrice"))
            if sign and change > 0 and sign < 0:
                change = -change
        return {
            "price": round(price, 2),
            "change": round(change, 2) if change is not None else None,
            "change_pct": round(change_pct, 2) if change_pct is not None else None,
            "source": "naver",
            "market_status": d.get("marketStatus"),
        }
    except Exception:
        return None


def _naver_stock(code: str) -> Optional[Dict[str, Any]]:
    try:
        url = _NAVER_STOCK.format(code=code)
        r = requests.get(url, headers=_HEADERS, timeout=_HTTP_TIMEOUT)
        if r.status_code != 200:
            return None
        datas = r.json().get("datas") or []
        if not datas:
            return None
        d = datas[0]
        price = _to_float(d.get("closePrice"))
        if price is None:
            return None
        # 종목 compareToPreviousClosePrice 는 절댓값 → 방향객체로 부호 적용
        change_abs = _to_float(d.get("compareToPreviousClosePrice"))
        sign = _sign_from_name(d.get("compareToPreviousPrice"))
        change = (change_abs * sign) if change_abs is not None else None
        change_pct = _to_float(d.get("fluctuationsRatio"))
        if change_pct is not None and sign < 0 and change_pct > 0:
            change_pct = -change_pct
        return {
            "price": round(price, 2),
            "change": round(change, 2) if change is not None else None,
            "change_pct": round(change_pct, 2) if change_pct is not None else None,
            "source": "naver",
            "market_status": d.get("marketStatus"),
            "name": d.get("stockName"),
        }
    except Exception:
        return None


# ---------------------------------------------------------------------------
# pykrx 폴백 (최근 영업일 역행)
# ---------------------------------------------------------------------------

def _pykrx_backfill(is_index: bool, code: str, max_days: int = 7) -> Optional[Dict[str, Any]]:
    """당일이 비면 최근 영업일로 최대 max_days 역행하여 마지막 종가/전일대비 확보.

    change/change_pct 는 해당일 종가 vs (그 이전 영업일 종가) 로 계산.
    """
    try:
        from pykrx import stock as krx
    except Exception:
        return None

    end = dt.date.today()
    start = end - dt.timedelta(days=max_days + 7)  # 직전 영업일 1개 더 확보 위해 여유
    s, e = start.strftime("%Y%m%d"), end.strftime("%Y%m%d")
    df = None
    try:
        if is_index:
            # 신형 API(get_index_ohlcv, name_display=False)는 지수명 메타조회 버그를 우회.
            # 일부 pykrx 버전에서 get_index_ohlcv_by_date 가 KeyError('지수명') 발생.
            try:
                df = krx.get_index_ohlcv(s, e, code, name_display=False)
            except Exception:
                df = None
            if df is None or df.empty:
                try:
                    df = krx.get_index_ohlcv_by_date(s, e, code)
                except Exception:
                    df = None
        else:
            df = krx.get_market_ohlcv_by_date(s, e, code)
    except Exception:
        return None
    if df is None or df.empty:
        return None

    closes = df["종가"].dropna()
    if closes.empty:
        return None
    last = float(closes.iloc[-1])
    prev = float(closes.iloc[-2]) if len(closes) >= 2 else last
    change = last - prev
    change_pct = (change / prev * 100) if prev else 0.0
    as_of_day = str(closes.index[-1])[:10]
    return {
        "price": round(last, 2),
        "change": round(change, 2),
        "change_pct": round(change_pct, 2),
        "source": "pykrx",
        "as_of_day": as_of_day,
    }


def _get_kospi_sector_map() -> Dict[str, str]:
    """KOSPI 전종목 코드 -> 업종명 매핑.

    pykrx의 KOSPI 업종 지수 구성종목을 이용한다. 일부 환경에서 업종 포트폴리오
    조회가 실패할 수 있으므로 WATCH_STOCKS 매핑을 최후 보강으로 유지한다.
    """
    ck = "kospi:sector-map"
    cached = _cache_get(ck, allow_stale=True)
    if cached is not None:
        return cached

    sector_map: Dict[str, str] = dict(WATCH_SECTOR_MAP)
    naver_map = _naver_upjong_sector_map()
    if naver_map:
        sector_map.update(naver_map)
        _cache_set(ck, sector_map)
        return sector_map

    try:
        from pykrx import stock as krx

        for index_code in krx.get_index_ticker_list(market="KOSPI"):
            try:
                sector_name = str(krx.get_index_ticker_name(index_code) or "").strip()
                members = krx.get_index_portfolio_deposit_file(index_code) or []
            except Exception:
                continue
            if not sector_name:
                continue
            for code in members:
                code_s = str(code).zfill(6)
                # 기존 수작업 섹터는 더 세밀하므로 보존하고, 나머지만 업종명으로 채운다.
                sector_map.setdefault(code_s, sector_name)
    except Exception:
        pass

    _cache_set(ck, sector_map)
    return sector_map


def _decode_naver(resp: requests.Response) -> str:
    enc = (resp.encoding or "").lower()
    if "euc" in enc or "949" in enc:
        return resp.content.decode("euc-kr", "ignore")
    return resp.content.decode("utf-8", "ignore")


def _naver_upjong_sector_map() -> Dict[str, str]:
    """네이버 업종 상세 페이지를 이용한 코드 -> 업종명 매핑.

    pykrx/KRX가 차단되거나 빈값인 환경에서도 동작하는 무키 fallback이다.
    """
    try:
        if _SECTOR_MAP_FILE.exists():
            import json
            data = json.loads(_SECTOR_MAP_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data:
                return {str(k).zfill(6): str(v) for k, v in data.items() if v}
    except Exception:
        pass

    try:
        s = requests.Session()
        headers = {"User-Agent": _UA, "Referer": "https://finance.naver.com/sise/"}
        r = s.get("https://finance.naver.com/sise/sise_group.naver?type=upjong",
                  headers=headers, timeout=8)
        text = _decode_naver(r)
        links: list[tuple[str, str]] = []
        for href, name in re.findall(
            r'<a[^>]+href="([^"]*sise_group_detail\.naver\?type=upjong[^"]+)"[^>]*>(.*?)</a>',
            text,
            flags=re.I | re.S,
        ):
            sector = _html.unescape(re.sub(r"<.*?>", "", name)).strip()
            if sector and "no=" in href:
                links.append((sector, "https://finance.naver.com" + href.replace("&amp;", "&")))

        def fetch_detail(pair: tuple[str, str]) -> Dict[str, str]:
            sector, url = pair
            out: Dict[str, str] = {}
            try:
                for page in range(1, 30):
                    sep = "&" if "?" in url else "?"
                    rr = s.get(f"{url}{sep}page={page}", headers=headers, timeout=8)
                    detail = _decode_naver(rr)
                    found = 0
                    for code, nm in re.findall(
                        r'<a[^>]+href="/item/main\.naver\?code=(\d{6})"[^>]*>(.*?)</a>',
                        detail,
                        flags=re.I | re.S,
                    ):
                        if code:
                            out[code] = sector
                            found += 1
                    if found == 0:
                        break
            except Exception:
                return {}
            return out

        sector_map: Dict[str, str] = {}
        with ThreadPoolExecutor(max_workers=8) as ex:
            futs = [ex.submit(fetch_detail, pair) for pair in links]
            for fut in as_completed(futs, timeout=60):
                try:
                    sector_map.update(fut.result())
                except Exception:
                    pass
        if sector_map:
            try:
                import json
                _SECTOR_MAP_FILE.parent.mkdir(parents=True, exist_ok=True)
                _SECTOR_MAP_FILE.write_text(
                    json.dumps(sector_map, ensure_ascii=False, indent=2, sort_keys=True),
                    encoding="utf-8",
                )
            except Exception:
                pass
        return sector_map
    except Exception:
        return {}


def _parse_signed_number(text: str) -> Optional[float]:
    raw = re.sub(r"[^0-9.+-]", "", str(text or ""))
    if raw in ("", "+", "-", ".", "+.", "-."):
        return None
    try:
        return float(raw)
    except Exception:
        return None


def _naver_kospi_market_rows() -> List[Dict[str, Any]]:
    """네이버 시가총액 페이지에서 KOSPI 전종목 현재가/등락률을 수집."""
    ck = "naver:kospi-market-rows"
    cached = _cache_get(ck, allow_stale=True)
    if cached is not None:
        return cached.get("rows", [])

    try:
        s = requests.Session()
        headers = {"User-Agent": _UA, "Referer": "https://finance.naver.com/sise/"}
        sector_map = _get_kospi_sector_map()
        rows: List[Dict[str, Any]] = []
        empty_pages = 0

        for page in range(1, 80):
            url = f"https://finance.naver.com/sise/sise_market_sum.naver?sosok=0&page={page}"
            r = s.get(url, headers=headers, timeout=8)
            text = _decode_naver(r)
            found = 0
            for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", text, flags=re.I | re.S):
                m = re.search(
                    r'<a[^>]+href="/item/main\.naver\?code=(\d{6})"[^>]*>(.*?)</a>',
                    tr,
                    flags=re.I | re.S,
                )
                if not m:
                    continue
                code = m.group(1)
                name = _html.unescape(re.sub(r"<.*?>", "", m.group(2))).strip()
                cells = [
                    _html.unescape(re.sub(r"\s+", " ", re.sub(r"<.*?>", " ", td))).strip()
                    for td in re.findall(r"<td[^>]*>(.*?)</td>", tr, flags=re.I | re.S)
                ]
                if len(cells) < 5:
                    continue
                price = _parse_signed_number(cells[2])
                change_abs = _parse_signed_number(cells[3])
                change_pct = _parse_signed_number(cells[4])
                market_cap = _parse_signed_number(cells[6]) if len(cells) > 6 else None
                # sise_market_sum 컬럼: ...시가총액(6)·상장주식수(7)·외국인비율(8)·거래량(9)...
                volume = _parse_signed_number(cells[9]) if len(cells) > 9 else None
                if "하락" in cells[3] and change_abs is not None and change_abs > 0:
                    change_abs = -change_abs
                if "하락" in cells[4] and change_pct is not None and change_pct > 0:
                    change_pct = -change_pct
                if price is None:
                    continue
                # 거래대금(원) ≈ 거래량 × 현재가 (네이버 시총페이지엔 거래대금 직접 컬럼이 없음)
                trade_value = (volume * price) if (volume and price) else None
                rows.append({
                    "symbol": code,
                    "display": name or code,
                    "price": int(price) if float(price).is_integer() else round(price, 2),
                    "change": round(change_pct, 2) if change_pct is not None else None,
                    "change_abs": round(change_abs, 2) if change_abs is not None else None,
                    "asset_type": "stock",
                    "sector": sector_map.get(code, "KOSPI"),
                    "market_cap": market_cap,
                    "volume": int(volume) if volume else None,
                    "trade_value": int(trade_value) if trade_value else None,
                    "trade_value_estimated": True,  # 네이버 시총페이지엔 거래대금 직접 컬럼 없음 → 거래량×현재가 근사
                    "source": "naver-kospi-all",
                })
                found += 1

            if found == 0:
                empty_pages += 1
                if empty_pages >= 2:
                    break
            else:
                empty_pages = 0

        if rows:
            _cache_set(ck, {"rows": rows})
        return rows
    except Exception:
        return []


def _row_get(row: Any, *names: str) -> Any:
    for name in names:
        try:
            if hasattr(row, "get"):
                v = row.get(name)
            else:
                v = row[name]
            if v is not None:
                return v
        except Exception:
            continue
    return None


def _get_kospi_market_rows() -> List[Dict[str, Any]]:
    """KOSPI 전종목 시세 스냅샷.

    한 종목씩 호출하지 않고 pykrx의 by_ticker 일괄 스냅샷을 사용해 대상을 KOSPI
    전체로 넓힌다. 실패 시 빈 리스트를 반환하고 기존 WATCH_STOCKS 경로가 폴백한다.
    """
    ck = "kospi:all-stocks"
    cached = _cache_get(ck, allow_stale=True)
    if cached is not None:
        return cached.get("rows", [])

    naver_rows = _naver_kospi_market_rows()
    if naver_rows:
        _cache_set(ck, {"rows": naver_rows})
        return naver_rows

    try:
        from pykrx import stock as krx

        codes: List[str] = []
        df = None
        for back in range(0, 10):
            day = (dt.date.today() - dt.timedelta(days=back)).strftime("%Y%m%d")
            try:
                codes = [str(c).zfill(6) for c in (krx.get_market_ticker_list(day, market="KOSPI") or [])]
                df = krx.get_market_ohlcv_by_ticker(day, market="KOSPI")
            except Exception:
                codes, df = [], None
            if codes and df is not None and not getattr(df, "empty", True):
                break
        if not codes or df is None or getattr(df, "empty", True):
            return []

        sector_map = _get_kospi_sector_map()
        rows: List[Dict[str, Any]] = []
        for code in codes:
            try:
                row = df.loc[code]
            except Exception:
                continue

            price = _to_float(_row_get(row, "종가", "현재가", "Close"))
            if price is None:
                continue
            change_pct = _to_float(_row_get(row, "등락률", "수익률", "Change"))
            change_abs = _to_float(_row_get(row, "대비", "전일비", "ChangeAbs"))
            try:
                name = str(krx.get_market_ticker_name(code) or "").strip()
            except Exception:
                name = ""

            rows.append({
                "symbol": code,
                "display": name or WATCH_NAME_MAP.get(code) or code,
                "price": int(price) if float(price).is_integer() else round(price, 2),
                "change": round(change_pct, 2) if change_pct is not None else None,
                "change_abs": round(change_abs, 2) if change_abs is not None else None,
                "asset_type": "stock",
                "sector": sector_map.get(code, "KOSPI"),
                "market_cap": _to_float(_row_get(row, "시가총액", "MarketCap")),
                "volume": _to_float(_row_get(row, "거래량", "Volume")),
                "trade_value": _to_float(_row_get(row, "거래대금", "TradeValue")),
                "trade_value_estimated": False,  # pykrx 거래대금은 실측값
                "source": "pykrx-kospi-all",
            })

        if rows:
            _cache_set(ck, {"rows": rows})
        return rows
    except Exception:
        return []


# ---------------------------------------------------------------------------
# 공개 API
# ---------------------------------------------------------------------------

def get_index(name: str) -> Dict[str, Any]:
    """name in {'KOSPI','KOSDAQ'} (대소문자/심볼 허용). 절대 공백 금지."""
    key_raw = (name or "").strip().upper()
    alias = {"^KS11": "KOSPI", "KS11": "KOSPI", "^KQ11": "KOSDAQ", "KQ11": "KOSDAQ"}
    key = alias.get(key_raw, key_raw)
    meta = INDEX_MAP.get(key)
    if meta is None:
        return {"symbol": key_raw, "display": key_raw, "price": None,
                "change": None, "change_pct": None, "source": "unknown", "asset_type": "index"}

    ck = f"index:{key}"
    cached = _cache_get(ck)
    if cached is not None:
        return cached

    pykrx_code = meta.get("pykrx", "")
    data = _naver_index(meta["naver"]) or (
        _pykrx_backfill(True, pykrx_code) if pykrx_code else None
    )
    if data is None:
        # 최후: 만료된 캐시라도 반환 (절대 공백 금지)
        stale = _cache_get(ck, allow_stale=True)
        if stale is not None:
            out = dict(stale)
            out["source"] = stale.get("source", "stale") + "+stale"
            return out
        return {"symbol": meta["symbol"], "display": meta["display"], "price": None,
                "change": None, "change_pct": None, "source": "unavailable", "asset_type": "index"}

    out = {
        "symbol": meta["symbol"],
        "display": meta["display"],
        "price": data.get("price"),
        "change": data.get("change"),
        "change_pct": data.get("change_pct"),
        "source": data.get("source"),
        "asset_type": "index",
        "as_of": dt.datetime.now().isoformat(timespec="seconds"),
    }
    _cache_set(ck, out)
    return out


def get_quote(code: str) -> Dict[str, Any]:
    """종목코드 6자리 -> {symbol, display, price, change, change_pct, source}. 절대 공백 금지."""
    code = str(code).strip().zfill(6)
    ck = f"stock:{code}"
    cached = _cache_get(ck)
    if cached is not None:
        return cached

    display = WATCH_NAME_MAP.get(code)
    sector = _get_kospi_sector_map().get(code)

    data = _naver_stock(code) or _pykrx_backfill(False, code)
    if data is None:
        stale = _cache_get(ck, allow_stale=True)
        if stale is not None:
            out = dict(stale)
            out["source"] = str(stale.get("source", "stale")) + "+stale"
            return out
        return {"symbol": code, "display": display or code, "price": None,
                "change": None, "change_pct": None, "source": "unavailable",
                "asset_type": "stock", "sector": sector}

    out = {
        "symbol": code,
        "display": display or data.get("name") or code,
        "price": data.get("price"),
        "change": data.get("change"),
        "change_pct": data.get("change_pct"),
        "source": data.get("source"),
        "asset_type": "stock",
        "sector": sector,
        "as_of": dt.datetime.now().isoformat(timespec="seconds"),
    }
    _cache_set(ck, out)
    return out


def get_quotes(codes: List[str]) -> Dict[str, Dict[str, Any]]:
    """여러 종목 일괄 조회 -> {code: quote}."""
    return {str(c).zfill(6): get_quote(c) for c in codes}


def _with_index_contribution(rows: List[Dict[str, Any]]) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Add normalized KOSPI contribution points.

    Raw market-cap weighted contribution is a proxy because KOSPI uses free-float
    adjusted market cap and a divisor. Normalize raw contributions so the sum of
    every stock's contribution equals the actual KOSPI point move.
    """
    total_cap = sum((_to_float(r.get("market_cap")) or 0.0) for r in rows)
    q = get_index("KOSPI")
    idx_price = _to_float(q.get("price")) or 0.0
    idx_change = _to_float(q.get("change")) or 0.0
    prev_index = idx_price - idx_change if idx_price and idx_change is not None else idx_price
    if prev_index <= 0:
        prev_index = idx_price or 0.0

    raw_items: List[tuple[Dict[str, Any], float, float, float]] = []
    raw_sum = 0.0
    for r in rows:
        out = dict(r)
        cap = _to_float(out.get("market_cap")) or 0.0
        chg = _to_float(out.get("change")) or 0.0
        weight = (cap / total_cap) if total_cap > 0 else 0.0
        contrib_pct = weight * chg
        raw_contrib_pt = prev_index * (contrib_pct / 100.0)
        raw_sum += raw_contrib_pt
        raw_items.append((out, weight, contrib_pct, raw_contrib_pt))

    normalization = (idx_change / raw_sum) if raw_sum else 0.0
    enriched: List[Dict[str, Any]] = []
    normalized_sum = 0.0
    for idx, (out, weight, contrib_pct, raw_contrib_pt) in enumerate(raw_items):
        contrib_pt = raw_contrib_pt * normalization
        # Keep the displayed 3-decimal values additively consistent by assigning
        # residual rounding error to the final row.
        if idx == len(raw_items) - 1:
            contrib_pt = idx_change - normalized_sum
        rounded_pt = round(contrib_pt, 3)
        normalized_sum += rounded_pt
        out["index_weight"] = round(weight * 100.0, 4)
        out["index_contribution_pct"] = round(contrib_pct, 4)
        out["raw_index_contribution_pt"] = round(raw_contrib_pt, 3)
        out["index_contribution_pt"] = rounded_pt
        enriched.append(out)
    return enriched, {
        "total_market_cap": round(total_cap, 2),
        "actual_index_change_pt": round(idx_change, 6),
        "raw_contribution_sum_pt": round(raw_sum, 6),
        "normalization_factor": round(normalization, 8),
    }


def get_kospi_universe(
    q: str = "",
    limit: int = 100,
    sector: str = "",
    min_market_cap: float | int | str = 0,
    direction: str = "all",
    sort: str = "contribution",
    order: str = "desc",
) -> Dict[str, Any]:
    """KOSPI 전종목 검색용 universe. 홈 화면 snapshot과 분리한다."""
    query = str(q or "").strip().lower()
    rows, contribution_meta = _with_index_contribution(_get_kospi_market_rows())
    if query:
        rows = [
            r for r in rows
            if query in str(r.get("symbol", "")).lower()
            or query in str(r.get("display", "")).lower()
            or query in str(r.get("sector", "")).lower()
        ]
    sector_q = str(sector or "").strip()
    if sector_q:
        rows = [r for r in rows if str(r.get("sector") or "") == sector_q]
    min_cap = _to_float(min_market_cap) or 0.0
    if min_cap > 0:
        rows = [r for r in rows if (_to_float(r.get("market_cap")) or 0.0) >= min_cap]
    direction_q = str(direction or "all").lower()
    if direction_q == "up":
        rows = [r for r in rows if (_to_float(r.get("change")) or 0.0) > 0]
    elif direction_q == "down":
        rows = [r for r in rows if (_to_float(r.get("change")) or 0.0) < 0]

    sort_key = str(sort or "contribution").lower()
    key_map = {
        "contribution": "index_contribution_pt",
        "index_contribution": "index_contribution_pt",
        "change": "change",
        "market_cap": "market_cap",
        "trade_value": "trade_value",
        "volume": "volume",
        "name": "display",
    }
    field = key_map.get(sort_key, "index_contribution_pt")
    reverse = str(order or "desc").lower() != "asc"
    rows.sort(
        key=lambda r: str(r.get(field) or "") if field == "display" else (_to_float(r.get(field)) or 0.0),
        reverse=reverse,
    )
    lim = max(1, min(int(limit or 100), 3000))
    return {
        "stocks": rows[:lim],
        "total": len(rows),
        "limit": lim,
        "sort": sort_key,
        "order": "desc" if reverse else "asc",
        "total_market_cap": contribution_meta["total_market_cap"],
        "contribution_meta": contribution_meta,
        "as_of": dt.datetime.now().isoformat(timespec="seconds"),
        "source": "kospi-universe",
    }


def get_sector_returns() -> List[Dict[str, Any]]:
    """전종목 시가총액 가중 업종 등락률."""
    buckets: Dict[str, Dict[str, float]] = {}
    for r in _get_kospi_market_rows():
        sector = str(r.get("sector") or "KOSPI")
        change = _to_float(r.get("change"))
        if change is None:
            continue
        market_cap = _to_float(r.get("market_cap")) or _to_float(r.get("price")) or 1.0
        if market_cap <= 0:
            market_cap = 1.0
        b = buckets.setdefault(sector, {"weighted": 0.0, "weight": 0.0, "count": 0.0})
        b["weighted"] += change * market_cap
        b["weight"] += market_cap
        b["count"] += 1.0

    sectors = []
    for sector, b in buckets.items():
        if b["weight"] <= 0:
            continue
        sectors.append({
            "sector": sector,
            "change": round(b["weighted"] / b["weight"], 2),
            "count": int(b["count"]),
            "market_cap": round(b["weight"], 2),
            "method": "market_cap_weighted",
        })
    sectors.sort(key=lambda x: x["change"], reverse=True)
    return sectors


def get_market_breadth() -> Dict[str, Any]:
    """시장 폭 + 지수 기여 상·하위 종목을 단일 스냅샷에서 집계.

    프론트가 direction=all/up/down 3회 호출하던 것을 1회로 대체. 같은 universe
    스냅샷에서 등락 종목수와 기여도 드라이버를 함께 산출해 정합성을 보장한다.
    """
    rows = _get_kospi_market_rows()
    if not rows:
        return {"up": 0, "down": 0, "flat": 0, "total": 0,
                "advance_decline_ratio": None, "top_drivers": [], "bottom_drivers": [],
                "as_of": dt.datetime.now().isoformat(timespec="seconds"),
                "source": "empty"}

    up = down = flat = 0
    for r in rows:
        chg = _to_float(r.get("change"))
        if chg is None:
            continue
        if chg > 0:
            up += 1
        elif chg < 0:
            down += 1
        else:
            flat += 1

    enriched, _meta = _with_index_contribution(rows)
    ranked = sorted(enriched, key=lambda r: _to_float(r.get("index_contribution_pt")) or 0.0, reverse=True)

    def _driver(r: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "name": r.get("display") or r.get("symbol"),
            "code": r.get("symbol"),
            "change": r.get("change"),
            "contribution": r.get("index_contribution_pt"),
        }

    top_drivers = [_driver(r) for r in ranked[:5]]
    bottom_drivers = [_driver(r) for r in ranked[-5:][::-1]]
    total = up + down + flat
    return {
        "up": up, "down": down, "flat": flat, "total": total,
        "advance_decline_ratio": round(up / down, 2) if down else None,
        "top_drivers": top_drivers,
        "bottom_drivers": bottom_drivers,
        "as_of": dt.datetime.now().isoformat(timespec="seconds"),
        "source": rows[0].get("source", "kospi-all"),
    }


def get_market_heatmap(top_per_sector: int = 40) -> Dict[str, Any]:
    """Finviz 스타일 그룹 히트맵 데이터.

    전종목을 GICS 11 대분류로 접고, 대분류별 시총가중 등락률 + 대표 종목 타일을
    반환한다. 미분류('기타')는 노이즈라 제외한다. 셀 크기=시총, 색=등락률용.
    """
    from .sector_taxonomy import to_major_sector

    groups: Dict[str, Dict[str, Any]] = {}
    for r in _get_kospi_market_rows():
        change = _to_float(r.get("change"))
        market_cap = _to_float(r.get("market_cap"))
        if change is None or not market_cap or market_cap <= 0:
            continue
        major = to_major_sector(r.get("sector"))
        if major == "기타":
            continue
        g = groups.setdefault(major, {"stocks": [], "wsum": 0.0, "w": 0.0})
        g["stocks"].append({
            "code": r.get("symbol"),
            "name": r.get("display") or r.get("symbol"),
            "change": change,
            "market_cap": market_cap,
            "price": r.get("price"),
        })
        g["wsum"] += change * market_cap
        g["w"] += market_cap

    sectors: List[Dict[str, Any]] = []
    for major, g in groups.items():
        if g["w"] <= 0:
            continue
        stocks = sorted(g["stocks"], key=lambda s: s["market_cap"] or 0, reverse=True)
        sectors.append({
            "sector": major,
            "change": round(g["wsum"] / g["w"], 2),
            "market_cap": round(g["w"], 2),
            "count": len(g["stocks"]),
            "stocks": stocks[: max(1, int(top_per_sector))],
        })
    sectors.sort(key=lambda x: x["market_cap"], reverse=True)
    up = sum(1 for s in sectors if s["change"] >= 0)
    return {
        "sectors": sectors,
        "up": up,
        "down": len(sectors) - up,
        "method": "gics11_cap_weighted",
        "as_of": dt.datetime.now().isoformat(timespec="seconds"),
    }


_NAVER_MINUTE = "https://api.stock.naver.com/chart/domestic/item/{code}/minute?count=400"


def get_intraday(code: str, points: int = 80) -> Dict[str, Any]:
    """네이버 분봉으로 당일 일중 가격 흐름을 반환(히트맵 호버 스파크라인용).

    반환: {code, points:[{t:'HHMM', price}], prev_close, last, change_pct, source}
    분봉은 당일치만 제공되며, points 개로 다운샘플한다. 실패해도 빈 흐름으로 graceful.
    """
    code = str(code or "").strip()
    ck = f"intraday:{code}:{points}"
    cached = _cache_get(ck)
    if cached is not None:
        return cached

    out: Dict[str, Any] = {"code": code, "points": [], "prev_close": None,
                           "last": None, "change_pct": None, "source": "naver"}
    try:
        url = _NAVER_MINUTE.format(code=code)
        r = requests.get(url, headers=_HEADERS, timeout=_HTTP_TIMEOUT)
        arr = r.json() if r.status_code == 200 else []
        raw = [
            {"t": str(p.get("localDateTime", ""))[8:12], "price": _to_float(p.get("currentPrice"))}
            for p in arr if _to_float(p.get("currentPrice")) is not None
        ]
        # ~points 개로 균등 다운샘플(마지막 점은 항상 포함)
        if len(raw) > points > 0:
            step = len(raw) / points
            sampled = [raw[int(i * step)] for i in range(points)]
            if sampled and raw and sampled[-1] is not raw[-1]:
                sampled.append(raw[-1])
            raw = sampled
        out["points"] = raw
        if raw:
            out["last"] = raw[-1]["price"]
        # 전일 종가: 실시간 쿼트의 (현재가 - 부호있는 change) 로 산출.
        # change_pct 는 prev_close·last 로 자체 재계산해 부호/값 일관성 보장
        # (네이버 fluctuationsRatio 와 방향객체가 장중 순간적으로 엇갈리는 경우 방지).
        q = _naver_stock(code)
        if q and q.get("price") is not None and q.get("change") is not None:
            out["prev_close"] = round(q["price"] - q["change"], 2)
            out["last"] = q.get("price")
        elif raw:
            out["prev_close"] = raw[0]["price"]
        if out["prev_close"] and out["last"] is not None and out["prev_close"] != 0:
            out["change_pct"] = round((out["last"] - out["prev_close"]) / out["prev_close"] * 100, 2)
    except Exception as e:  # noqa: BLE001
        out["error"] = str(e)

    _cache_set(ck, out)
    return out


def get_ticks() -> Dict[str, Any]:
    """main.py /api/market/snapshot, /api/market/stream 용 통합 ticks.

    KOSPI/KOSDAQ 지수 + 주요 10종목. 준실시간(네이버) → pykrx 폴백.
    절대 공백 금지: 모든 종목이 실패해도 지수/캐시값으로 최소 채움.
    """
    ck = "ticks:all"
    cached = _cache_get(ck)
    if cached is not None:
        return cached

    ticks: List[Dict[str, Any]] = []

    for idx_name in ("KOSPI", "KOSDAQ"):
        q = get_index(idx_name)
        if q.get("price") is not None:
            ticks.append({
                "symbol": q["symbol"], "display": q["display"],
                "price": q["price"], "change": q.get("change_pct"),
                "change_abs": q.get("change"),
                "asset_type": "index", "source": q.get("source"),
            })

    universe_by_code = {r.get("symbol"): r for r in _get_kospi_market_rows()}
    for code, name, sector in WATCH_STOCKS:
        row = universe_by_code.get(code)
        if row and row.get("price") is not None:
            ticks.append({
                "symbol": code, "display": row.get("display") or name,
                "price": row.get("price"),
                "change": row.get("change"),
                "change_abs": row.get("change_abs"),
                "asset_type": "stock",
                "sector": row.get("sector") or sector,
                "source": row.get("source"),
            })
            continue
        q = get_quote(code)
        if q.get("price") is not None:
            ticks.append({
                "symbol": code, "display": name,
                "price": int(q["price"]) if q["price"] is not None else None,
                "change": q.get("change_pct"),
                "change_abs": q.get("change"),
                "asset_type": "stock", "sector": q.get("sector") or sector, "source": q.get("source"),
            })

    stocks = [t for t in ticks if t.get("asset_type") == "stock"]
    advancers = sum(1 for t in stocks if (t.get("change") or 0) > 0)
    decliners = sum(1 for t in stocks if (t.get("change") or 0) < 0)

    result = {
        "ticks": ticks,
        "breadth": {"advancers": advancers, "decliners": decliners, "new_highs": 0},
        "as_of": dt.datetime.now().isoformat(),
        "transport": "price_service(naver+pykrx+kospi-all)",
    }

    # 모든 소스 실패로 ticks 가 비면 최후 캐시 반환 (절대 공백 금지)
    if not ticks:
        stale = _cache_get(ck, allow_stale=True)
        if stale is not None and stale.get("ticks"):
            stale_out = dict(stale)
            stale_out["transport"] = "price_service(stale-cache)"
            return stale_out
        # 그래도 없으면 빈 구조라도 일관된 형태로 반환
        return result

    _cache_set(ck, result)
    return result
