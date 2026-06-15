from __future__ import annotations

import asyncio
import datetime as dt
import json
import math
import os
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse

from .models import CommitteeReviewRequest, CommandRequest, IdeaEvaluateRequest, MorningBriefRequest, ReportGenerateRequest, SecurityAnalysisRequest, StockDiagnosisRequest
# LEGACY (frontend 미사용) — SecurityAnalysisEngine/SecurityDataLoader 와 services.* 는
# 신규 라이브 파이프라인(price_service/market_table/pnl/idea_engine/committee_runner)으로
# 대체되어 프론트엔드에서 호출되지 않는다. 다만 backend/tests 의 회귀 스위트
# (test_api / test_idea_api / test_security_analysis / test_encoding_quality)가
# 아래 심볼들과 /api 레거시 엔드포인트를 그대로 검증하므로 import·정의를 유지한다.
# import 제거 시 테스트 회귀가 발생하므로 절대 삭제하지 말 것.
from .security_analysis import SecurityAnalysisEngine, SecurityDataLoader
from .services import CommandRouter, IdeaEvaluationService, MorningBriefService, ReportFactoryService, StockDoctorService, source_list, wrap

app = FastAPI(title="AI Investment Desk OS", version="0.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# .env 로더 (python-dotenv 없이 수동 파싱). 위원회 .env 의 키들을
# 백엔드(uvicorn) 프로세스 전역(os.environ)에 주입한다.
# 이미 존재하는 환경변수는 보존(덮어쓰지 않음).
# ---------------------------------------------------------------------------

def _load_env_file() -> dict:
    """committee_engine/TradingAgents/.env 를 수동 파싱하여 os.environ 에 주입.

    - python-dotenv 의존 없음.
    - KEY=VALUE 형식만 처리. '#' 시작 줄/빈 줄/'='없는 줄은 무시.
    - 양끝 따옴표 제거, 값 앞뒤 공백 strip.
    - 이미 os.environ 에 존재(비어있지 않음)하면 보존.
    반환: {주입된키: 값길이} (디버그/검증용. 값은 노출하지 않음)
    """
    # backend/.env 또는 프로젝트 루트의 committee_engine/.env 를 순서대로 시도
    _base = Path(__file__).resolve().parent
    _candidates = [
        _base / '.env',                                                    # backend/.env
        _base.parent / '.env',                                             # 프로젝트루트/.env
        _base.parent / 'committee_engine' / 'TradingAgents' / '.env',     # 원래 위치
    ]
    env_path = next((p for p in _candidates if p.exists()), _candidates[-1])
    injected: dict = {}
    try:
        if not env_path.exists():
            return injected
        for raw in env_path.read_text(encoding="utf-8-sig").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip()
            # export KEY=... 형태 허용
            if key.startswith("export "):
                key = key[len("export "):].strip()
            if (len(value) >= 2) and (value[0] == value[-1]) and value[0] in ("'", '"'):
                value = value[1:-1]
            if not key:
                continue
            # 이미 비어있지 않은 값이 있으면 보존
            existing = os.environ.get(key)
            if existing:
                continue
            if value:
                os.environ[key] = value
                injected[key] = len(value)
    except Exception:
        # .env 로딩 실패는 치명적이지 않음 (개별 엔드포인트가 키 부재를 처리)
        return injected
    return injected


_ENV_INJECTED = _load_env_file()


@app.on_event("startup")
def _warm_caches() -> None:
    """백그라운드 상시 워머 — 시세 캐시를 주기적으로 미리 채워 모든 사용자 요청을 warm hit 시킨다.
    부팅 직후 1회 + 이후 45초마다 갱신하여 캐시가 식어 콜드(수 초)로 노출되는 일을 막는다.
    (Cross-Asset 테이블·홈탭 KPI·히트맵 전종목 집계가 대상.)"""
    import threading
    import time as _time

    def _refresh_once() -> None:
        try:
            from .market_table import warm_cache
            warm_cache()  # 해외지수/FX/원자재 yfinance + 국채 (Cross-Asset 테이블)
        except Exception:
            pass
        for _idx in ("KOSPI", "KOSDAQ"):
            try:
                from .price_service import get_index
                get_index(_idx)
            except Exception:
                pass
        try:
            from .price_service import get_market_heatmap
            get_market_heatmap()  # 전종목 KOSPI 행 캐시 예열 (히트맵 첫 진입 콜드 방지)
        except Exception:
            pass

    def _loop() -> None:
        while True:
            _refresh_once()
            _time.sleep(45)

    threading.Thread(target=_loop, name="warm-caches", daemon=True).start()


router = CommandRouter()
morning_service = MorningBriefService()
stock_service = StockDoctorService()
report_service = ReportFactoryService()
idea_service = IdeaEvaluationService()


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/api/health")
def health():
    return {"status": "ok", "service": "ai-investment-desk-os"}


@app.get("/api/data-status")
def data_status():
    # source_list() 일부 프로브가 클라우드(pykrx/엑셀 미가용)에서 예외를 던질 수 있으므로
    # 전체를 감싸 부분 실패해도 200 을 유지한다(진단/배지용 — 핵심 탭과 무관).
    try:
        sources = [source.model_dump() for source in source_list()]
    except Exception as e:
        sources = [{"name": "data_status", "status": "error", "detail": str(e)[:200]}]
    result = {
        # 실제 라이브 데이터 파이프라인 상태:
        #   시세=네이버 준실시간 + pykrx 폴백 / 시황·테이블=infomax 엑셀 / 위원회 LLM=MiMo.
        "mode": "live: naver+pykrx / infomax-excel / mimo-committee",
        "sources": sources,
    }
    return wrap("data_status", result, confidence=0.9).model_dump()


# ---------------------------------------------------------------------------
# Market data — pykrx SSE stream
# ---------------------------------------------------------------------------

def _fetch_pykrx_ticks() -> dict:
    """KR 준실시간 ticks (네이버 폴링 1차 + pykrx 폴백). 절대 공백 금지.

    내부 구현은 app.price_service 로 위임한다. 함수명은 호환을 위해 유지.
    """
    try:
        from .price_service import get_ticks
        return get_ticks()
    except Exception as e:
        return {"ticks": [], "breadth": {"advancers": 0, "decliners": 0, "new_highs": 0},
                "as_of": dt.datetime.now().isoformat(), "transport": f"error:{e}"}


def _estimate_price_as_of_day() -> str:
    """시세 데이터 소스의 기준일을 추정(영업일 기준).

    실제 소스 기준일을 못 얻을 때 사용하는 폴백:
      - KST 기준 현재 시각.
      - 평일 09:00 이전(장 시작 전)에는 전 영업일을, 그 외(장중/장후)에는 당일을 기준일로.
      - 주말(토/일)은 직전 금요일로 역행.
    반환: 'YYYY-MM-DD'
    """
    now_kst = dt.datetime.utcnow() + dt.timedelta(hours=9)
    day = now_kst.date()
    # 장 시작(09:00) 전이면 전일 종가가 최신 기준
    if now_kst.weekday() < 5 and (now_kst.hour * 100 + now_kst.minute) < 900:
        day = day - dt.timedelta(days=1)
    # 주말이면 직전 금요일로
    while day.weekday() >= 5:
        day = day - dt.timedelta(days=1)
    return day.isoformat()


def _price_as_of_from_ticks(data: dict) -> str:
    """ticks 응답에서 시세 기준일(price_as_of)을 도출.

    우선순위:
      1) 개별 tick 의 'as_of_day'(pykrx 폴백 시 실제 종가일) 중 최댓값.
      2) 없으면 응답의 'as_of'(소스 호출 시각)에서 날짜 부분.
      3) 그래도 없으면 영업일 추정.
    """
    try:
        days = [str(t.get("as_of_day"))[:10] for t in data.get("ticks", [])
                if isinstance(t, dict) and t.get("as_of_day")]
        if days:
            return max(days)
    except Exception:
        pass
    as_of = data.get("as_of")
    if isinstance(as_of, str) and len(as_of) >= 10:
        return as_of[:10]
    return _estimate_price_as_of_day()


@app.get("/api/market/snapshot")
def market_snapshot():
    data = _fetch_pykrx_ticks()
    if isinstance(data, dict):
        data = _enrich_market_payload(data)
    return data


def _enrich_market_payload(data: dict) -> dict:
    """Add stream/snapshot metadata without mutating the cached price payload."""
    out = dict(data)
    out["price_as_of"] = _price_as_of_from_ticks(out)
    out["fetched_at"] = dt.datetime.now().isoformat(timespec="seconds")
    out.setdefault("provider_status", "ok" if out.get("ticks") else "empty")
    return out


@app.get("/api/market/stream")
async def market_stream(request: Request, limit: Optional[int] = None):
    async def generator():
        sent = 0
        while True:
            if await request.is_disconnected():
                break
            try:
                data = await asyncio.get_running_loop().run_in_executor(None, _fetch_pykrx_ticks)
                if isinstance(data, dict):
                    data = _enrich_market_payload(data)
                else:
                    data = {
                        "ticks": [],
                        "provider_status": "invalid_payload",
                        "fetched_at": dt.datetime.now().isoformat(timespec="seconds"),
                    }
            except Exception as e:
                data = {
                    "ticks": [],
                    "provider_status": f"error:{e}",
                    "fetched_at": dt.datetime.now().isoformat(timespec="seconds"),
                }
            yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
            sent += 1
            if limit is not None and sent >= limit:
                break
            await asyncio.sleep(10)
    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@app.get("/api/market/sectors")
def market_sectors():
    try:
        from .price_service import get_sector_returns
        return {"sectors": get_sector_returns(), "method": "market_cap_weighted"}
    except Exception as e:
        return {"sectors": [], "error": str(e)}


@app.get("/api/market/breadth")
def market_breadth():
    """시장 폭(상승/하락/보합) + 지수 기여 상·하위 드라이버 단일 집계."""
    try:
        from .price_service import get_market_breadth
        return get_market_breadth()
    except Exception as e:
        return {"up": 0, "down": 0, "flat": 0, "total": 0,
                "top_drivers": [], "bottom_drivers": [], "error": str(e)}


@app.get("/api/market/heatmap")
def market_heatmap(top_per_sector: int = 40):
    """Finviz 스타일 그룹 히트맵: GICS 11 대분류 그룹 + 대표 종목 타일.

    셀 크기=시총, 색=등락률. 미분류 종목은 제외. 호버 일중 흐름은
    /api/market/intraday/{code} 로 별도 조회한다.
    """
    try:
        from .price_service import get_market_heatmap
        return get_market_heatmap(top_per_sector=top_per_sector)
    except Exception as e:
        return {"sectors": [], "error": str(e)}


@app.get("/api/market/intraday/{code}")
def market_intraday(code: str, points: int = 80):
    """종목 당일 분봉 흐름(스파크라인용). points 개로 다운샘플."""
    from .price_service import get_intraday
    return get_intraday(code, points=points)


@app.get("/api/market/candles/{symbol}")
def market_candles(symbol: str, period: str = "1M"):
    def yahoo_candles(sym: str, range_: str) -> list[dict]:
        import requests
        y_range = {"1D": "5d", "1W": "1mo", "1M": "1mo", "3M": "3mo", "1Y": "1y"}.get(range_, "1mo")
        url = (
            "https://query1.finance.yahoo.com/v8/finance/chart/"
            + urllib.parse.quote(sym, safe="")
            + f"?range={y_range}&interval=1d"
        )
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=8)
        js = r.json() if r.ok else {}
        result = (js.get("chart", {}).get("result") or [None])[0]
        if not result:
            return []
        ts = result.get("timestamp") or []
        q = ((result.get("indicators", {}).get("quote") or [{}])[0])
        opens, highs, lows, closes = (q.get("open") or []), (q.get("high") or []), (q.get("low") or []), (q.get("close") or [])
        vols = q.get("volume") or []
        out = []
        for i, t in enumerate(ts):
            try:
                vals = [opens[i], highs[i], lows[i], closes[i]]
                if any(v is None for v in vals):
                    continue
                d = dt.datetime.utcfromtimestamp(int(t)).strftime("%Y-%m-%d")
                vol = vols[i] if i < len(vols) and vols[i] is not None else 0
                out.append({"time": d, "open": float(vals[0]), "high": float(vals[1]),
                            "low": float(vals[2]), "close": float(vals[3]), "volume": float(vol)})
            except Exception:
                continue
        return out

    is_index = symbol in ("^KS11", "^KQ11")
    is_kr = is_index or bool(re.fullmatch(r"\d{6}", symbol))
    # 요청 기간 → 거래일 봉 개수
    count_map = {"1D": 2, "1W": 7, "1M": 24, "3M": 66, "1Y": 252}
    count = count_map.get(period, 24)
    try:
        if is_kr:
            # KR 종목/지수: 네이버 fchart→siseJson→yfinance(.KS/.KQ). pykrx 는 클라우드에서
            # 죽으므로 사용하지 않는다(공유 OHLCV 소스 사용).
            from .ohlcv_sources import daily_ohlcv
            candles = daily_ohlcv(symbol, count=max(count, 2))
            if candles:
                candles = candles[-count:]  # 요청 기간으로 트림
        else:
            candles = yahoo_candles(symbol, period)  # US/글로벌 티커
        out = _reconcile_candles_with_live(symbol, candles, is_index)
        if not candles:
            out["error"] = "no candle data"
        return out
    except Exception as e:
        return {"candles": [], "last_close": None, "error": str(e)}


