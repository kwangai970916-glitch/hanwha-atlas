# -*- coding: utf-8 -*-
"""
한화손보 운용본부 — 장중 시황 리포트 실행기
실행 시각: 매일 08:30 (Windows 작업 스케줄러 등록 권장)

파이프라인:
  1. 국내 실시간 지수/섹터/수급 수집 (auto_data_fetcher)
  2. Claude API → 한화손보 형식 분석 텍스트 생성 (hanwha_report_text)
  3. Playwright → PNG 렌더링 (report_renderer_tele — 3페이지)
  4. 텔레그램 발송 (opt-in)
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
    import report_renderer_tele
except Exception as _render_err:
    report_renderer_tele = None
    print(f"[WARN] PNG 렌더러 비활성({_render_err}) → PNG 생략 모드")

load_env_file()


# ── 엔벨로프 → 분석 텍스트 변환 ──────────────────────────────────────────────
def _envelope_to_analysis_text(env: dict) -> str:
    """
    generate_report_sections()가 반환하는 envelope을 report_template_tele의
    init() renderAnalysis()가 기대하는 ■-헤더 형식 텍스트로 변환한다.

    출력 예:
        ■ KOSPI 흐름·주도 테마
        - 코스피는 ...
        - 외국인 ...

        ■ KOSDAQ 흐름·주도 테마
        - 코스닥은 ...

        ■ 섹터·RS 동향
        - 반도체 강세...
        - 바이오 약세...

        ■ 주요 헤드라인
        - 삼성전자 실적...
    """
    blocks: list = env.get("blocks", [])

    # block id → block 빠른 조회
    by_id = {b.get("id", ""): b for b in blocks}

    sections: list[str] = []

    # ── 1. KOSPI 흐름·주도 테마 ────────────────────────────────────────────
    kospi_block = by_id.get("kospi_theme")
    if kospi_block:
        body = kospi_block.get("body", "")
        bullets = _paragraph_to_bullets(body)
        if bullets:
            sections.append("■ KOSPI 흐름·주도 테마")
            for b in bullets:
                sections.append(f"- {b}")
            sections.append("")

    # ── 2. KOSDAQ 흐름·주도 테마 ──────────────────────────────────────────
    kosdaq_block = by_id.get("kosdaq_theme")
    if kosdaq_block:
        body = kosdaq_block.get("body", "")
        bullets = _paragraph_to_bullets(body)
        if bullets:
            sections.append("■ KOSDAQ 흐름·주도 테마")
            for b in bullets:
                sections.append(f"- {b}")
            sections.append("")

    # ── 3. 섹터·RS 동향 ───────────────────────────────────────────────────
    sector_block = by_id.get("sector_rs")
    if sector_block:
        body = sector_block.get("body", [])
        items = _normalise_list(body)
        if items:
            sections.append("■ 섹터·RS 동향")
            for item in items:
                sections.append(f"- {item}")
            sections.append("")

    # ── 4. 주요 헤드라인 ─────────────────────────────────────────────────
    headline_block = by_id.get("headlines")
    if headline_block:
        body = headline_block.get("body", [])
        items = _normalise_list(body)
        if items:
            sections.append("■ 주요 헤드라인")
            for item in items:
                sections.append(f"- {item}")
            sections.append("")

    # ── fallback: blocks에 없으면 legacy 필드 시도 ─────────────────────
    if not sections:
        legacy = env.get("legacy", "")
        if legacy:
            return legacy
        # 최소 헤더
        title = env.get("title", "장중 시황")
        stance = env.get("stance", "")
        sections.append(f"■ {title}")
        if stance:
            sections.append(f"- {stance}")

    return "\n".join(sections).strip()


def _paragraph_to_bullets(text: str) -> list[str]:
    """
    단락(str)을 '. '로 분리해 1-3개의 bullet으로 만든다.
    이미 '- '로 시작하는 줄은 그대로 처리.
    """
    if not text:
        return []
    # 이미 개행+dash 형식이면 그대로 분리
    if "\n" in text:
        lines = [l.strip().lstrip("- ").strip() for l in text.splitlines()]
        return [l for l in lines if l]
    # 마침표 기준 분리 (최대 3문장)
    sentences = [s.strip() for s in text.split(". ") if s.strip()]
    # 마지막 문장 끝 마침표 복원
    result = []
    for i, s in enumerate(sentences[:3]):
        if s and not s.endswith("."):
            s = s + "."
        if s:
            result.append(s)
    return result


def _normalise_list(body) -> list[str]:
    """
    list[str] 또는 list[dict{k,v,tone}] → list[str].
    각 항목에서 선행 '- '를 제거.
    """
    if not body:
        return []
    result = []
    for item in body:
        if isinstance(item, str):
            clean = item.strip().lstrip("- ").strip()
            if clean:
                result.append(clean)
        elif isinstance(item, dict):
            k = item.get("k", "")
            v = item.get("v", "")
            if k and v:
                result.append(f"{k}: {v}")
            elif k:
                result.append(k)
    return result


# ── 데이터 수집 ───────────────────────────────────────────────────────────
def _collect_intraday_data() -> dict:
    """장중 데이터: auto_data_fetcher(실시간) 우선, 투자자 수급은 pykrx-today로 보완."""
    now = datetime.now()

    # 1) PRIMARY: auto_data_fetcher 실시간 수집 (네이버 금융 크롤링)
    try:
        import auto_data_fetcher as adf
        raw = adf.get_complete_report_data()
        print("[장중] auto_data_fetcher 실시간 데이터 수집 성공")
    except Exception as e:
        print(f"[WARN] auto_data_fetcher 실패: {e} → 최소 fallback")
        raw = {}

    # 2) 국내 지수 (auto_data_fetcher PRIMARY)
    mi = raw.get("marketIndices", {})
    kp = mi.get("kospi", {})
    kq = mi.get("kosdaq", {})
    kospi = {
        "index": float(kp.get("index", 0)),
        "change": float(kp.get("change", 0)),
    }
    kosdaq = {
        "index": float(kq.get("index", 0)),
        "change": float(kq.get("change", 0)),
    }

    # 3) 미국 지수 (auto_data_fetcher)
    us_raw = mi.get("us_market", [])
    us_indices = {}
    for u in us_raw:
        name = u.get("name", "")
        chg  = float(u.get("change", 0))
        us_indices[name] = {
            "close":      float(u.get("close", 0)),
            "change":     chg,
            "change_str": f"{chg:+.2f}%",
        }

    # 4) 심리지표 (yfinance) — period 5d로 빈 응답 방지
    sentiment: dict = {}
    try:
        import yfinance as yf
        def _lc(t):
            for period in ("5d", "1mo"):
                try:
                    h = yf.Ticker(t).history(period=period)
                    if not h.empty:
                        return float(h["Close"].dropna().iloc[-1])
                except Exception:
                    pass
            return None
        vix    = _lc("^VIX")
        usdkrw = _lc("USDKRW=X")
        if vix:    sentiment["vix"]    = round(vix, 2)
        if usdkrw: sentiment["usdkrw"] = round(usdkrw, 1)
    except Exception as e:
        print(f"[WARN] yfinance 심리지표 실패: {e}")

    # yfinance가 못 채운 항목은 네이버 금융 폴백으로 보완
    try:
        _missing = [k for k in ("vix", "usdkrw") if not sentiment.get(k)]
        if _missing:
            from naver_macro import fetch_macro_fallback
            _nm = fetch_macro_fallback(_missing)
            sentiment.update(_nm)
            if _nm:
                print(f"[장중] 네이버 매크로 폴백 보완: {sorted(_nm)}")
    except Exception as e:
        print(f"[WARN] 네이버 매크로 폴백 실패: {e}")

    # Fear & Greed Index (alternative.me)
    try:
        import requests as _req
        fg_resp = _req.get("https://api.alternative.me/fng/?limit=1", timeout=8)
        if fg_resp.ok:
            fg_val = int(fg_resp.json()["data"][0]["value"])
            sentiment["fear_greed"] = fg_val
            print(f"[장중] Fear & Greed: {fg_val}")
    except Exception as e:
        print(f"[WARN] Fear&Greed 수집 실패: {e}")

    # 5) 투자자 수급 — auto_data_fetcher에 investor flows 없으므로 pykrx-today로 직접 수집
    #    (close-of-day 레퍼런스 모듈 미사용; pykrx를 직접 호출해 당일 실시간 수급 조회)
    investor: dict = {"individual": 0, "foreign": 0, "institution": 0}
    try:
        from pykrx import stock as krx
        today = now.strftime("%Y%m%d")
        iv = krx.get_market_trading_value_by_date(today, today, "KOSPI")
        if not iv.empty:
            row = iv.iloc[-1]
            for col in iv.columns:
                c = str(col).replace(" ", "")
                if "개인" in c:
                    investor["individual"] = int(row[col] / 1_000_000)
                elif "외국인" in c and "합계" in c:
                    investor["foreign"] = int(row[col] / 1_000_000)
                elif "기관" in c and "합계" in c:
                    investor["institution"] = int(row[col] / 1_000_000)
            print(f"[장중] pykrx 수급: 개인 {investor['individual']}억 / 외국인 {investor['foreign']}억 / 기관 {investor['institution']}억")
    except Exception as e:
        print(f"[WARN] pykrx 수급 수집 실패 (fallback 0): {e}")

    # 6) 섹터 등락률 (auto_data_fetcher PRIMARY)
    sectors = raw.get("sectorReturns", []) or []

    # 7) 상승/하락 종목 수 (breadth) — auto_data_fetcher에서 직접 추출
    breadth = {
        "up":   raw.get("kospiAdvance", 0),
        "down": raw.get("kospiDecline", 0),
    }

    # 8) 뉴스 헤드라인
    news = [
        n.get("title", "") if isinstance(n, dict) else str(n)
        for n in raw.get("newsHeadlines", [])[:8]
    ]

    # 9) 주도 테마 분류 (theme_taxonomy)
    try:
        from theme_taxonomy import aggregate_theme_returns
        kosdaq_sectors_list = raw.get("kosdaqSectors", []) or []
        theme_returns = aggregate_theme_returns(sectors)
        kosdaq_theme_returns = aggregate_theme_returns(kosdaq_sectors_list)
        print(f"[장중] 주도 테마: KOSPI {len(theme_returns)}개 / KOSDAQ {len(kosdaq_theme_returns)}개")
    except Exception as e:
        print(f"[WARN] theme_taxonomy 실패: {e}")
        theme_returns = []
        kosdaq_theme_returns = []
        kosdaq_sectors_list = raw.get("kosdaqSectors", []) or []

    # ── GICS 11 대분류 섹터 (홈탭 히트맵과 동일 소스) — theme 집계 이후 적용 ──
    try:
        import sys as _s
        _be = str(Path(__file__).resolve().parents[1])
        if _be not in _s.path:
            _s.path.insert(0, _be)
        from app.price_service import get_market_heatmap
        _hm = get_market_heatmap()
        _gics = [{"sector": x["sector"], "change": x["change"]} for x in (_hm.get("sectors") or []) if x.get("sector")]
        if _gics:
            _gics.sort(key=lambda v: v["change"], reverse=True)
            sectors = _gics
            print(f"[장중] GICS 11 대분류 섹터 {len(_gics)}개 적용")
    except Exception as e:
        print(f"[WARN] GICS 11 섹터 수집 실패(기존 유지): {e}")

    # ── 지수 기여도 (내재화) — 네이버 전종목 시총×등락률 → KOSPI 포인트 기여도 ──
    #    엑셀/외부입력 없이 price_service._with_index_contribution이 free-float
    #    정규화까지 적용해 산출(전종목 기여도 합 = 실제 지수 변동폭).
    top_contributors: list = []
    bottom_contributors: list = []
    try:
        import sys as _s
        _be = str(Path(__file__).resolve().parents[1])
        if _be not in _s.path:
            _s.path.insert(0, _be)
        from app.price_service import get_kospi_universe
        _uni = get_kospi_universe(sort="contribution", order="desc", limit=3000)
        _rows = _uni.get("stocks", []) or []

        def _to_contrib(r: dict) -> dict:
            return {
                "name": r.get("display") or r.get("symbol", ""),
                "contribution": round(float(r.get("index_contribution_pt") or 0), 3),
                "change": round(float(r.get("change") or 0), 2),
            }

        if _rows:
            top_contributors    = [_to_contrib(r) for r in _rows[:10]]
            bottom_contributors = [_to_contrib(r) for r in _rows[-10:][::-1]]
            print(f"[장중] 지수 기여도 내재화 산출: 상위 {len(top_contributors)} / 하위 {len(bottom_contributors)}종목")
    except Exception as e:
        print(f"[WARN] 지수 기여도 내재화 산출 실패(빈 값): {e}")
        _rows = []

    # ── Page 1 본문 (원본 아침시황 '섹터당 3줄' 결정론 생성 — 완전 내재화) ──
    #    GICS 11 대분류(시총가중) + 전종목 universe에서 섹터별 대표종목을 직접 추출.
    analysis_text_override = ""
    try:
        from intraday_analysis import generate_intraday_analysis_text
        from app.sector_taxonomy import to_major_sector
        from collections import defaultdict

        # 전종목 universe를 GICS 대분류로 버킷팅 → 섹터별 시총 상위 대표종목
        _buckets = defaultdict(list)
        for r in (_rows or []):
            g = to_major_sector(r.get("sector"))
            if g and g != "기타":
                _buckets[g].append(r)
        sector_reps: dict = {}
        for g, rs in _buckets.items():
            # 섹터를 실제로 움직인 종목 = |지수 기여도| 상위 (시총×등락률)
            rs.sort(key=lambda x: abs(float(x.get("index_contribution_pt") or 0)), reverse=True)
            sector_reps[g] = [
                {"name": x.get("display") or x.get("symbol", ""),
                 "change": float(x.get("change") or 0)}
                for x in rs[:5]
            ]

        _macro = None
        if us_indices:
            _macro = "전일 미국: " + ", ".join(
                f"{k} {v.get('change_str','')}" for k, v in list(us_indices.items())[:3]
            )
        _kosdaq_br = {"up": raw.get("kosdaqAdvance", 0), "down": raw.get("kosdaqDecline", 0)}

        # 1순위: 전문 애널리스트 문체(LLM, 내재화 데이터 주입)
        try:
            from hanwha_report_text import generate_intraday_page1_text
            analysis_text_override = generate_intraday_page1_text({
                "indices": {"kospi": kospi, "kosdaq": kosdaq},
                "breadth": breadth,
                "kosdaq_breadth": _kosdaq_br,
                "sectors": sectors,            # GICS 11 (시총가중)
                "sector_reps": sector_reps,    # 섹터별 대표종목(실등락)
                "top_contributors": top_contributors,
                "bottom_contributors": bottom_contributors,
                "news": [n.get("title", n) if isinstance(n, dict) else n
                         for n in (raw.get("newsHeadlines", []) or [])][:8],
                "usdkrw": sentiment.get("usdkrw"),
                "vix": sentiment.get("vix"),
                "us_indices": us_indices,
                "kosdaq_sectors": raw.get("kosdaqSectors", []) or [],
                "kosdaq_gainers": raw.get("kosdaqTopGainers", []) or raw.get("topGainers", []) or [],
                "kosdaq_losers": raw.get("kosdaqTopLosers", []) or raw.get("topLosers", []) or [],
            }) or ""
        except Exception as e:
            print(f"[WARN] Page1 전문문체 LLM 실패: {e}")
            analysis_text_override = ""

        # 2순위: 결정론 생성기(섹터당 3줄)
        if not analysis_text_override:
            analysis_text_override = generate_intraday_analysis_text(
                indices={"kospi": kospi, "kosdaq": kosdaq},
                breadth=breadth,
                kosdaq_breadth=_kosdaq_br,
                sectors=sectors,
                sector_reps=sector_reps,
                usdkrw=sentiment.get("usdkrw"),
                macro_text=_macro,
            )
            print(f"[장중] Page1 본문 결정론 폴백: {len(analysis_text_override)}자")
        else:
            print(f"[장중] Page1 본문 전문문체 LLM: {len(analysis_text_override)}자 "
                  f"(대표종목 버킷 {len(sector_reps)}개)")
    except Exception as e:
        print(f"[WARN] Page1 본문 생성 실패(LLM 엔벨로프로 폴백): {e}")

    return {
        "date": now.strftime("%Y.%m.%d"),
        "time": now.strftime("%H:%M"),
        "kr_indices": {
            "kospi":  kospi,
            "kosdaq": kosdaq,
        },
        "us_indices": us_indices,
        "investor":   investor,
        "sectors":    sectors,
        "sentiment":  sentiment,
        "breadth":    breadth,
        "news":       news,
        "kosdaq_sectors":      raw.get("kosdaqSectors", []) or [],
        "rs_kospi":            raw.get("rsData", []) or [],
        "rs_kosdaq":           raw.get("kosdaqRsData", []) or [],
        "top_gainers":         raw.get("topGainers", []) or [],
        "top_losers":          raw.get("topLosers", []) or [],
        "top_contributors":    top_contributors,
        "bottom_contributors": bottom_contributors,
        "analysis_text_override": analysis_text_override,
        "theme_returns":       theme_returns,
        "kosdaq_theme_returns": kosdaq_theme_returns,
        "adr_data":            raw.get("adrData", []) or [],
        "kosdaq_advance":      raw.get("kosdaqAdvance", 0),
        "kosdaq_decline":      raw.get("kosdaqDecline", 0),
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
            f"한화손보 운용본부 | 장중 시황\n"
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
            print(f"[장중] 텔레그램 발송 완료 → chat_id={chat_id}")
        else:
            print(f"[WARN] 텔레그램 응답 오류: {resp.status_code} {resp.text[:120]}")
    except Exception as e:
        print(f"[WARN] 텔레그램 발송 실패: {e}")


# ── 메인 ──────────────────────────────────────────────────────────────────
def main(send: bool = False, test_only: bool = True) -> str:
    print("=" * 52)
    print(f"[장중] 한화손보 운용본부 시황 리포트 시작")
    print(f"[장중] {datetime.now():%Y-%m-%d %H:%M:%S}")
    print("=" * 52)

    market_data = _collect_intraday_data()
    print(f"[장중] KOSPI {market_data['kr_indices']['kospi'].get('index',0):,.2f} "
          f"({market_data['kr_indices']['kospi'].get('change',0):+.2f}%)")

    print("[장중] Claude API 분석 텍스트 생성 중...")
    sections = generate_report_sections("intraday", market_data)
    print(f"[장중] 제목: {sections.get('title')} / 스탠스: {sections.get('stance')}")

    # Page 1 본문: 원본 '섹터당 3줄' 결정론 생성 우선, 실패 시 LLM 엔벨로프로 폴백
    analysis_text = market_data.get("analysis_text_override") or _envelope_to_analysis_text(sections)
    src = "결정론(섹터당 3줄)" if market_data.get("analysis_text_override") else "LLM 엔벨로프"
    print(f"[장중] 분석 텍스트 ({len(analysis_text)}자) — {src}")

    # 출력 디렉토리 결정 (output/<yyyymmdd>/)
    date_str = datetime.now().strftime("%Y%m%d")
    out_dir = os.path.join(HERE, "output", date_str)
    os.makedirs(out_dir, exist_ok=True)

    # 캔들 차트 생성 (best-effort)
    try:
        from generate_candle_tele import generate_candle_charts
        print("[장중] 캔들 차트 생성 중...")
        generate_candle_charts(out_dir)
        print("[장중] 캔들 차트 생성 완료")
    except Exception as e:
        print(f"[WARN] 캔들 차트 생성 실패 (렌더링은 계속): {e}")

    # news → newsHeadlines 형식 변환 [{'title': str}, ...]
    news_raw = market_data.get("news", [])
    news_headlines = [
        {"title": n} if isinstance(n, str) else n
        for n in news_raw
    ]

    # breadth에서 상승/하락 종목 수 추출
    breadth = market_data.get("breadth", {})
    kospi_advance = int(breadth.get("up", 0))
    kospi_decline = int(breadth.get("down", 0))

    # KOSDAQ breadth (kang_data에서 별도 제공되지 않으면 0)
    kosdaq_breadth = market_data.get("kosdaq_breadth", {})
    kosdaq_advance = int(kosdaq_breadth.get("up", 0))
    kosdaq_decline = int(kosdaq_breadth.get("down", 0))

    output_path = os.path.join(out_dir, "hanwha_intraday.png")

    if report_renderer_tele is None:
        print("[장중] PNG 렌더러 비활성 → 텍스트 리포트만 생성")
        if send:
            print("[장중] PNG 없음 — 텔레그램 발송 생략")
        print("[장중] 완료.")
        return ""

    print("[장중] 3페이지 PNG 렌더링 중...")
    page1_path, page2_path, page3_path = report_renderer_tele.render_full_report(
        analysis_text=analysis_text,
        output_path=output_path,
        date=market_data.get("date", ""),
        sector_returns=market_data.get("sectors"),
        top_gainers=market_data.get("top_gainers"),
        top_losers=market_data.get("top_losers"),
        top_contributors=market_data.get("top_contributors"),
        bottom_contributors=market_data.get("bottom_contributors"),
        kosdaq_sectors=market_data.get("kosdaq_sectors"),
        rs_data=market_data.get("rs_kospi"),
        kosdaq_rs_data=market_data.get("rs_kosdaq"),
        news_headlines=news_headlines,
        adr_data=market_data.get("adr_data"),
        kospi_advance=kospi_advance,
        kospi_decline=kospi_decline,
        kosdaq_advance=kosdaq_advance,
        kosdaq_decline=kosdaq_decline,
        # NEW: F1b visual widgets
        theme_returns=market_data.get("theme_returns"),
        kosdaq_theme_returns=market_data.get("kosdaq_theme_returns"),
        investor=market_data.get("investor"),
        indices=market_data.get("kr_indices"),
    )

    print(f"[장중] 저장 완료:")
    print(f"  Page1: {page1_path}")
    print(f"  Page2: {page2_path}")
    print(f"  Page3: {page3_path}")

    if send:
        _send(page1_path, sections, test_only=test_only)
    else:
        print("[장중] 텔레그램 발송 생략 (--send 옵션 없음)")

    print("[장중] 완료.")
    return page1_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="한화손보 장중 시황 리포트")
    parser.add_argument("--send", action="store_true", help="텔레그램 발송")
    parser.add_argument("--live", action="store_true", help="실채널 발송 (기본: 테스트 채팅방)")
    args = parser.parse_args()
    main(send=args.send, test_only=not args.live)
