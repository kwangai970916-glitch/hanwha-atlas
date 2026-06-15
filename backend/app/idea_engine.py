"""P1-5: AI 투자아이디어 근거접지(RAG) 엔진.

순수 프롬프트 환각을 막기 위해 **무료 실데이터(pykrx 시세/펀더멘털/수급, Google News RSS,
선택적 DART)**를 먼저 수집해 구조화 컨텍스트를 만들고, 그 컨텍스트만을 근거로 MiMo LLM이
JSON 투자아이디어를 생성하도록 강제한다. evidence[]는 수집된 실데이터(출처·수치)에만 근거하며
환각을 금지한다.

설계 원칙:
  1) 모든 외부 데이터 수집은 best-effort: 개별 실패/공백은 조용히 skip 하고, 실제로 값을
     얻은 소스만 data_sources 에 기록한다(=어떤 근거가 실재하는지 투명).
  2) pykrx by-code 쿼리만 사용(전수 ticker-list 조회 버그 우회). 종목명→코드는 by-code
     이름 역검증 + pnl._build_krx_name_to_code(있으면) + WATCH 별칭으로 해석.
  3) LLM 호출은 committee/idea 와 동일 패턴: openai SDK ChatCompletions + base_url 교체로
     MiMo(mimo-v2.5) 사용. 키 없거나 실패 시 OpenAI→Anthropic 폴백, 모두 불가면
     수집 데이터 기반 결정적(deterministic) fallback 아이디어를 생성(공백 금지).
  4) DART_API_KEY / ECOS_API_KEY 는 os.getenv 로 확인 후 있으면 사용, 없으면 graceful degrade.

공개 함수:
  build_idea(symbol_or_code, horizon=None) -> dict
    {symbol, name, thesis, stance, target_price?, horizon, key_drivers[], risks[],
     evidence[{claim, source, value}], context(요약), data_sources[], as_of, provider, ...}
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import urllib.parse
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# 상수 / 별칭
# ---------------------------------------------------------------------------

MIMO_BASE_URL = "https://api.xiaomimimo.com/v1"
MIMO_MODEL = "mimo-v2.5"

# pykrx 투자자 구분(get_market_net_purchases_of_equities 의 investor 인자)
_INVESTORS = ["외국인", "기관합계", "개인"]

# 자주 쓰는 종목 한글명 → KRX 코드 별칭(전수조회 없이 빠른 해석용; best-effort 보조)
_NAME_ALIAS: Dict[str, str] = {
    "삼성전자": "005930",
    "삼성전자우": "005935",
    "sk하이닉스": "000660",
    "하이닉스": "000660",
    "현대차": "005380",
    "기아": "000270",
    "한화에어로스페이스": "012450",
    "한화에어로": "012450",
    "한화오션": "042660",
    "hd한국조선해양": "009540",
    "두산에너빌리티": "034020",
    "kb금융": "105560",
    "신한지주": "055550",
    "lg에너지솔루션": "373220",
    "삼성바이오로직스": "207940",
    "naver": "035420",
    "네이버": "035420",
    "카카오": "035720",
    "포스코홀딩스": "005490",
    "현대모비스": "012330",
    "셀트리온": "068270",
}


def _norm_name(s: str) -> str:
    """공백/괄호/특수문자 제거 + 소문자 정규화 키."""
    return re.sub(r"[\s()（）\[\]·,./\-]", "", str(s or "")).lower()


def _today_ymd() -> str:
    return dt.date.today().strftime("%Y%m%d")


def _ymd(d: dt.date) -> str:
    return d.strftime("%Y%m%d")


def _safe_float(v: Any) -> Optional[float]:
    try:
        f = float(v)
        if f != f:  # NaN
            return None
        return f
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# 1) 종목 정규화: 한글명/6자리코드 → KRX 코드 (+ 종목명)
# ---------------------------------------------------------------------------

# 동봉 정적 name<->code 맵 (네이버 기반 전체 KOSPI/KOSDAQ ~4300종목). 클라우드에서
# pykrx 전수 ticker-list 가 죽어도 종목명 해석이 가능하도록 한다.
_STATIC_MAPS_CACHE = None


def _static_name_code_maps():
    global _STATIC_MAPS_CACHE
    if _STATIC_MAPS_CACHE is not None:
        return _STATIC_MAPS_CACHE
    norm: Dict[str, str] = {}
    c2n: Dict[str, str] = {}
    try:
        from pathlib import Path
        p = Path(__file__).resolve().parent / "data" / "krx_name_to_code.json"
        raw = json.loads(p.read_text(encoding="utf-8"))
        for name, code in raw.items():
            code = str(code).zfill(6)
            norm[_norm_name(name)] = code
            c2n.setdefault(code, name)
    except Exception:
        pass
    _STATIC_MAPS_CACHE = (norm, c2n)
    return _STATIC_MAPS_CACHE


def _naver_fundamental(code: str) -> Optional[Dict[str, Any]]:
    """네이버 모바일 integration API → PER/PBR/EPS/BPS/DIV. 클라우드 동작(무키)."""
    try:
        import requests
        r = requests.get(f"https://m.stock.naver.com/api/stock/{code}/integration",
                         headers={"User-Agent": "Mozilla/5.0"}, timeout=8)
        infos = r.json().get("totalInfos") or []
        m = {it.get("code"): it.get("value") for it in infos if isinstance(it, dict)}

        def fv(k):
            v = m.get(k)
            return _safe_float(re.sub(r"[^0-9.\-]", "", str(v))) if v else None

        out: Dict[str, Any] = {"as_of": dt.date.today().isoformat()}
        for src, dst in (("per", "PER"), ("pbr", "PBR"), ("eps", "EPS"), ("bps", "BPS")):
            v = fv(src)
            if v is not None:
                out[dst] = round(v, 4)
        dy = fv("dividendYieldRatio")
        if dy is not None:
            out["DIV"] = round(dy, 4)
        return out if len(out) > 1 else None
    except Exception:
        return None


def _ohlcv_from_naver(code: str, lookback_days: int = 180) -> Optional[Dict[str, Any]]:
    """pykrx 대체: 공유 OHLCV 소스(네이버)로 _collect_ohlcv 와 동일 산출."""
    try:
        from .ohlcv_sources import daily_ohlcv
        bars = daily_ohlcv(code, count=max(lookback_days + 10, 60))
        closes = [b["close"] for b in bars if b.get("close")]
        if len(closes) < 2:
            return None
        last = closes[-1]

        def ret_over(n):
            if len(closes) <= n or not closes[-1 - n]:
                return None
            return round((last / closes[-1 - n] - 1.0) * 100.0, 2)

        highs = [b["high"] for b in bars if b.get("high")]
        lows = [b["low"] for b in bars if b.get("low")]
        return {
            "as_of": bars[-1]["time"],
            "close": last,
            "volume": (int(bars[-1].get("volume") or 0) or None),
            "chg_1d_pct": (round((last / closes[-2] - 1.0) * 100.0, 2) if closes[-2] else None),
            "ret_5d_pct": ret_over(5),
            "ret_20d_pct": ret_over(20),
            "ret_60d_pct": ret_over(60),
            "ret_120d_pct": ret_over(120),
            "high_period": (max(highs) if highs else None),
            "low_period": (min(lows) if lows else None),
            "period_days": len(closes),
        }
    except Exception:
        return None


def _resolve_symbol(symbol_or_code: str) -> Tuple[Optional[str], Optional[str]]:
    """입력(한글명 또는 6자리코드) → (code, name). 해석 실패 시 (None, None) 또는 (None, name)."""
    raw = str(symbol_or_code or "").strip()
    if not raw:
        return None, None

    # 6자리(또는 그 이상 숫자) → 코드로 간주, zero-pad 6
    digits = re.sub(r"\D", "", raw)
    if digits and len(digits) >= 4 and len(re.sub(r"\d", "", raw)) == 0:
        code = digits.zfill(6)[-6:]
        name = _krx_name(code) or raw
        return code, name

    key = _norm_name(raw)

    # 1) 정적 별칭
    if key in _NAME_ALIAS:
        code = _NAME_ALIAS[key]
        return code, (_krx_name(code) or raw)

    # 2) 동봉 정적 name->code (네이버 기반 전체 KOSPI/KOSDAQ, 클라우드 무의존)
    norm_map, _ = _static_name_code_maps()
    if key in norm_map:
        code = norm_map[key]
        return code, (_krx_name(code) or raw)

    # 3) pnl.py 의 KRX 이름→코드 맵(있으면; by-code 기반 캐시, best-effort)
    try:
        from .pnl import _build_krx_name_to_code, _resolve_code  # type: ignore

        name_to_code = _build_krx_name_to_code()
        code = _resolve_code(raw, name_to_code)
        if code:
            return code, (_krx_name(code) or raw)
    except Exception:
        pass

    # 해석 실패: 이름만 반환(뉴스 검색 등은 이름으로 가능)
    return None, raw


def _krx_name(code: str) -> Optional[str]:
    """종목명(상장명). 동봉 정적 역맵(네이버) 우선 → pykrx 폴백. 실패 시 None."""
    _, c2n = _static_name_code_maps()
    nm = c2n.get(str(code).zfill(6))
    if nm:
        return nm
    try:
        from pykrx import stock as krx

        nm = krx.get_market_ticker_name(code)
        if nm and str(nm).strip():
            return str(nm).strip()
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# 2) 컨텍스트 수집 (각 소스 best-effort; 실패/공백은 skip)
# ---------------------------------------------------------------------------

def _collect_ohlcv(code: str, lookback_days: int = 180) -> Optional[Dict[str, Any]]:
    """pykrx OHLCV by-date → 최근 종가/거래량/기간수익률. 실패/공백 시 None."""
    try:
        from pykrx import stock as krx

        end = dt.date.today()
        start = end - dt.timedelta(days=lookback_days + 10)
        df = krx.get_market_ohlcv_by_date(_ymd(start), _ymd(end), code)
        if df is None or df.empty:
            return None
        # 컬럼: 시가/고가/저가/종가/거래량/등락률
        closes = df["종가"].dropna()
        if closes.empty:
            return None
        last = _safe_float(closes.iloc[-1])
        last_date = str(closes.index[-1])[:10]
        vol = _safe_float(df["거래량"].iloc[-1]) if "거래량" in df.columns else None

        def ret_over(n: int) -> Optional[float]:
            if len(closes) <= n:
                return None
            base = _safe_float(closes.iloc[-1 - n])
            if not base:
                return None
            return round((last / base - 1.0) * 100.0, 2)

        # 52주 고저(가용 구간 내)
        hi = _safe_float(df["고가"].max()) if "고가" in df.columns else None
        lo = _safe_float(df["저가"].min()) if "저가" in df.columns else None

        # 최근 일간 등락률(있으면)
        chg_1d = None
        if "등락률" in df.columns:
            chg_1d = _safe_float(df["등락률"].iloc[-1])
            if chg_1d is not None:
                chg_1d = round(chg_1d, 2)

        return {
            "as_of": last_date,
            "close": last,
            "volume": int(vol) if vol is not None else None,
            "chg_1d_pct": chg_1d,
            "ret_5d_pct": ret_over(5),
            "ret_20d_pct": ret_over(20),
            "ret_60d_pct": ret_over(60),
            "ret_120d_pct": ret_over(120),
            "high_period": hi,
            "low_period": lo,
            "period_days": len(closes),
        }
    except Exception:
        pass
    # 폴백: 공유 OHLCV 소스(네이버) — pykrx 가 죽은 클라우드 대비
    return _ohlcv_from_naver(code, lookback_days)


def _collect_fundamental(code: str) -> Optional[Dict[str, Any]]:
    """최신 PER/PBR/EPS/BPS/DIV. 네이버 모바일 API 우선(클라우드 동작), pykrx 폴백."""
    nv = _naver_fundamental(code)
    if nv:
        return nv
    try:
        from pykrx import stock as krx

        end = dt.date.today()
        start = end - dt.timedelta(days=120)
        df = krx.get_market_fundamental_by_date(_ymd(start), _ymd(end), code)
        if df is None or df.empty:
            return None
        row = df.iloc[-1]
        out: Dict[str, Any] = {"as_of": str(df.index[-1])[:10]}
        # 컬럼: BPS/PER/PBR/EPS/DIV/DPS (버전별 일부)
        for col in ("PER", "PBR", "EPS", "BPS", "DIV", "DPS"):
            if col in df.columns:
                v = _safe_float(row.get(col))
                if v is not None:
                    out[col] = round(v, 4)
        # 의미 있는 값이 하나도 없으면 None
        if len(out) <= 1:
            return None
        return out
    except Exception:
        return None


def _collect_investor_flows(code: str, lookback_days: int = 20) -> Optional[Dict[str, Any]]:
    """투자자별(외국인/기관/개인) 최근 N영업일 순매수(거래대금). 시장 전체 조회 후 종목 행 추출.

    get_market_net_purchases_of_equities(from, to, market, investor)는 investor별로
    시장 전체 종목의 순매수표를 반환하므로, code 행을 찾아 순매수 금액을 합산한다.
    KOSPI/KOSDAQ 중 어느 시장인지 모를 수 있어 양쪽을 시도한다.
    """
    try:
        from pykrx import stock as krx

        end = dt.date.today()
        start = end - dt.timedelta(days=lookback_days + 10)
        s, e = _ymd(start), _ymd(end)
        flows: Dict[str, Any] = {}
        net_col_candidates = ("순매수거래대금", "순매수거래량", "순매수")
        for inv in _INVESTORS:
            got = None
            for market in ("KOSPI", "KOSDAQ"):
                try:
                    df = krx.get_market_net_purchases_of_equities(s, e, market, inv)
                except Exception:
                    df = None
                if df is None or df.empty or code not in df.index:
                    continue
                row = df.loc[code]
                col = next((c for c in net_col_candidates if c in df.columns), None)
                if col is None:
                    # 첫 숫자형 컬럼 사용
                    col = next((c for c in df.columns if "순매수" in str(c)), None)
                if col is None:
                    continue
                val = _safe_float(row.get(col))
                if val is not None:
                    got = val
                    break
            if got is not None:
                # 억원 단위 환산(거래대금은 원 단위) — 가독성
                flows[inv] = round(got / 1e8, 1)
        if not flows:
            return None
        flows["unit"] = "억원(순매수, 최근%d일 합산 추정)" % lookback_days
        flows["lookback_days"] = lookback_days
        return flows
    except Exception:
        return None


def _collect_shorting(code: str, lookback_days: int = 20) -> Optional[Dict[str, Any]]:
    """공매도 거래대금/잔고(가능하면). pykrx shorting API는 버전별로 상이 → best-effort."""
    try:
        from pykrx import stock as krx

        end = dt.date.today()
        start = end - dt.timedelta(days=lookback_days + 10)
        s, e = _ymd(start), _ymd(end)
        fn = getattr(krx, "get_shorting_volume_by_date", None) \
            or getattr(krx, "get_shorting_value_by_date", None)
        if fn is None:
            return None
        df = fn(s, e, code)
        if df is None or df.empty:
            return None
        last = df.iloc[-1].to_dict()
        out = {"as_of": str(df.index[-1])[:10]}
        for k, v in last.items():
            fv = _safe_float(v)
            if fv is not None:
                out[str(k)] = round(fv, 2)
        return out if len(out) > 1 else None
    except Exception:
        return None


def _collect_news(name: str, max_items: int = 6) -> Optional[List[Dict[str, Any]]]:
    """Google News RSS(한국어) 종목명 헤드라인 최근 N건. 실패/공백 시 None."""
    try:
        import feedparser

        q = urllib.parse.quote(f"{name} 주가")
        url = f"https://news.google.com/rss/search?q={q}&hl=ko&gl=KR&ceid=KR:ko"
        feed = feedparser.parse(url)
        entries = getattr(feed, "entries", None) or []
        if not entries:
            return None
        items: List[Dict[str, Any]] = []
        for ent in entries[:max_items]:
            title = (ent.get("title") or "").strip()
            if not title:
                continue
            items.append({
                "title": title,
                "published": ent.get("published") or ent.get("updated") or "",
                "link": ent.get("link") or "",
            })
        return items or None
    except Exception:
        return None


def _collect_dart(code: str, name: str, max_items: int = 5) -> Optional[Dict[str, Any]]:
    """DART_API_KEY 있으면 최근 공시 목록 조회. 없거나 실패 시 None(graceful degrade)."""
    api_key = (os.getenv("DART_API_KEY") or "").strip()
    if not api_key:
        return None
    try:
        import requests

        end = dt.date.today()
        start = end - dt.timedelta(days=90)
        params = {
            "crtfc_key": api_key,
            "bgn_de": _ymd(start),
            "end_de": _ymd(end),
            "page_count": "100",
        }
        # DART 고유번호(corp_code) 매핑은 별도 ZIP 필요 → 1차는 종목명 키워드 매칭으로 필터.
        r = requests.get("https://opendart.fss.or.kr/api/list.json", params=params, timeout=8)
        if r.status_code != 200:
            return None
        data = r.json()
        if str(data.get("status")) not in ("000",):
            return None
        rows = data.get("list") or []
        nm_key = _norm_name(name)
        picked: List[Dict[str, Any]] = []
        for row in rows:
            corp = _norm_name(row.get("corp_name", ""))
            stock = str(row.get("stock_code", "")).strip()
            if (stock and stock == code) or (nm_key and (nm_key in corp or corp in nm_key)):
                picked.append({
                    "report_nm": row.get("report_nm"),
                    "rcept_dt": row.get("rcept_dt"),
                    "flr_nm": row.get("flr_nm"),
                })
            if len(picked) >= max_items:
                break
        if not picked:
            return None
        return {"disclosures": picked, "source": "DART opendart.fss.or.kr"}
    except Exception:
        return None


def _collect_live_quote(code: str) -> Optional[Dict[str, Any]]:
    """price_service.get_quote 준실시간 현재가(있으면). best-effort."""
    try:
        from .price_service import get_quote

        q = get_quote(code)
        if q and q.get("price") is not None:
            return {
                "price": q.get("price"),
                "change_pct": q.get("change_pct"),
                "source": q.get("source"),
            }
    except Exception:
        pass
    return None


def _collect_holding(code: str, name: str) -> Optional[Dict[str, Any]]:
    """보유종목이면 pnl.py Price_Raw 현재가/평가 정보 주입(best-effort)."""
    try:
        from . import pnl  # type: ignore

        summary = pnl.get_pnl_summary()
        holdings = summary.get("holdings") or []
        nm_key = _norm_name(name)
        for h in holdings:
            hk = _norm_name(h.get("name", ""))
            if not hk:
                continue
            if hk == nm_key or (nm_key and (nm_key in hk or hk in nm_key)) \
                    or str(h.get("live_code") or "") == code:
                return {
                    "name": h.get("name"),
                    "qty": h.get("qty"),
                    "price_raw": h.get("price"),
                    "price_kind": h.get("price_kind"),
                    "value": h.get("value"),
                    "pnl": h.get("pnl"),
                    "pnl_pct": h.get("pnl_pct"),
                }
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# 3) 구조화 컨텍스트 블록 → 프롬프트
# ---------------------------------------------------------------------------

def _build_context(code: Optional[str], name: str, horizon: Optional[str]) -> Dict[str, Any]:
    """가능한 모든 소스를 best-effort 수집하여 구조화 컨텍스트 dict + data_sources 리스트 구성."""
    ctx: Dict[str, Any] = {
        "symbol": code,
        "name": name,
        "horizon": horizon,
    }
    sources: List[str] = []

    if code:
        ohlcv = _collect_ohlcv(code)
        if ohlcv:
            ctx["price"] = ohlcv
            sources.append("pykrx:OHLCV")

        fund = _collect_fundamental(code)
        if fund:
            ctx["fundamental"] = fund
            sources.append("pykrx:fundamental(PER/PBR/DIV)")

        flows = _collect_investor_flows(code)
        if flows:
            ctx["investor_flows"] = flows
            sources.append("pykrx:net_purchases(investor)")

        short = _collect_shorting(code)
        if short:
            ctx["shorting"] = short
            sources.append("pykrx:shorting")

        live = _collect_live_quote(code)
        if live:
            ctx["live_quote"] = live
            sources.append(f"price_service:{live.get('source','live')}")

        holding = _collect_holding(code, name)
        if holding:
            ctx["holding"] = holding
            sources.append("pnl:Price_Raw(보유)")

        dart = _collect_dart(code, name)
        if dart:
            ctx["dart"] = dart
            sources.append("DART:disclosures")

    news = _collect_news(name)
    if news:
        ctx["news"] = news
        sources.append("GoogleNewsRSS")

    ctx["_data_sources"] = sources
    return ctx


def _format_context_block(ctx: Dict[str, Any]) -> str:
    """LLM 주입용 사람이 읽는 구조화 컨텍스트(JSON+요약). evidence 근거의 단일 출처."""
    safe = {k: v for k, v in ctx.items() if not k.startswith("_")}
    return json.dumps(safe, ensure_ascii=False, indent=2)


_SYSTEM_PROMPT = (
    "당신은 한국 주식 시장을 담당하는 시니어 애널리스트입니다. "
    "보험사 일반계정(장기·안정성·규제자본 민감) 관점에서 투자 판단을 합니다. "
    "반드시 아래 제공된 CONTEXT(실데이터)에 근거해서만 작성하고, CONTEXT에 없는 수치를 "
    "지어내지 마십시오(환각 금지). evidence 항목의 value는 CONTEXT에 실제로 존재하는 수치를 "
    "그대로 인용하고, source 에는 그 수치의 출처(예: pykrx OHLCV, pykrx PER/PBR, "
    "Google News, DART, 보유평가)를 명시하십시오. 수치가 부족하면 정성적 판단으로 보완하되 "
    "근거 없는 목표가/숫자를 만들지 마십시오. 출력은 한국어, 오직 JSON 한 개만 출력합니다."
)


def _user_prompt(ctx: Dict[str, Any]) -> str:
    name = ctx.get("name") or ctx.get("symbol") or "해당 종목"
    horizon = ctx.get("horizon") or "6~12개월"
    block = _format_context_block(ctx)
    schema = (
        '{\n'
        '  "thesis": "핵심 투자 논거(2~4문장)",\n'
        '  "stance": "매수|보유|매도 중 하나",\n'
        '  "target_price": 숫자 또는 null(근거 있을 때만),\n'
        '  "horizon": "투자기간",\n'
        '  "key_drivers": ["상승 동인 ...", "..."],\n'
        '  "risks": ["리스크 ...", "..."],\n'
        '  "evidence": [\n'
        '    {"claim": "주장/관찰", "source": "출처(CONTEXT 내)", "value": "인용 수치/사실"}\n'
        '  ]\n'
        '}'
    )
    return (
        f"분석 대상: {name} (코드: {ctx.get('symbol') or 'N/A'})\n"
        f"투자기간(horizon): {horizon}\n\n"
        f"=== CONTEXT (실데이터, 이 안의 수치만 근거로 사용) ===\n{block}\n\n"
        f"위 CONTEXT만을 근거로 보험사 일반계정 관점의 투자아이디어를 작성하십시오.\n"
        f"evidence는 CONTEXT에 실재하는 수치/사실만 인용(출처·값 명시). 환각 금지.\n\n"
        f"아래 JSON 스키마로만 출력(설명문/마크다운 금지):\n{schema}"
    )


# ---------------------------------------------------------------------------
# 4) LLM 호출 (MiMo → OpenAI → Anthropic) + JSON 파서
# ---------------------------------------------------------------------------

def _extract_json(text: str) -> Optional[dict]:
    """LLM 응답 텍스트에서 첫 번째 JSON 오브젝트 추출/파싱. 실패 시 None."""
    if not text:
        return None
    t = text.strip()
    # 코드펜스 제거
    t = re.sub(r"^```(?:json)?\s*", "", t)
    t = re.sub(r"\s*```$", "", t)
    try:
        return json.loads(t)
    except Exception:
        pass
    # 본문 중 첫 {...} 블록 시도(괄호 균형)
    start = t.find("{")
    if start == -1:
        return None
    depth = 0
    for i in range(start, len(t)):
        if t[i] == "{":
            depth += 1
        elif t[i] == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(t[start:i + 1])
                except Exception:
                    return None
    return None


def _call_llm(system: str, user: str) -> Tuple[Optional[dict], Optional[str], List[str]]:
    """MiMo → OpenAI → Anthropic 폴백. (parsed_json, provider, errors)."""
    errors: List[str] = []
    mimo_key = os.environ.get("MIMO_API_KEY", "").strip()
    openai_key = os.environ.get("OPENAI_API_KEY", "").strip()
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()

    # --- 1) MiMo (OpenAI 호환) ---
    if mimo_key:
        try:
            from openai import OpenAI

            client = OpenAI(api_key=mimo_key, base_url=MIMO_BASE_URL, timeout=30, max_retries=1)
            resp = client.chat.completions.create(
                model=MIMO_MODEL,
                max_tokens=1600,
                temperature=0.4,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            )
            text = resp.choices[0].message.content or ""
            parsed = _extract_json(text)
            if parsed is not None:
                return parsed, "mimo", errors
            errors.append("mimo:json_parse_failed")
        except Exception as e:
            errors.append(f"mimo:{e}")

    # --- 2) OpenAI ---
    if openai_key:
        try:
            from openai import OpenAI

            client = OpenAI(api_key=openai_key, timeout=30, max_retries=1)
            resp = client.chat.completions.create(
                model="gpt-4o-mini",
                max_tokens=1600,
                temperature=0.4,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            )
            text = resp.choices[0].message.content or ""
            parsed = _extract_json(text)
            if parsed is not None:
                return parsed, "openai", errors
            errors.append("openai:json_parse_failed")
        except Exception as e:
            errors.append(f"openai:{e}")

    # --- 3) Anthropic ---
    if anthropic_key:
        try:
            import anthropic

            client = anthropic.Anthropic(api_key=anthropic_key, timeout=30, max_retries=1)
            msg = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=1600,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
            text = msg.content[0].text
            parsed = _extract_json(text)
            if parsed is not None:
                return parsed, "anthropic", errors
            errors.append("anthropic:json_parse_failed")
        except Exception as e:
            errors.append(f"anthropic:{e}")

    if not (mimo_key or openai_key or anthropic_key):
        errors.append("no_llm_key")
    return None, None, errors


# ---------------------------------------------------------------------------
# 5) 결정적(deterministic) fallback — LLM 불가 시에도 실데이터 기반 아이디어 생성
# ---------------------------------------------------------------------------

def _deterministic_idea(ctx: Dict[str, Any]) -> dict:
    """LLM 미가용/실패 시 수집 데이터만으로 규칙기반 아이디어 + evidence 생성(공백 금지)."""
    name = ctx.get("name") or ctx.get("symbol") or "해당 종목"
    price = ctx.get("price") or {}
    fund = ctx.get("fundamental") or {}
    flows = ctx.get("investor_flows") or {}
    news = ctx.get("news") or []

    evidence: List[Dict[str, Any]] = []
    drivers: List[str] = []
    risks: List[str] = []

    ret60 = price.get("ret_60d_pct")
    ret20 = price.get("ret_20d_pct")
    close = price.get("close")
    if close is not None:
        evidence.append({
            "claim": "최근 종가",
            "source": f"pykrx OHLCV ({price.get('as_of')})",
            "value": f"{close:,.0f}원",
        })
    if ret60 is not None:
        evidence.append({
            "claim": "최근 약 3개월 주가 수익률",
            "source": "pykrx OHLCV",
            "value": f"{ret60:+.2f}%",
        })
        (drivers if ret60 >= 0 else risks).append(
            f"최근 3개월 가격 모멘텀 {ret60:+.2f}%"
        )

    per = fund.get("PER")
    pbr = fund.get("PBR")
    div = fund.get("DIV")
    if per is not None:
        evidence.append({"claim": "밸류에이션 PER", "source": "pykrx fundamental", "value": f"{per}배"})
    if pbr is not None:
        evidence.append({"claim": "밸류에이션 PBR", "source": "pykrx fundamental", "value": f"{pbr}배"})
        if pbr < 1.0:
            drivers.append(f"PBR {pbr}배로 자산가치 대비 저평가 영역")
    if div is not None and div > 0:
        evidence.append({"claim": "배당수익률", "source": "pykrx fundamental", "value": f"{div}%"})
        drivers.append(f"배당수익률 {div}% — 일반계정 인컴 매력")

    foreign = flows.get("외국인")
    inst = flows.get("기관합계")
    if foreign is not None:
        evidence.append({
            "claim": "외국인 순매수(최근 약 20일)",
            "source": "pykrx net_purchases",
            "value": f"{foreign:+.1f}억원",
        })
        (drivers if foreign >= 0 else risks).append(
            f"외국인 수급 {foreign:+.1f}억원"
        )
    if inst is not None:
        evidence.append({
            "claim": "기관 순매수(최근 약 20일)",
            "source": "pykrx net_purchases",
            "value": f"{inst:+.1f}억원",
        })

    for n in news[:3]:
        evidence.append({
            "claim": "뉴스 헤드라인",
            "source": f"Google News ({n.get('published','')})",
            "value": n.get("title"),
        })

    # 규칙기반 stance: 모멘텀/밸류/수급 점수 합산
    score = 0
    if ret60 is not None:
        score += 1 if ret60 > 0 else -1
    if pbr is not None:
        score += 1 if pbr < 1.0 else 0
    if foreign is not None:
        score += 1 if foreign > 0 else -1
    stance = "매수" if score >= 2 else ("매도" if score <= -2 else "보유")

    if not drivers:
        drivers.append("수집된 정량 동인이 제한적 — 추가 데이터 확인 필요")
    if not risks:
        risks.append("거시·업황 변동성 및 데이터 커버리지 한계")

    thesis = (
        f"{name}에 대해 수집된 실데이터(시세·밸류에이션·수급·뉴스)를 종합하면, "
        f"가격 모멘텀과 수급·밸류에이션 신호를 합산한 규칙기반 판단은 '{stance}'입니다. "
        f"LLM 생성이 불가하여 정량 규칙으로 산출된 보조 결론이며, evidence의 출처·수치를 "
        f"검토 후 운용역 판단으로 확정하십시오."
    )

    return {
        "thesis": thesis,
        "stance": stance,
        "target_price": None,
        "horizon": ctx.get("horizon") or "6~12개월",
        "key_drivers": drivers,
        "risks": risks,
        "evidence": evidence,
    }


# ---------------------------------------------------------------------------
# 6) 출력 정규화
# ---------------------------------------------------------------------------

_VALID_STANCE = {"매수", "보유", "매도"}


def _normalize_idea(raw: dict, ctx: Dict[str, Any]) -> dict:
    """LLM/fallback 결과를 표준 스키마로 정규화(키 보정·타입 정리)."""
    out: Dict[str, Any] = {}
    out["thesis"] = str(raw.get("thesis") or "").strip() or "투자 논거 미생성"

    stance = str(raw.get("stance") or "").strip()
    # 영문/변형 매핑
    smap = {"buy": "매수", "hold": "보유", "neutral": "보유", "sell": "매도",
            "강력매수": "매수", "비중확대": "매수", "비중축소": "매도", "중립": "보유"}
    stance = smap.get(stance.lower(), stance)
    out["stance"] = stance if stance in _VALID_STANCE else "보유"

    tp = raw.get("target_price")
    if isinstance(tp, str):
        tp_num = _safe_float(re.sub(r"[^\d.\-]", "", tp))
        tp = tp_num
    out["target_price"] = tp if isinstance(tp, (int, float)) else None

    out["horizon"] = str(raw.get("horizon") or ctx.get("horizon") or "6~12개월").strip()

    def _as_list(v: Any) -> List[Any]:
        if isinstance(v, list):
            return [x for x in v if x not in (None, "")]
        if v in (None, ""):
            return []
        return [v]

    out["key_drivers"] = [str(x).strip() for x in _as_list(raw.get("key_drivers"))]
    out["risks"] = [str(x).strip() for x in _as_list(raw.get("risks"))]

    evidence_out: List[Dict[str, Any]] = []
    for ev in _as_list(raw.get("evidence")):
        if isinstance(ev, dict):
            evidence_out.append({
                "claim": str(ev.get("claim") or "").strip(),
                "source": str(ev.get("source") or "").strip(),
                "value": ev.get("value") if not isinstance(ev.get("value"), (dict, list))
                else json.dumps(ev.get("value"), ensure_ascii=False),
            })
        elif ev:
            evidence_out.append({"claim": str(ev).strip(), "source": "", "value": None})
    out["evidence"] = evidence_out
    return out


# ---------------------------------------------------------------------------
# 공개 API
# ---------------------------------------------------------------------------

def build_idea(symbol_or_code: str, horizon: Optional[str] = None) -> Dict[str, Any]:
    """근거접지(RAG) 투자아이디어 생성.

    인자:
      symbol_or_code: 한글 종목명 또는 6자리 KRX 코드(예: '삼성전자' / '005930')
      horizon: 투자기간 문자열(선택). 미지정 시 '6~12개월'.

    반환(dict):
      symbol, name, thesis, stance(매수/보유/매도), target_price?, horizon,
      key_drivers[], risks[], evidence[{claim, source, value}],
      data_sources[](실제 사용된 소스), context(수집 요약), provider, as_of,
      llm_errors?(있으면), grounded(bool)
    """
    as_of = dt.datetime.now().isoformat(timespec="seconds")

    code, name = _resolve_symbol(symbol_or_code)
    display_name = name or str(symbol_or_code)

    # 종목/이름 모두 해석 불가하면 최소 구조 반환(공백 금지)
    if not code and not name:
        return {
            "symbol": None,
            "name": str(symbol_or_code),
            "thesis": "종목을 식별하지 못했습니다. 6자리 코드 또는 정확한 종목명을 입력하십시오.",
            "stance": "보유",
            "target_price": None,
            "horizon": horizon or "6~12개월",
            "key_drivers": [],
            "risks": ["종목 식별 실패"],
            "evidence": [],
            "data_sources": [],
            "context": {},
            "provider": "none",
            "grounded": False,
            "as_of": as_of,
        }

    ctx = _build_context(code, display_name, horizon)
    data_sources = ctx.get("_data_sources", [])

    user_prompt = _user_prompt(ctx)
    parsed, provider, errors = _call_llm(_SYSTEM_PROMPT, user_prompt)

    if parsed is not None:
        idea = _normalize_idea(parsed, ctx)
        grounded = bool(data_sources) and bool(idea.get("evidence"))
    else:
        # LLM 불가/실패 → 결정적 fallback(실데이터 기반)
        idea = _normalize_idea(_deterministic_idea(ctx), ctx)
        provider = "deterministic_fallback"
        grounded = bool(data_sources)

    # 수집 컨텍스트 요약(원천 수치 노출 — 검증/근거 추적용)
    context_summary = {k: v for k, v in ctx.items() if not k.startswith("_")}

    result: Dict[str, Any] = {
        "symbol": code,
        "name": display_name,
        "thesis": idea["thesis"],
        "stance": idea["stance"],
        "target_price": idea["target_price"],
        "horizon": idea["horizon"],
        "key_drivers": idea["key_drivers"],
        "risks": idea["risks"],
        "evidence": idea["evidence"],
        "data_sources": data_sources,
        "context": context_summary,
        "provider": provider or "none",
        "grounded": grounded,
        "as_of": as_of,
    }
    if errors:
        result["llm_errors"] = errors
    return result


if __name__ == "__main__":  # 간이 수동 점검
    import sys

    sym = sys.argv[1] if len(sys.argv) > 1 else "005930"
    out = build_idea(sym)
    print(json.dumps(out, ensure_ascii=False, indent=2))