def _reconcile_candles_with_live(symbol: str, candles: list[dict], is_index: bool) -> dict:
    """KPI(실시간 네이버)와 캔들(pykrx 일봉) 종가 불일치 해소.
    지수는 get_index 실시간 가격으로 마지막 캔들 종가를 보정하고 last_close 를 함께 내려보낸다."""
    if not candles:
        return {"candles": candles, "last_close": None}
    last_close = candles[-1].get("close")
    try:
        if is_index:
            from .price_service import get_index
            key = {"^KS11": "KOSPI", "^KQ11": "KOSDAQ"}.get(symbol, symbol)
            q = get_index(key)
            live = q.get("price")
            if live:
                today_str = dt.date.today().strftime("%Y-%m-%d")
                last = candles[-1]
                if last.get("time") == today_str:
                    # 오늘 일봉이 이미 있으면 종가만 실시간으로 덮어쓰기
                    last["close"] = float(live)
                    last["high"] = max(last.get("high", live), float(live))
                    last["low"] = min(last.get("low", live), float(live))
                else:
                    # 오늘 일봉이 아직 없으면 실시간 캔들 1개 추가
                    base = float(last.get("close", live))
                    candles.append({"time": today_str, "open": base, "high": max(base, float(live)),
                                    "low": min(base, float(live)), "close": float(live), "volume": 0.0})
                last_close = float(live)
        elif re.fullmatch(r"\d{6}", symbol):
            # 종목: 마지막 봉 종가를 실시간 네이버 시세로 맞춰 KPI/Drawer 표시가와 일치시킨다.
            from .price_service import get_quote
            q = get_quote(symbol)
            live = q.get("price")
            if live:
                today_str = dt.date.today().strftime("%Y-%m-%d")
                last = candles[-1]
                if last.get("time") == today_str:
                    last["close"] = float(live)
                    last["high"] = max(last.get("high", live), float(live))
                    last["low"] = min(last.get("low", live), float(live))
                last_close = float(live)
    except Exception:
        pass
    return {"candles": candles, "last_close": last_close}


