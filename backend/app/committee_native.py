# backend/app/committee_native.py
"""네이티브(서버 내장) AI 투자위원회 엔진.

로컬 개발기에서는 committee_runner 가 committee_engine/TradingAgents 격리 venv를
subprocess 로 구동하지만, 벤더드 엔진은 라이선스·용량 문제로 저장소에서 제외되어
배포 서버(Railway 등)에는 존재하지 않는다. 이 모듈은 **동일한 산출물 계약**으로
백엔드 프로세스 안에서 직접 멀티에이전트 위원회를 구동하는 대체 엔진이다.

산출물 계약(committee_engine/TradingAgents/run_committee.py 와 동일):
  - status.json    {stage, stage_label, step, ticker, input, is_kr, ts[, error, stderr]}
  - messages.jsonl {idx, ts, agent, stage, text, icon}
  - decision.json  {ticker, input, is_kr, date, decision, reports, language}

reports 키(프론트 REPORT_TABS 와 1:1):
  market_report · sentiment_report · news_report · fundamentals_report ·
  investment_plan · investment_debate · risk_debate · trader_investment_plan ·
  final_trade_decision

LLM: MiMo → OpenAI → Anthropic 폴백 체인(한국어 자유서술).
키가 전혀 없거나 호출이 연속 실패하면 수집 데이터 기반 규칙 폴백 리포트로
graceful degrade 하여 파이프라인을 끝까지 완주한다(중단 없음).
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .idea_engine import (
    MIMO_BASE_URL,
    MIMO_MODEL,
    _build_context,
    _collect_news,
    _format_context_block,
    _resolve_symbol,
)

KOREAN_RULE = (
    "\n\n[출력 규칙]\n"
    "- 반드시 한국어 마크다운으로 작성한다. BUY/HOLD/SELL 토큰은 '매수(BUY)'처럼 병기한다.\n"
    "- 수치·티커·고유명사는 보존하고, 제공된 데이터에 없는 사실을 지어내지 않는다.\n"
    "- 데이터가 비어 있으면 '확인 불가'로 명시하고 다른 시그널로 판단한다."
)

_PERSONA = "너는 한화손해보험 일반계정 주식운용 데스크의 AI 투자위원회 소속"

_HANGUL = re.compile(r"[가-힣]")

# 단계 메타데이터: stage → (step 1-based, 한국어 라벨)  ※ run_committee.py 와 동일
_STAGE_META = {
    "starting": (0, "시작 중"),
    "analysts": (1, "애널리스트 조사 중"),
    "research_debate": (2, "Bull/Bear 투자토론 중"),
    "risk_debate": (3, "리스크 심의 중"),
    "decision": (4, "최종 결정 작성 중"),
    "done": (4, "심의 완료"),
    "error": (0, "오류 발생"),
}


# ---------------------------------------------------------------------------
# 1) 티커 정규화 (kr_normalize 의 경량 포트)
# ---------------------------------------------------------------------------

def _is_korean(ticker: str) -> bool:
    t = str(ticker or "").strip()
    if _HANGUL.search(t):
        return True
    if t.upper().endswith((".KS", ".KQ")):
        return True
    return bool(re.fullmatch(r"\d{6}", t))


def _market_suffix(code: str) -> str:
    """6자리 코드의 시장 접미사(.KS/.KQ). 조회 실패 시 .KS."""
    try:
        from pykrx import stock as krx

        if code in (krx.get_market_ticker_list(market="KOSDAQ") or []):
            return "KQ"
    except Exception:
        pass
    return "KS"


def _normalize(ticker: str) -> Tuple[str, bool, Optional[str], str]:
    """입력 → (yf_ticker, is_kr, code6, display_name)."""
    t = str(ticker or "").strip()
    if not _is_korean(t):
        return t.upper(), False, None, t.upper()
    if t.upper().endswith((".KS", ".KQ")):
        code = t[:6]
        name = code
        c, n = _resolve_symbol(code)
        return t.upper(), True, c or code, (n or name)
    code, name = _resolve_symbol(t)
    if code:
        return f"{code}.{_market_suffix(code)}", True, code, (name or t)
    return t, True, None, (name or t)


# ---------------------------------------------------------------------------
# 2) LLM 호출 (자유서술) — MiMo → OpenAI → Anthropic
# ---------------------------------------------------------------------------

def _has_any_key() -> bool:
    return any(
        os.environ.get(k, "").strip()
        for k in ("MIMO_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY")
    )


def _chat(system: str, user: str, max_tokens: int = 1200) -> Tuple[Optional[str], Optional[str]]:
    """(text, provider). 모든 공급자 실패 시 (None, None)."""
    system = system + KOREAN_RULE
    mimo_key = os.environ.get("MIMO_API_KEY", "").strip()
    openai_key = os.environ.get("OPENAI_API_KEY", "").strip()
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()

    if mimo_key:
        try:
            from openai import OpenAI

            client = OpenAI(api_key=mimo_key, base_url=MIMO_BASE_URL, timeout=90, max_retries=1)
            resp = client.chat.completions.create(
                model=MIMO_MODEL, max_tokens=max_tokens, temperature=0.4,
                # MiMo reasoning 끄기 — 발언은 산문이므로 추론토큰이 max_tokens 를 잡아먹어
                # 본문이 잘리는 것을 막고 응답을 빠르게 한다(실측 reasoning_tokens=0).
                extra_body={"chat_template_kwargs": {"enable_thinking": False}},
                messages=[{"role": "system", "content": system},
                          {"role": "user", "content": user}],
            )
            text = (resp.choices[0].message.content or "").strip()
            if text:
                return text, "mimo"
        except Exception:
            pass

    if openai_key:
        try:
            from openai import OpenAI

            client = OpenAI(api_key=openai_key, timeout=90, max_retries=1)
            resp = client.chat.completions.create(
                model="gpt-4o-mini", max_tokens=max_tokens, temperature=0.4,
                messages=[{"role": "system", "content": system},
                          {"role": "user", "content": user}],
            )
            text = (resp.choices[0].message.content or "").strip()
            if text:
                return text, "openai"
        except Exception:
            pass

    if anthropic_key:
        try:
            import anthropic

            client = anthropic.Anthropic(api_key=anthropic_key, timeout=90, max_retries=1)
            msg = client.messages.create(
                model="claude-sonnet-4-6", max_tokens=max_tokens, system=system,
                messages=[{"role": "user", "content": user}],
            )
            text = (msg.content[0].text or "").strip()
            if text:
                return text, "anthropic"
        except Exception:
            pass

    return None, None


# ---------------------------------------------------------------------------
# 3) 컨텍스트 수집
# ---------------------------------------------------------------------------

def _us_context(ticker: str) -> Dict[str, Any]:
    """미국 티커 경량 컨텍스트(yfinance + Google News). 전 항목 best-effort."""
    ctx: Dict[str, Any] = {"symbol": ticker, "name": ticker}
    sources: List[str] = []
    try:
        import yfinance as yf

        t = yf.Ticker(ticker)
        hist = t.history(period="6mo")
        if hist is not None and not hist.empty:
            close = hist["Close"]
            last = float(close.iloc[-1])
            def _ret(n: int) -> Optional[float]:
                if len(close) > n:
                    return round((last / float(close.iloc[-1 - n]) - 1) * 100, 2)
                return None
            ctx["price"] = {
                "last_close": round(last, 2),
                "return_1m_pct": _ret(21),
                "return_3m_pct": _ret(63),
                "ma20": round(float(close.tail(20).mean()), 2),
                "ma60": round(float(close.tail(60).mean()), 2),
                "high_6m": round(float(close.max()), 2),
                "low_6m": round(float(close.min()), 2),
            }
            sources.append("yfinance:OHLCV")
        info = getattr(t, "info", None) or {}
        fund = {k: info.get(k) for k in (
            "shortName", "sector", "industry", "marketCap", "trailingPE",
            "forwardPE", "priceToBook", "dividendYield", "beta",
        ) if info.get(k) is not None}
        if fund:
            ctx["fundamental"] = fund
            sources.append("yfinance:info")
            if fund.get("shortName"):
                ctx["name"] = fund["shortName"]
    except Exception:
        pass
    try:
        import urllib.parse

        import feedparser

        q = urllib.parse.quote(f"{ticker} stock")
        feed = feedparser.parse(
            f"https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en")
        items = [
            {"title": (e.get("title") or "").strip(),
             "published": e.get("published") or ""}
            for e in (getattr(feed, "entries", None) or [])[:6]
            if (e.get("title") or "").strip()
        ]
        if items:
            ctx["news"] = items
            sources.append("GoogleNewsRSS")
    except Exception:
        pass
    ctx["_data_sources"] = sources
    return ctx


def _gather_context(is_kr: bool, code: Optional[str], name: str, yf_ticker: str) -> Dict[str, Any]:
    if is_kr:
        ctx = _build_context(code, name, horizon=None)
    else:
        ctx = _us_context(yf_ticker)
    # 보유 정보 등 내부 키는 위원회 프롬프트에 그대로 쓰지 않을 이유가 없어 유지.
    return ctx


# ---------------------------------------------------------------------------
# 4) 규칙 폴백 리포트 (LLM 불가 시에도 공백 금지)
# ---------------------------------------------------------------------------

def _bullets(obj: Any, limit: int = 14) -> str:
    if isinstance(obj, dict):
        rows = [f"- {k}: {v}" for k, v in list(obj.items())[:limit]]
        return "\n".join(rows) if rows else "- 확인 불가"
    if isinstance(obj, list):
        rows = []
        for it in obj[:limit]:
            if isinstance(it, dict):
                rows.append("- " + (it.get("title") or json.dumps(it, ensure_ascii=False)[:120]))
            else:
                rows.append(f"- {it}")
        return "\n".join(rows) if rows else "- 확인 불가"
    return f"- {obj}" if obj else "- 확인 불가"


_FALLBACK_NOTE = (
    "\n\n> ⚠️ LLM 미가용으로 수집 데이터 기반 **규칙 폴백 리포트**가 표시됩니다. "
    "API 키 설정 시 전 단계가 LLM 심의로 대체됩니다."
)


def _fb_market(ctx: Dict[str, Any]) -> str:
    return ("## 기술·시장 분석 (규칙 폴백)\n\n### 가격·추세 지표\n"
            + _bullets(ctx.get("price") or ctx.get("live_quote"))
            + _FALLBACK_NOTE)


def _fb_sentiment(ctx: Dict[str, Any]) -> str:
    body = "### 수급(투자자별 순매수)\n" + _bullets(ctx.get("investor_flows"))
    if ctx.get("shorting"):
        body += "\n\n### 공매도\n" + _bullets(ctx.get("shorting"))
    return "## 심리·수급 분석 (규칙 폴백)\n\n" + body + _FALLBACK_NOTE


def _fb_news(ctx: Dict[str, Any]) -> str:
    return ("## 뉴스 분석 (규칙 폴백)\n\n### 최근 헤드라인\n"
            + _bullets(ctx.get("news")) + _FALLBACK_NOTE)


def _fb_fundamentals(ctx: Dict[str, Any]) -> str:
    return ("## 펀더멘털 분석 (규칙 폴백)\n\n### 밸류에이션·재무 지표\n"
            + _bullets(ctx.get("fundamental")) + _FALLBACK_NOTE)


# ---------------------------------------------------------------------------
# 5) 메인 파이프라인
# ---------------------------------------------------------------------------

def _excerpt(text: str, max_chars: int = 240) -> str:
    clean = re.sub(r"^#+\s+.*$", "", str(text or ""), flags=re.MULTILINE)
    clean = re.sub(r"^[-*#>]\s*", "", clean, flags=re.MULTILINE)
    clean = re.sub(r"\*+", "", clean)
    clean = " ".join(clean.split())
    if not clean.strip():
        return ""
    if len(clean) <= max_chars:
        return clean.strip()
    trunc = clean[:max_chars]
    for sep in ["다.", "요.", ".", "!", "?"]:
        idx = trunc.rfind(sep)
        if idx > max_chars // 3:
            return trunc[: idx + len(sep)].strip()
    return trunc.strip() + "…"


def _clip(text: str, n: int = 1500) -> str:
    t = str(text or "")
    return t if len(t) <= n else t[:n] + "\n…(중략)"


# '과매도(oversold)/과매수(overbought)' 기술 용어 오매칭을 lookbehind 로 차단.
_DECISION_TOKENS = [
    (re.compile(r"(?<!과)매도|SELL", re.I), "매도(SELL)"),
    (re.compile(r"(?<!과)매수|BUY", re.I), "매수(BUY)"),
    (re.compile(r"보유|관망|HOLD", re.I), "보유(HOLD)"),
]


def _first_token(segment: str) -> Optional[str]:
    """구간 내에서 가장 먼저 등장하는 판단 토큰(위치 기준, 우선순위 아님)."""
    best: Optional[Tuple[int, str]] = None
    for pat, label in _DECISION_TOKENS:
        m = pat.search(segment)
        if m and (best is None or m.start() < best[0]):
            best = (m.start(), label)
    return best[1] if best else None


def _extract_decision(final_text: str) -> str:
    """최종 리포트에서 판단 토큰 추출. '최종 결정' 라인 우선, 없으면 보유(HOLD)."""
    text = str(final_text or "")
    m = re.search(r"최종\s*결정[^\n]*", text)
    if m:
        token = _first_token(m.group(0))
        if token:
            return token
    return _first_token(text[:600]) or _first_token(text) or "보유(HOLD)"


def run_native_committee(raw_ticker: str, date: Optional[str], out_dir: str) -> int:
    """위원회 1회 완주. 산출물은 out_dir 에 기록. 성공 0 / 실패 1 반환."""
    date = date or dt.date.today().isoformat()
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    status_path = out / "status.json"
    msg_path = out / "messages.jsonl"
    msg_idx = [0]

    yf_ticker, is_kr, code, name = _normalize(raw_ticker)

    def write_status(stage: str, **extra: Any) -> None:
        step, label = _STAGE_META.get(stage, (0, stage))
        status_path.write_text(json.dumps(
            {"stage": stage, "stage_label": label, "step": step,
             "ticker": yf_ticker, "input": raw_ticker, "is_kr": is_kr,
             "engine": "native", "ts": dt.datetime.now().isoformat(), **extra},
            ensure_ascii=False), encoding="utf-8")

    def write_msg(agent: str, stage: str, text: str, icon: str = "") -> None:
        excerpt = _excerpt(text)
        if not excerpt:
            return
        entry = {"idx": msg_idx[0], "ts": dt.datetime.now().isoformat(),
                 "agent": agent, "stage": stage, "text": excerpt, "icon": icon}
        with open(str(msg_path), "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        msg_idx[0] += 1

    write_status("starting")
    try:
        ctx = _gather_context(is_kr, code, name, yf_ticker)
        ctx_block = _clip(_format_context_block(ctx), 6000)
        subject = f"{name}({yf_ticker})"
        # 키가 없으면 LLM 시도 자체를 생략(빠른 규칙 완주).
        # 키가 있어도 연속 2회 전체 실패하면 이후 단계는 규칙 폴백으로 전환.
        llm_on = _has_any_key()
        fail_streak = [0]

        def speak(system: str, user: str, fallback: str, max_tokens: int = 1200) -> str:
            if not llm_on or fail_streak[0] >= 2:
                return fallback
            text, _provider = _chat(system, user, max_tokens=max_tokens)
            if text:
                fail_streak[0] = 0
                return text
            fail_streak[0] += 1
            return fallback

        reports: Dict[str, str] = {}

        # ── 1단계: 애널리스트 4인 ────────────────────────────────────────
        write_status("analysts")
        analysts = [
            ("market_report", "기술적 애널리스트", "chart",
             f"{_PERSONA} 기술적 애널리스트다. 가격·추세·이동평균·수익률 데이터로 기술적 분석 리포트를 작성한다.",
             _fb_market(ctx)),
            ("sentiment_report", "심리 애널리스트", "heart",
             f"{_PERSONA} 심리 애널리스트다. 투자자별 수급(외국인/기관/개인 순매수)·공매도·뉴스 톤으로 시장 심리 리포트를 작성한다.",
             _fb_sentiment(ctx)),
            ("news_report", "뉴스 애널리스트", "news",
             f"{_PERSONA} 뉴스 애널리스트다. 최근 헤드라인에서 주가 영향 이슈를 추려 호재/악재로 구분해 리포트를 작성한다.",
             _fb_news(ctx)),
            ("fundamentals_report", "재무 애널리스트", "landmark",
             f"{_PERSONA} 재무 애널리스트다. 밸류에이션(PER/PBR/배당)·재무 지표로 펀더멘털 리포트를 작성한다.",
             _fb_fundamentals(ctx)),
        ]
        for key, agent, icon, system, fallback in analysts:
            user = (f"[분석 대상] {subject} · 기준일 {date}\n\n[수집 데이터(JSON)]\n{ctx_block}\n\n"
                    "위 데이터만 근거로 마크다운 리포트를 작성하라. 섹션 3~4개, 마지막에 '핵심 시사점' 1줄.")
            reports[key] = speak(system, user, fallback, max_tokens=1100)
            write_msg(agent, "analysts", reports[key], icon)

        digest = "\n\n".join(
            f"[{k}]\n{_clip(reports[k], 1200)}"
            for k in ("market_report", "sentiment_report", "news_report", "fundamentals_report"))

        # ── 2단계: Bull/Bear 투자토론 + 리서치 매니저 ──────────────────
        write_status("research_debate")
        bull = speak(
            f"{_PERSONA} Bull 리서처다. 애널리스트 보고서를 근거로 {subject} 매수론을 가장 강하게 주장한다.",
            f"[애널리스트 보고서 요약]\n{digest}\n\n매수 논거 3~5개를 근거 수치와 함께 제시하라.",
            f"## 🐂 Bull 논거 (규칙 폴백)\n\n{_bullets(ctx.get('price'))}\n" + _FALLBACK_NOTE, 900)
        write_msg("Bull 리서처", "research_debate", bull, "arrow_up")

        bear = speak(
            f"{_PERSONA} Bear 리서처다. Bull 주장을 반박하며 {subject} 의 하방 리스크를 가장 강하게 주장한다.",
            f"[애널리스트 보고서 요약]\n{digest}\n\n[Bull 주장]\n{_clip(bull, 1500)}\n\n"
            "Bull 논거를 조목조목 반박하고 하방 리스크 3~5개를 제시하라.",
            f"## 🐻 Bear 논거 (규칙 폴백)\n\n{_bullets(ctx.get('shorting') or ctx.get('news'))}\n" + _FALLBACK_NOTE, 900)
        write_msg("Bear 리서처", "research_debate", bear, "arrow_down")

        judge = speak(
            f"{_PERSONA} 리서치 매니저다. Bull/Bear 토론을 판정하고 투자계획을 확정한다.",
            f"[Bull]\n{_clip(bull, 1500)}\n\n[Bear]\n{_clip(bear, 1500)}\n\n"
            f"승자 판정과 근거, {subject} 에 대한 투자계획(방향·비중·진입 조건·모니터링 지표)을 작성하라.",
            "## 리서치 매니저 판정 (규칙 폴백)\n\n토론 데이터가 제한적이므로 중립 보유(HOLD) 관점을 유지한다."
            + _FALLBACK_NOTE, 1100)
        reports["investment_plan"] = judge
        reports["investment_debate"] = (
            f"## 🐂 Bull Case\n\n{bull}\n\n## 🐻 Bear Case\n\n{bear}\n\n"
            f"## 🧑‍⚖️ Research Manager 판단\n\n{judge}")
        write_msg("리서치 매니저", "research_debate", judge, "users")

        # ── 3단계: 리스크 3-way 심의 + 리스크 매니저 ───────────────────
        write_status("risk_debate")
        risk_views: Dict[str, str] = {}
        for label, stance in (
            ("공격", "수익 기회를 극대화하는 공격적 관점에서 이 투자계획을 평가하라."),
            ("보수", "보험 일반계정의 자본 보전 관점에서 가장 보수적으로 이 투자계획을 평가하라."),
            ("중립", "공격/보수 양쪽을 균형 있게 조정하는 중립 관점에서 이 투자계획을 평가하라."),
        ):
            risk_views[label] = speak(
                f"{_PERSONA} 리스크 토론자({label})다.",
                f"[투자계획]\n{_clip(judge, 1500)}\n\n{stance} 핵심 포인트 3개 이내.",
                f"## {label} 관점 (규칙 폴백)\n\n데이터 제한으로 {label} 관점 기본 점검 항목만 제시한다."
                + _FALLBACK_NOTE, 550)
            write_msg(f"{label} 리스크", "risk_debate", risk_views[label], "shield")

        risk_judge = speak(
            f"{_PERSONA} 리스크 매니저다. 3-way 리스크 토론을 종합해 최종 리스크 판정을 내린다.",
            f"[투자계획]\n{_clip(judge, 1200)}\n\n[공격]\n{_clip(risk_views['공격'], 800)}\n\n"
            f"[보수]\n{_clip(risk_views['보수'], 800)}\n\n[중립]\n{_clip(risk_views['중립'], 800)}\n\n"
            "승인/조건부 승인/보류 중 하나로 판정하고 손절·비중 한도 등 리스크 가드레일을 제시하라.",
            "## 리스크 매니저 판정 (규칙 폴백)\n\n데이터 제한으로 조건부 승인(소규모 비중·타이트한 손절)을 권고한다."
            + _FALLBACK_NOTE, 900)
        reports["risk_debate"] = (
            f"## ⚡ Aggressive\n\n{risk_views['공격']}\n\n## 🛡️ Conservative\n\n{risk_views['보수']}\n\n"
            f"## ⚖️ Neutral\n\n{risk_views['중립']}\n\n## 🧑‍⚖️ Risk Manager 판정\n\n{risk_judge}")
        write_msg("리스크 매니저", "risk_debate", risk_judge, "shield")

        # ── 4단계: 트레이더 + 최종 결정 ────────────────────────────────
        write_status("decision")
        trader = speak(
            f"{_PERSONA} 트레이더다. 승인된 투자계획을 실행 가능한 매매 플랜으로 구체화한다.",
            f"[투자계획]\n{_clip(judge, 1200)}\n\n[리스크 판정]\n{_clip(risk_judge, 1000)}\n\n"
            "진입가 구간·분할 매매·손절/익절 기준·실행 일정이 담긴 트레이딩 플랜을 작성하라.",
            "## 트레이딩 플랜 (규칙 폴백)\n\n분할 진입(3회)·-7% 손절·소규모 비중 기본 플랜을 적용한다."
            + _FALLBACK_NOTE, 900)
        reports["trader_investment_plan"] = trader
        write_msg("트레이더", "decision", trader, "briefcase")

        final = speak(
            f"{_PERSONA} 의장(포트폴리오 매니저)이다. 전체 심의를 종합해 최종 결정을 내린다.",
            f"[투자계획]\n{_clip(judge, 1200)}\n\n[리스크 판정]\n{_clip(risk_judge, 1000)}\n\n"
            f"[트레이딩 플랜]\n{_clip(trader, 1000)}\n\n"
            f"{subject} 에 대한 최종 결정 리포트를 작성하라. 첫 줄은 반드시 "
            "'## 최종 결정: 매수(BUY)|보유(HOLD)|매도(SELL)' 중 하나의 형식으로 시작한다. "
            "이어서 핵심 근거 3개, 리스크 가드레일, 재심의 트리거를 제시하라.",
            "## 최종 결정: 보유(HOLD)\n\nLLM 미가용으로 규칙 폴백 기준 중립 판정을 적용한다."
            + _FALLBACK_NOTE, 1100)
        reports["final_trade_decision"] = final
        decision = _extract_decision(final)
        write_msg("최종 결정", "decision", final, "gavel")

        (out / "decision.json").write_text(json.dumps(
            {"ticker": yf_ticker, "input": raw_ticker, "is_kr": is_kr,
             "date": date, "decision": decision, "reports": reports,
             "language": "ko", "engine": "native"},
            ensure_ascii=False), encoding="utf-8")
        write_status("done")
        return 0
    except Exception as e:
        import traceback

        tb = traceback.format_exc()
        write_status("error", error=str(e), stderr=tb[:2000], trace=tb[:2000])
        return 1