@app.get("/api/market/universe")
def market_universe(
    q: str = "",
    limit: int = 100,
    sector: str = "",
    min_market_cap: float = 0,
    direction: str = "all",
    sort: str = "contribution",
    order: str = "desc",
):
    from .price_service import get_kospi_universe
    return get_kospi_universe(
        q=q,
        limit=limit,
        sector=sector,
        min_market_cap=min_market_cap,
        direction=direction,
        sort=sort,
        order=order,
    )


@app.get("/api/market/table")
def market_table_endpoint():
    from .market_table import get_market_table
    return get_market_table()


@app.get("/api/market/kpi")
def market_kpi():
    """KPI 행 직결 집계.

    형태: {kospi, kosdaq, usdkrw, vix, wti, gold} 각 {value, change}.
      - kospi/kosdaq: price_service (네이버 준실시간 + pykrx 폴백). change = 전일대비 %.
      - usdkrw/vix/wti/gold: yfinance (market_table 재사용). change = 1일 변동 %.
      - 빈값은 null (프론트가 처리).
    """
    from .price_service import get_index
    from .market_table import get_yf_metric
    from concurrent.futures import ThreadPoolExecutor

    def idx_kpi(name: str) -> tuple[dict, Optional[str]]:
        q = get_index(name)
        day = q.get("as_of_day")
        # change = 전일대비 %(하위호환 유지), change_pt = 포인트 변화(PM 가독성)
        return ({"value": q.get("price"), "change": q.get("change_pct"),
                 "change_pct": q.get("change_pct"), "change_pt": q.get("change")},
                str(day)[:10] if day else None)

    now = dt.datetime.now()
    # 6개 외부호출(KOSPI/KOSDAQ + yfinance 4종)을 병렬로 — 콜드캐시에서 sum→max 로 단축.
    with ThreadPoolExecutor(max_workers=6) as _ex:
        _f = {
            "kospi":  _ex.submit(idx_kpi, "KOSPI"),
            "kosdaq": _ex.submit(idx_kpi, "KOSDAQ"),
            "usdkrw": _ex.submit(get_yf_metric, "USDKRW=X"),
            "vix":    _ex.submit(get_yf_metric, "^VIX"),
            "wti":    _ex.submit(get_yf_metric, "CL=F"),
            "gold":   _ex.submit(get_yf_metric, "GC=F"),
        }
    kospi, kospi_day = _f["kospi"].result()
    kosdaq, kosdaq_day = _f["kosdaq"].result()
    price_days: list[str] = [d for d in (kospi_day, kosdaq_day) if d]
    payload = {
        "kospi":  kospi,
        "kosdaq": kosdaq,
        "usdkrw": _f["usdkrw"].result(),
        "vix":    _f["vix"].result(),
        "wti":    _f["wti"].result(),
        "gold":   _f["gold"].result(),
        "as_of":  now.isoformat(timespec="seconds"),
    }
    # price_as_of: 시세 기준일(소스 실제 기준일 우선, 없으면 영업일 추정)
    payload["price_as_of"] = max(price_days) if price_days else _estimate_price_as_of_day()
    # fetched_at: 서버 수집 시각. 기존 as_of 는 호환 위해 유지.
    payload["fetched_at"] = now.isoformat(timespec="seconds")
    return payload


# ---------------------------------------------------------------------------
# Market News — 상장주식 실시간 뉴스 + 종목 태그
# ---------------------------------------------------------------------------

_NEWS_CACHE: dict = {}
_NEWS_TTL = 90  # 90초 캐시 (네이버 크롤 부하 제한)

# 주요 종목명 → KRX 코드 (뉴스 제목 태깅용 빠른 매핑)
_STOCK_TAG_MAP: list[tuple[str, str]] = [
    # 삼성전자 — 정식·약칭
    ("삼성전자", "005930"), ("삼전", "005930"),
    # SK하이닉스 — 정식·약칭
    ("SK하이닉스", "000660"), ("하이닉스", "000660"), ("닉스", "000660"),
    # LG에너지솔루션
    ("LG에너지솔루션", "373220"), ("LG엔솔", "373220"), ("엔솔", "373220"),
    # 삼성바이오로직스
    ("삼성바이오로직스", "207940"), ("삼바", "207940"), ("삼성바이오", "207940"),
    # 현대차·기아
    ("현대차", "005380"), ("현대자동차", "005380"),
    ("기아", "000270"), ("기아차", "000270"),
    # 삼성SDI
    ("삼성SDI", "006400"), ("SDI", "006400"),
    # LG화학
    ("LG화학", "051910"),
    # 포스코
    ("POSCO홀딩스", "005490"), ("포스코", "005490"), ("포스코홀딩스", "005490"),
    # 카카오·네이버
    ("카카오", "035720"), ("카카오뱅크", "323410"), ("카카오페이", "377300"),
    ("NAVER", "035420"), ("네이버", "035420"),
    # 한화그룹
    ("한화에어로스페이스", "012450"), ("한화에어로", "012450"),
    ("한화오션", "042660"), ("한화시스템", "272210"),
    # 조선·HD
    ("HD한국조선해양", "009540"), ("HD현대", "009540"),
    ("HD현대일렉트릭", "267260"), ("현대일렉", "267260"),
    # 방산
    ("두산에너빌리티", "034020"), ("두산에너빌", "034020"),
    ("LIG넥스원", "079550"), ("넥스원", "079550"),
    ("두산로보틱스", "454910"),
    # 금융
    ("KB금융", "105560"), ("KB", "105560"),
    ("신한지주", "055550"), ("신한", "055550"),
    ("하나금융", "086790"), ("하나금융지주", "086790"),
    ("우리금융", "316140"), ("우리은행", "316140"),
    ("삼성생명", "032830"), ("한화생명", "088350"),
    ("삼성화재", "000810"), ("DB손해보험", "005830"),
    ("한화손해보험", "000370"), ("한화손보", "000370"),
    # 전자·통신
    ("현대모비스", "012330"),
    ("LG전자", "066570"), ("LG디스플레이", "034220"),
    ("SK텔레콤", "017670"), ("SKT", "017670"),
    ("KT", "030200"), ("LG유플러스", "032640"),
    # 바이오·헬스
    ("셀트리온", "068270"), ("삼성바이오에피스", "207940"),
    ("유한양행", "000100"), ("종근당", "001630"), ("한미약품", "128940"),
    # 에너지·소재
    ("SK이노베이션", "096770"), ("에쓰오일", "010950"), ("S-OIL", "010950"),
    ("에코프로비엠", "247540"), ("에코비엠", "247540"),
    ("에코프로", "086520"),
    ("포스코퓨처엠", "003670"), ("포스코퓨처", "003670"),
    # 전력·케이블
    ("LS ELECTRIC", "010120"), ("LS일렉트릭", "010120"), ("LS", "010120"),
    ("이수페타시스", "007660"), ("가온전선", "000500"),
    # 항공·운송
    ("대한항공", "003490"), ("아시아나항공", "020560"),
    ("HMM", "011200"), ("팬오션", "028670"),
    # 반도체 장비·소재
    ("원익IPS", "240810"), ("피에스케이", "319660"),
    ("한미반도체", "042700"), ("HPSP", "403870"),
]


@app.get("/api/market/news")
def market_news(limit: int = 25):
    """상장주식 실시간 뉴스 — 네이버 금융 크롤 + 종목 태그.

    반환: [{title, url, time, stocks:[{name,code}], source}]
    90초 캐시로 네이버 부하 제한.
    """
    import re, requests, sys
    from bs4 import BeautifulSoup

    now_ts = time.time()
    cached = _NEWS_CACHE.get("news")
    if cached and now_ts - cached["ts"] < _NEWS_TTL:
        items = cached["items"]
        return {"items": items[:limit], "total": len(items), "cached": True}

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://finance.naver.com/",
    }

    items: list[dict] = []
    seen: set[str] = set()

    def _tag_stocks(title: str) -> list[dict]:
        found = []
        for name, code in _STOCK_TAG_MAP:
            if name in title and code not in [s["code"] for s in found]:
                found.append({"name": name, "code": code})
        return found

    def _parse_time(raw: str) -> str:
        raw = raw.strip()
        # "2026.06.05 14:32" → "14:32", "3분 전" → "3분 전"
        m = re.search(r'(\d{1,2}:\d{2})', raw)
        return m.group(1) if m else raw[:8]

    # ① 네이버 금융 메인 뉴스
    try:
        r = requests.get("https://finance.naver.com/news/mainnews.naver",
                         headers=headers, timeout=8)
        soup = BeautifulSoup(r.text, "html.parser")
        for a in soup.find_all("a", href=lambda h: h and "/news/news_read.naver" in h):
            title = a.get_text(strip=True)
            if not title or len(title) < 8 or title in seen:
                continue
            seen.add(title)
            href = a["href"]
            url = ("https://finance.naver.com" + href) if href.startswith("/") else href
            # 시간 추출: 인접 span 탐색
            time_el = a.find_next("span", class_=lambda c: c and ("date" in c or "time" in c))
            t = _parse_time(time_el.get_text()) if time_el else ""
            items.append({"title": title, "url": url, "time": t,
                          "stocks": _tag_stocks(title), "source": "naver_main"})
    except Exception:
        pass

    # ② 네이버 금융 종목 뉴스 (더 많은 종목 태그)
    try:
        r2 = requests.get(
            "https://finance.naver.com/news/news_list.naver?mode=LSS2D&section_id=101&section_id2=258",
            headers=headers, timeout=8)
        soup2 = BeautifulSoup(r2.text, "html.parser")
        for a in soup2.find_all("a", href=lambda h: h and "/news/news_read.naver" in h):
            title = a.get_text(strip=True)
            if not title or len(title) < 8 or title in seen:
                continue
            seen.add(title)
            href = a["href"]
            url = ("https://finance.naver.com" + href) if href.startswith("/") else href
            time_el = a.find_next("span", class_=lambda c: c and ("date" in c or "time" in c))
            t = _parse_time(time_el.get_text()) if time_el else ""
            items.append({"title": title, "url": url, "time": t,
                          "stocks": _tag_stocks(title), "source": "naver_stock"})
    except Exception:
        pass

    # ③ 네이버 금융 공시 (DART 대체 — 무키 접근)
    try:
        r3 = requests.get(
            "https://finance.naver.com/news/news_list.naver?mode=LSS2D&section_id=101&section_id2=259",
            headers=headers, timeout=8)
        soup3 = BeautifulSoup(r3.text, "html.parser")
        for a in soup3.find_all("a", href=lambda h: h and ("/news/news_read.naver" in h or "dart.fss.or.kr" in h)):
            title = a.get_text(strip=True)
            if not title or len(title) < 6 or title in seen:
                continue
            seen.add(title)
            href = a.get("href", "")
            url = ("https://finance.naver.com" + href) if href.startswith("/") else href
            time_el = a.find_next("span", class_=lambda c: c and ("date" in c or "time" in c))
            t = _parse_time(time_el.get_text()) if time_el else ""
            items.append({"title": title, "url": url, "time": t,
                          "stocks": _tag_stocks(title), "source": "dart",
                          "type": "dart"})
    except Exception:
        pass

    # 캐시 저장
    if items:
        _NEWS_CACHE["news"] = {"items": items, "ts": now_ts}

    return {"items": items[:limit], "total": len(items), "cached": False}


# ---------------------------------------------------------------------------
# P&L
# ---------------------------------------------------------------------------

_DEMO_HOLDINGS = [
    {"name": "삼성전자",    "live_code": "005930"},
    {"name": "SK하이닉스", "live_code": "000660"},
    {"name": "한화손해보험","live_code": "000370"},
]

@app.get("/api/pnl")
def pnl():
    from .pnl import get_pnl_summary
    result = get_pnl_summary()
    # Mock 포트폴리오(2번째 탭 데모)는 자체 7종목으로 완결 → 데모 종목 보강 생략
    if result.get("source") == "mock":
        return result
    # 데모용 — 보유종목에 세 종목 항상 포함 (중복 제거)
    existing_codes = {h.get("live_code") for h in result.get("holdings", [])}
    for demo in _DEMO_HOLDINGS:
        if demo["live_code"] not in existing_codes:
            result.setdefault("holdings", []).append({**demo, "qty": 0, "pnl": 0, "pnl_pct": 0, "value": 0})
    return result


@app.get("/api/pnl/curve")
def pnl_curve(period: str = ""):
    """손익 시계열 곡선 + BM 오버레이(포트 시작=100 리베이스).

    period: ''/MAX(전체) | 1Y | 6M | 3M | 1M (최근 N영업일 제한).
    """
    from .pnl import get_pnl_curve
    return get_pnl_curve(period or None)


@app.get("/api/pnl/risk")
def pnl_risk(period: str = ""):
    """위험지표(연율수익/변동성/MDD/베타/TE/IR/초과수익) + 정합성 메타."""
    from .pnl import get_pnl_risk
    return get_pnl_risk(period or None)


@app.get("/api/pnl/attribution")
def pnl_attribution():
    """자산군별 포트폴리오 기여 분석 (bm_name 기준 그룹화).

    반환: {groups:[{group, weight_pct, market_value, pnl, pnl_contribution_pct,
                    avg_return_pct, holdings_count}], total_market_value, total_pnl, as_of}
    """
    from .pnl import get_pnl_attribution
    return get_pnl_attribution()


@app.get("/api/pnl/trades")
def pnl_trades(
    limit: int = 50,
    offset: int = 0,
    sort: str = "date",
    order: str = "desc",
):
    """매도내역 페이지네이션 + 풍부한 컬럼.

    query params:
      limit  : 페이지 크기 (기본 50)
      offset : 시작 위치 (기본 0)
      sort   : 정렬 기준 — date | pnl | return_pct | holding_days | name (기본 date)
      order  : asc | desc (기본 desc)

    반환: {trades[], total, limit, offset, sort, order, sells_col_fallback, fetched_at}
    """
    from .pnl import get_pnl_trades
    return get_pnl_trades(limit=limit, offset=offset, sort=sort, order=order)


@app.get("/api/pnl/rolling-risk")
def pnl_rolling_risk(window: int = 60):
    """롤링 베타·IR 시계열.

    query params:
      window : 롤링 윈도우 영업일 수 (기본 60)

    반환: {dates[], beta[], ir[], window, as_of}
    """
    from .pnl import get_pnl_rolling_risk
    return get_pnl_rolling_risk(window=window)


@app.get("/api/pnl/holding-series")
def pnl_holding_series(key: str = "", period: str = "MAX"):
    """종목별 가격·BM 시계열 (드릴다운 차트용, 시작=100 리베이스).

    query params:
      key    : 종목명 또는 KRX 코드
      period : MAX(기본) | 1Y | 3M | 1M

    반환: {name, dates[], price_index[], bm_index[], bm_name, period, as_of}
    """
    if not key:
        raise HTTPException(400, "key 파라미터 필요 (종목명 또는 코드)")
    from .pnl import get_holding_series
    return get_holding_series(key, period or None)


@app.get("/api/pnl/news")
def pnl_news(codes: str = ""):
    from .pnl import _mock_enabled
    if _mock_enabled():
        from .mock_portfolio import mock_holdings_news
        return mock_holdings_news(codes)
    import sys
    items = []
    code_list = [c.strip() for c in codes.split(",") if c.strip()]

    name_map: dict[str, str] = {}
    try:
        from pykrx import stock as krx
        today = dt.date.today().strftime("%Y%m%d")
        for code in code_list:
            try:
                name = krx.get_market_ticker_name(code)
                if name:
                    name_map[code] = name
            except Exception:
                pass
    except Exception:
        pass

    for code in code_list:
        name = name_map.get(code, code)

        try:
            sitele_path = str(Path(__file__).resolve().parents[1] / "sitele")
            if sitele_path not in sys.path:
                sys.path.insert(0, sitele_path)
            import auto_data_fetcher as adf
            raw = adf.get_complete_report_data()
            for n in raw.get("newsHeadlines", [])[:10]:
                title = n.get("title", "") if isinstance(n, dict) else str(n)
                if name in title or code in title:
                    items.append({"time": dt.datetime.now().strftime("%H:%M"),
                                  "name": name, "title": title,
                                  "url": n.get("url", "") if isinstance(n, dict) else "",
                                  "type": "news"})
        except Exception:
            pass

        try:
            import OpenDartReader
            dart_key = os.environ.get("DART_API_KEY", "")
            if dart_key:
                dart = OpenDartReader.OpenDartReader(dart_key)
                today_str = dt.date.today().strftime("%Y%m%d")
                df = dart.list(code, start=today_str, end=today_str, kind="A")
                if df is not None and not df.empty:
                    for _, row in df.head(3).iterrows():
                        items.append({"time": str(row.get("rcept_dt", ""))[-6:] or dt.datetime.now().strftime("%H:%M"),
                                      "name": name, "title": str(row.get("report_nm", "")),
                                      "url": f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={row.get('rcept_no','')}",
                                      "type": "dart"})
        except Exception:
            pass

    items.sort(key=lambda x: x["time"], reverse=True)
    return {"items": items[:20]}


# ---------------------------------------------------------------------------
# Briefing agent
# ---------------------------------------------------------------------------

_briefing_cache: dict = {}


@app.get("/api/briefing/history")
def briefing_history(limit: int = 50, slot: str = ""):
    """브리핑 생성/발송 이력(최신순).

    backend/data/briefing_history.jsonl 에서 읽는다. run_briefing 성공 시 briefing.py
    내부에서 append_history 가 자동 기록하므로 별도 기록 불필요.
    쿼리: limit(기본 50), slot(premarket|intraday|close, 빈값이면 전체).
    반환: {items: [...], count: n}
    """
    from .briefing_history import list_history
    items = list_history(limit=limit, slot=(slot or None))
    return {"items": items, "count": len(items)}


@app.get("/api/briefing/schedule")
def briefing_schedule():
    """다음 브리핑 실행 예정 시각(카운트다운 UI 용).

    SLOT_SCHEDULE: premarket 07:00 / intraday 08:30 / close 16:30 KST(UTC+9).
    반환: {slots: [{slot,label,next_ts,next_epoch,seconds_until}, ...]} — next_epoch 오름차순.
    """
    from .briefing_history import next_scheduled_times
    return {"slots": next_scheduled_times()}


@app.get("/api/briefing/record-png")
def briefing_record_png(idx: int = 0):
    """이력 레코드의 PNG 파일 서빙 (과거 시황 재열람용).

    query params:
      idx : briefing_history.list_history() 결과에서 0-based 인덱스 (기본 0=최신)

    보안: png_path 는 반드시 sitele/output 하위여야 함 (경로 traversal 방지).
    """
    from .briefing_history import list_history
    from .briefing import SITELE_DIR

    records = list_history(limit=200)
    if idx < 0 or idx >= len(records):
        raise HTTPException(404, f"이력 레코드 없음 (idx={idx}, 총 {len(records)}건)")

    rec = records[idx]
    png_path = rec.get("png_path", "")
    if not png_path:
        raise HTTPException(404, "PNG 경로 없음 (해당 이력에 PNG 미포함)")

    resolved = Path(png_path).resolve()
    output_root = (SITELE_DIR / "output").resolve()
    # 경로 traversal 방지: sitele/output 하위여야 함
    try:
        resolved.relative_to(output_root)
    except ValueError:
        raise HTTPException(403, "허용되지 않은 경로 (sitele/output 하위만 허용)")

    if not resolved.exists():
        raise HTTPException(404, f"PNG 파일 없음: {resolved.name}")

    return FileResponse(str(resolved), media_type="image/png")


@app.get("/api/briefing/latest")
def briefing_latest():
    """홈 '최신 시황' 팝업/위젯용 — 가장 최근 시황 전체 결과(9섹션/PNG/interactive) 또는 이력 폴백."""
    from .briefing import get_latest_briefing
    return get_latest_briefing()


@app.post("/api/briefing/{slot}")
async def trigger_briefing(slot: str, background_tasks: BackgroundTasks):
    if slot not in ("premarket", "intraday", "close"):
        raise HTTPException(400, "slot must be premarket|intraday|close")
    _briefing_cache[slot] = {"status": "running"}
    def _run():
        from .briefing import run_briefing
        result = run_briefing(slot)
        _briefing_cache[slot] = result
    background_tasks.add_task(_run)
    return {"status": "started", "slot": slot}


@app.get("/api/briefing/{slot}/status")
def briefing_status(slot: str):
    return _briefing_cache.get(slot, {"status": "idle"})


@app.get("/api/briefing/{slot}/png")
def briefing_png(slot: str, t: str = ""):
    """슬롯 PNG 서빙.

    t: (선택) 특정 페이지 파일 경로. 장중 3페이지처럼 png_paths 가 여러 장일 때
       프론트가 페이지별 URL(?t=<path>)로 요청. 보안상 t 는 반드시 해당 슬롯의
       png_paths 목록 안에 있고 sitele/output 하위여야 서빙(경로 traversal 방지).
       t 미지정/불일치 시 대표 png_path 로 폴백.
    """
    from .briefing import SITELE_DIR

    cache = _briefing_cache.get(slot, {})
    png_paths = cache.get("png_paths") or []
    target = cache.get("png_path")

    if t:
        output_root = (SITELE_DIR / "output").resolve()
        try:
            resolved = Path(t).resolve()
            resolved.relative_to(output_root)               # traversal 방지
            allowed = {str(Path(p).resolve()) for p in png_paths} | (
                {str(Path(target).resolve())} if target else set())
            if str(resolved) in allowed and resolved.exists():
                target = str(resolved)
        except (ValueError, OSError):
            pass  # 불일치 → 대표 png_path 폴백

    if not target or not Path(target).exists():
        raise HTTPException(404, "PNG 없음 — 먼저 생성 필요")
    return FileResponse(target, media_type="image/png")


# ---------------------------------------------------------------------------
# Backtest + Claude AI idea
# ---------------------------------------------------------------------------

@app.post("/api/backtest")
def backtest(code: str = "005930", start: str = "2024-01-01",
             end: str = "", strategy: str = "ma_cross"):
    """룰베이스 백테스트.

    run_backtest(code, start, end, strategy) 4-위치인자 호출(역호환 유지).
    반환: 지표(CAGR/MDD/Sharpe/Sortino/Calmar/win_rate/turnover/vol) +
          equity_curve[{date,strategy,bm}] + trades[{date,side,price,weight_*,equity}] +
          monthly[{month,year,m,return}] + benchmark/bm_return/bm_degraded +
          assumptions(비용/체결규칙/생존편향/면책) + available_strategies. 실패 시 {error}.
    전략 5종: ma_cross(=sma), dual_momentum, bollinger, breakout52, vol_target.
    """
    from .backtest import run_backtest
    if not end:
        end = dt.date.today().isoformat()
    return run_backtest(code, start, end, strategy)


@app.get("/api/idea/radar")
def idea_radar_endpoint(keywords: str = "", horizon_months: int = 3, use_llm: bool = True,
                        use_live_factors: Optional[bool] = None):
    """Market-wide multi-factor idea radar.

    Returns a deterministic, graceful-degradation research pipeline:
    market regime, theme radar, and Top Picks 5. Relative strength is only
    one input inside the chart factor, never the sole ranking reason.

    Market Regime 은 실시간 매크로(VIX·USD/KRW·지수)와 테마 점수 분산으로 판정하고,
    use_llm=true(기본)이면 MiMo LLM 이 판정 서술/근거를 보강한다. use_llm=false 면
    규칙기반 판정만 사용(외부 LLM 호출 없음).
    """
    from .idea_radar import build_radar

    return build_radar(keywords=keywords, horizon_months=horizon_months, use_llm=use_llm,
                       use_live_factors=use_live_factors)


@app.get("/api/idea/history")
def idea_history_endpoint(with_performance: bool = False):
    """Persistent saved idea list for 3-month research-note tracking.

    with_performance=true: 각 아이디어에 current_price·tracking_return_pct·만료 여부를 실시간 보강.
    with_performance=false(기본): 기존 동작 그대로(빠름, 테스트 호환).
    """
    if with_performance:
        from .idea_radar import list_history_with_performance
        return {"items": list_history_with_performance()}
    from .idea_radar import list_history
    return {"items": list_history()}


@app.post("/api/idea/history")
async def save_idea_history(request: Request):
    """Save a radar Top Pick as a tracked research note."""
    from .idea_radar import save_history

    payload = await request.json()
    return save_history(payload.get("pick") or payload, note=payload.get("note", ""))


@app.patch("/api/idea/history/{idea_id}")
async def update_idea_history_endpoint(idea_id: str, request: Request):
    """Update saved idea status/note."""
    from .idea_radar import update_history

    payload = await request.json()
    try:
        return update_history(idea_id, status=payload.get("status"), note=payload.get("note"))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


def _parse_idea_json(text: str) -> dict:
    """LLM 응답 텍스트에서 thesis JSON 블록을 추출/파싱. 실패 시 thesis 원문 폴백."""
    import json as _json
    if not text:
        return {"thesis": ""}
    start_idx = text.find("{")
    end_idx = text.rfind("}") + 1
    if start_idx >= 0 and end_idx > start_idx:
        try:
            return _json.loads(text[start_idx:end_idx])
        except Exception:
            pass
    return {"thesis": text}


def _idea_user_prompt(prompt: str) -> str:
    return (
        f"주식 투자아이디어를 JSON으로 작성해줘:\n\n{prompt}\n\n"
        '출력: {"thesis": "...", "bull_case": "...", "bear_case": "...", '
        '"target_price": "...", "stop_loss": "...", "horizon": "..."}'
    )


def _generate_idea_llm(prompt: str) -> dict:
    """LLM 폴백 체인: MiMo(OpenAI호환) → OpenAI → Anthropic.

    - MiMo/OpenAI: openai SDK (ChatCompletions).
    - Anthropic: anthropic SDK (messages.create).
    각 단계에서 키가 없으면 건너뛰고, 호출 실패 시 다음 백엔드로 폴백.
    하나도 성공/키가 없으면 명확한 에러 메시지 반환.
    """
    user_prompt = _idea_user_prompt(prompt)
    errors: list[str] = []

    mimo_key = os.environ.get("MIMO_API_KEY", "").strip()
    openai_key = os.environ.get("OPENAI_API_KEY", "").strip()
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()

    # --- 1) MiMo (OpenAI 호환) ---
    if mimo_key:
        try:
            from openai import OpenAI
            client = OpenAI(api_key=mimo_key, base_url="https://api.xiaomimimo.com/v1")
            resp = client.chat.completions.create(
                model="mimo-v2.5",
                max_tokens=2000,
                # MiMo reasoning 모델: JSON 모드로 추론 끄고 깔끔한 JSON 강제(파싱 실패 방지)
                response_format={"type": "json_object"},
                messages=[{"role": "user", "content": user_prompt}],
            )
            text = resp.choices[0].message.content or ""
            return {"result": _parse_idea_json(text), "provider": "mimo"}
        except Exception as e:
            errors.append(f"mimo:{e}")

    # --- 2) OpenAI ---
    if openai_key:
        try:
            from openai import OpenAI
            client = OpenAI(api_key=openai_key)
            resp = client.chat.completions.create(
                model="gpt-4o-mini",
                max_tokens=1200,
                messages=[{"role": "user", "content": user_prompt}],
            )
            text = resp.choices[0].message.content or ""
            return {"result": _parse_idea_json(text), "provider": "openai"}
        except Exception as e:
            errors.append(f"openai:{e}")

    # --- 3) Anthropic ---
    if anthropic_key:
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=anthropic_key)
            msg = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=1200,
                messages=[{"role": "user", "content": user_prompt}],
            )
            text = msg.content[0].text
            return {"result": _parse_idea_json(text), "provider": "anthropic"}
        except Exception as e:
            errors.append(f"anthropic:{e}")

    if not (mimo_key or openai_key or anthropic_key):
        return {"error": "LLM 키 미설정 (MIMO_API_KEY / OPENAI_API_KEY / ANTHROPIC_API_KEY 중 하나 필요)",
                "result": None}
    return {"error": "모든 LLM 백엔드 호출 실패: " + " | ".join(errors), "result": None}


@app.post("/api/idea")
async def generate_idea(symbol: str = "삼성전자", horizon: str = "",
                        prompt: str = ""):
    """근거접지(RAG) 투자아이디어.

    1차: idea_engine.build_idea(symbol, horizon) — 무료 실데이터(pykrx 시세/펀더멘털/
         수급/공매도 + Google News RSS + 선택적 DART) 수집 후 MiMo LLM 으로 grounded
         아이디어 생성. LLM 불가 시 모듈 내부에서 결정적 fallback 으로 graceful degrade.
    폴백: build_idea 자체가 예외로 실패하면 기존 단순 프롬프트 LLM 체인(_generate_idea_llm)
         으로 회귀하여 공백 응답을 피한다.

    인자:
      symbol : 종목명/6자리코드(예: '삼성전자' / '005930'). prompt 만 온 레거시 호출도 수용.
      horizon: 투자기간(선택). 미지정 시 모듈 기본('6~12개월').
      prompt : 레거시 호환용. symbol 미지정 시 prompt 를 종목 해석 입력으로 사용.
    """
    sym = (symbol or "").strip() or (prompt or "").strip() or "삼성전자"
    try:
        from .idea_engine import build_idea
        # 단독 아이디어는 고성능 모델(pro) 사용. (아이디어랩 위원회의 다수 에이전트 발언은
        # build_idea/_call_llm 기본값 pro=False 로 표준 모델 → 속도 유지)
        return build_idea(sym, horizon=(horizon or None), pro=True)
    except Exception as e:
        # RAG 엔진 자체 실패 → 기존 단순 프롬프트 LLM 폴백(공백 금지)
        fallback_prompt = (prompt or "").strip() or f"{sym} 투자아이디어"
        out = _generate_idea_llm(fallback_prompt)
        out["engine_error"] = str(e)
        out["provider_note"] = "idea_engine 실패 → 단순 프롬프트 LLM 폴백"
        return out


# ---------------------------------------------------------------------------
# LEGACY (unused by frontend) — 결정론 샘플 기반 구버전 엔드포인트.
#   현재 프론트엔드(frontend/src)는 이 6개 엔드포인트를 호출하지 않는다
#   (api.ts 에 정의만 있고 import/호출 없음). 라이브 파이프라인
#   (market/* · pnl/* · briefing/* · idea · backtest · committee/*)으로 대체됨.
#   그러나 backend/tests 회귀 스위트가 계약을 검증하므로 정의를 유지한다.
#   삭제 금지(테스트 회귀). 신규 기능은 위 라이브 엔드포인트를 사용할 것.
# ---------------------------------------------------------------------------

@app.post("/api/command")
def command(request: CommandRequest):
    intent = router.route(request.query)
    if intent == "stock_diagnosis":
        symbol = "삼성전자" if "삼성" in request.query else request.query.replace("진단해줘", "").strip()
        result = stock_service.diagnose(symbol)
        if result is None:
            raise HTTPException(status_code=404, detail={"code": "STOCK_NOT_FOUND", "message": "종목을 찾을 수 없습니다."})
        return wrap(intent, result, confidence=result["confidence"]).model_dump()
    if intent == "report_generate":
        brief = morning_service.build()
        result = report_service.generate(brief, request.context.get("tone", "실장 보고"))
        return wrap(intent, result, confidence=result["confidence"]).model_dump()
    result = morning_service.build()
    return wrap("morning_brief", result, confidence=result["confidence"]).model_dump()


@app.post("/api/morning-brief")
def morning_brief(_: MorningBriefRequest):
    result = morning_service.build()
    return wrap("morning_brief", result, confidence=result["confidence"]).model_dump()


@app.post("/api/stock-diagnosis")
def stock_diagnosis(request: StockDiagnosisRequest):
    result = stock_service.diagnose(request.symbol)
    if result is None:
        raise HTTPException(status_code=404, detail={"code": "STOCK_NOT_FOUND", "message": "종목을 찾을 수 없습니다."})
    return wrap("stock_diagnosis", result, confidence=result["confidence"]).model_dump()


@app.post("/api/report-generate")
def report_generate(request: ReportGenerateRequest):
    result = report_service.generate(request.source_result, request.tone)
    return wrap("report_generate", result, confidence=result["confidence"]).model_dump()


@app.post("/api/ideas/evaluate")
def idea_evaluate(request: IdeaEvaluateRequest):
    result = idea_service.evaluate(request.symbol, request.portfolio_overrides)
    if result is None:
        raise HTTPException(status_code=404, detail={"code": "STOCK_NOT_FOUND", "message": "종목을 찾을 수 없습니다."})
    return wrap("idea_evaluation", result, confidence=min(result.get("evidence_score", 80) / 100, 0.9)).model_dump()


@app.post("/api/research/security-analysis")
def security_analysis(request: SecurityAnalysisRequest):
    try:
        context = SecurityDataLoader().load_context(request.symbol)
    except KeyError:
        raise HTTPException(status_code=404, detail={"code": "SECURITY_CONTEXT_NOT_FOUND", "message": "증권분석 컨텍스트를 찾을 수 없습니다."})
    report = SecurityAnalysisEngine().analyze(context).to_dict()
    return wrap("security_analysis", report, confidence=0.78).model_dump()


@app.post("/api/committee/run")
def committee_run(ticker: str, date: Optional[str] = None):
    from .committee_runner import start_run
    if not ticker or not ticker.strip():
        raise HTTPException(400, "ticker required")
    return start_run(ticker.strip(), date)


@app.get("/api/committee/status")
def committee_status(job_id: str):
    from .committee_runner import get_status
    return get_status(job_id)


@app.get("/api/committee/result")
def committee_result(job_id: str):
    from .committee_runner import get_result
    return get_result(job_id)


@app.get("/api/committee/messages/{job_id}")
def committee_messages(job_id: str, since: int = 0):
    """실행 중 에이전트 멘트 폴링 (since=마지막으로 받은 idx+1)."""
    from .committee_runner import get_messages
    return get_messages(job_id, since)


@app.get("/api/committee/latest")
def committee_latest():
    """최근 위원회 결정 조회.

    현재 세션의 가장 최근 done 잡 decision.json, 없으면 seed(samsung.json) 반환.
    형태: {ticker, input, decision, reports, is_seed} 또는 {available: false}.
    """
    from .committee_runner import get_latest_result
    return get_latest_result()


# ── 아이디에이션 위원회 (실제 멀티에이전트 발굴 토론) ──────────────
@app.post("/api/idea/committee/run")
def idea_committee_run(keywords: str = "", horizon_months: int = 3):
    from .ideation.runner import start_run
    horizon_months = max(1, min(24, horizon_months))
    kw = keywords.strip()[:200]
    return start_run(kw, horizon_months)


@app.get("/api/idea/committee/status")
def idea_committee_status(job_id: str):
    from .ideation.runner import get_status
    return get_status(job_id)


@app.get("/api/idea/committee/messages/{job_id}")
def idea_committee_messages(job_id: str, since: int = 0):
    from .ideation.runner import get_messages
    return get_messages(job_id, since)


@app.get("/api/idea/committee/result")
def idea_committee_result(job_id: str):
    from .ideation.runner import get_result
    return get_result(job_id)


@app.get("/api/idea/committee/latest")
def idea_committee_latest():
    from .ideation.runner import get_latest_result
    return get_latest_result()


# ---------------------------------------------------------------------------
# 정적 프론트엔드 서빙 (단일 서비스 배포)
# frontend/dist 가 존재하면 빌드된 SPA 를 같은 오리진에서 서빙한다.
# 모든 /api 라우트가 위에서 먼저 등록되므로 API 와 충돌하지 않는다.
# dist 가 없으면(로컬 dev: Vite 가 5173 에서 별도 구동) 마운트를 건너뛴다.
# ---------------------------------------------------------------------------
from fastapi.staticfiles import StaticFiles  # noqa: E402

_FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if _FRONTEND_DIST.is_dir():
    app.mount("/", StaticFiles(directory=str(_FRONTEND_DIST), html=True), name="frontend")
