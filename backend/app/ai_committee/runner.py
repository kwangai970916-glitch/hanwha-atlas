from __future__ import annotations

import datetime as dt
from typing import Any

from ..data_loader import load_dart_events, load_market_summary, load_news, load_sectors, load_stocks
from ..models import DISCLAIMER
from ..security_analysis import SecurityAnalysisEngine, SecurityDataLoader
from .agents import (
    BearCaseAgent,
    FundamentalAgent,
    InsurancePMAgent,
    MacroAgent,
    RiskManagerAgent,
    SentimentNewsAgent,
    TechnicalAgent,
    ValuationAgent,
)
from .agents.base import CommitteeContext


class AICommitteeRunner:
    """Deep multi-agent AI investment committee.

    The contract is inspired by virattt/ai-hedge-fund's agent debate pattern,
    but customized for insurance general-account equity PM governance.
    """

    def review(
        self,
        symbol: str,
        idea: str = "보유종목 투자 thesis 재점검",
        event: str = "manual_review",
        portfolio_overrides: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        stock = _find_stock(symbol)
        if stock is None:
            return None

        security_report = _load_security_report(stock["symbol"])
        sector = _find_sector(stock["sector"])
        news = [item for item in load_news() if stock["symbol"] in item.get("symbols", [])]
        darts = [item for item in load_dart_events() if item.get("symbol") == stock["symbol"]]
        portfolio = _portfolio_context(stock, security_report, portfolio_overrides or {})
        context = CommitteeContext(
            symbol=stock["symbol"],
            idea=idea,
            event=event,
            stock=stock,
            sector=sector,
            news=news,
            darts=darts,
            portfolio=portfolio,
            security_report=security_report,
        )

        analytical_agents = [
            FundamentalAgent(),
            ValuationAgent(),
            TechnicalAgent(),
            SentimentNewsAgent(),
            MacroAgent(),
            RiskManagerAgent(),
            BearCaseAgent(),
        ]
        opinions = [agent.analyze(context) for agent in analytical_agents]
        debate = _build_debate(opinions)
        scenarios = _scenario_analysis(security_report, opinions)
        final_view = _insurance_pm_view(context, opinions, debate, scenarios)
        opinions.append(InsurancePMAgent().analyze_final(context, final_view))
        memo = _memo(stock, idea, event, opinions, final_view, portfolio, debate, scenarios)

        return {
            "schema_version": "committee_review.v1",
            "source_inspiration": "virattt/ai-hedge-fund customized for insurance PM",
            "depth_profile": {
                "level": "deep_multi_agent",
                "agent_count": len(opinions),
                "data_mode": "sample-first",
                "stages": ["context", "agent_analysis", "debate", "scenario", "pm_decision"],
            },
            "symbol": stock["symbol"],
            "name": stock["name"],
            "sector": stock["sector"],
            "idea": idea,
            "event": event,
            "agent_opinions": opinions,
            "debate": debate,
            "scenario_analysis": scenarios,
            "risk_review": {
                "portfolio_weight": portfolio["current_weight"],
                "sector_weight": portfolio["sector_weight"],
                "active_risk": portfolio["active_risk"],
                "daily_pnl_bp": portfolio["daily_pnl_bp"],
                "risk_flags": final_view["risk_flags"],
                "insurance_constraints": final_view["insurance_constraints"],
            },
            "final_view": final_view,
            "committee_memo": memo,
            "as_of": dt.datetime.now().isoformat(timespec="seconds"),
            "mode": "deep-sample-first-committee",
            "disclaimer": DISCLAIMER,
        }


def build_triggers() -> list[dict[str, Any]]:
    triggers: list[dict[str, Any]] = []
    for row in load_stocks():
        momentum = float(row["momentum"])
        sector = _find_sector(row["sector"])
        sector_strength = float(sector.get("relative_strength", 50)) if sector else 50
        if momentum >= 88:
            triggers.append({"symbol": row["symbol"], "name": row["name"], "trigger_type": "price_momentum", "severity": "high" if momentum >= 90 else "medium", "reason": f"모멘텀 {momentum:.0f}점으로 단기 가격/수급 점검 필요"})
        if row["valuation"] == "부담":
            triggers.append({"symbol": row["symbol"], "name": row["name"], "trigger_type": "valuation_pressure", "severity": "medium", "reason": "밸류에이션 부담 구간 진입으로 bear case 검토 필요"})
        if sector_strength >= 88:
            triggers.append({"symbol": row["symbol"], "name": row["name"], "trigger_type": "sector_concentration", "severity": "medium", "reason": f"{row['sector']} 섹터 강세에 따른 포트폴리오 집중도 점검"})
    return triggers[:8]


def _load_security_report(symbol: str) -> dict[str, Any]:
    try:
        context = SecurityDataLoader().load_context(symbol)
        report = SecurityAnalysisEngine().analyze(context).to_dict()
        report["raw_context"] = {
            "technical": context.technical,
            "valuation": context.valuation,
            "quote": context.quote,
            "portfolio_position": context.portfolio_position,
        }
        report["technical_snapshot"] = context.technical
        return report
    except Exception:
        return {
            "financial_analysis": {},
            "valuation_analysis": {},
            "portfolio_impact": {},
            "evidence_stack": [],
            "counter_evidence": [],
            "scenario_analysis": {},
            "thesis_break_conditions": [],
            "raw_context": {},
        }


def _find_stock(symbol: str) -> dict[str, Any] | None:
    key = symbol.strip().lower()
    aliases = {"삼성전자": "005930", "하이닉스": "000660", "sk하이닉스": "000660"}
    normalized = aliases.get(key, symbol.strip())
    return next((row for row in load_stocks() if row["symbol"] == normalized or row["name"].lower() == key), None)


def _find_sector(sector: str) -> dict[str, Any]:
    return next((row for row in load_sectors() if row["sector"] == sector), {})


def _portfolio_context(stock: dict[str, Any], report: dict[str, Any], overrides: dict[str, Any]) -> dict[str, float]:
    p = report.get("portfolio_impact", {})
    is_semis = stock["sector"] == "반도체"
    current = float(overrides.get("current_weight", p.get("current_weight", 18.0 if stock["symbol"] == "005930" else 7.5)))
    sector_weight = float(overrides.get("sector_weight", p.get("sector_weight_after", 28.0 if is_semis else 12.0)))
    return {
        "current_weight": current,
        "sector_weight": sector_weight,
        "active_risk": float(overrides.get("active_risk", 1.8 if is_semis else 0.9)),
        "daily_pnl_bp": float(overrides.get("daily_pnl_bp", 22.0 if float(stock["momentum"]) >= 88 else 9.0)),
    }


def _build_debate(opinions: list[dict[str, Any]]) -> dict[str, Any]:
    positives = [o for o in opinions if o["stance"] in {"Positive", "Supportive"}]
    warnings = [o for o in opinions if o["stance"] in {"Overheated", "Concentration Warning", "Expectation Priced-In Risk", "Negative"}]
    return {
        "agreements": [
            {"point": "투자 thesis는 실적 revision과 섹터 리더십 확인이 핵심", "agents": ["Fundamental", "Macro"]},
            {"point": "추가 확대는 risk budget과 timing discipline이 필요", "agents": ["Technical", "Risk Manager", "Insurance PM"]},
        ],
        "disagreements": [
            {"point": "업사이드가 valuation premium을 충분히 보상하는지", "agents": ["Valuation", "Bear Case"]},
            {"point": "현재 가격에서 즉시 확대할지 조정 시 접근할지", "agents": [o["agent"] for o in warnings[:3]] or ["Technical"]},
        ],
        "contested_assumptions": ["AI/HBM capex cycle 지속", "EPS revision 지속", "외국인 수급 유지"],
        "open_questions": ["다음 실적 업데이트에서 margin expansion이 확인되는가", "업종 비중 한도 여유가 충분한가"],
        "positive_agent_count": len(positives),
        "warning_agent_count": len(warnings),
    }


def _scenario_analysis(report: dict[str, Any], opinions: list[dict[str, Any]]) -> dict[str, Any]:
    base = report.get("scenario_analysis") or {}
    return {
        "bull": {"probability": float(base.get("bull", {}).get("probability", 0.25)), "assumption": base.get("bull", {}).get("assumption", "EPS revision과 섹터 RS 지속"), "upside_pct": 18, "risk": "과도한 증액 후 변동성 확대", "pm_action": "한도 내 점진 증액"},
        "base": {"probability": float(base.get("base", {}).get("probability", 0.50)), "assumption": base.get("base", {}).get("assumption", "실적 개선 지속, 일부 기대 선반영"), "upside_pct": 8, "risk": "횡보 구간 기회비용", "pm_action": "보유/조정 시 분할 접근"},
        "bear": {"probability": float(base.get("bear", {}).get("probability", 0.25)), "assumption": base.get("bear", {}).get("assumption", "가격 상승 둔화와 수급 반전"), "upside_pct": -12, "risk": "multiple de-rating", "pm_action": "축소 또는 watchlist 하향"},
    }


def _insurance_pm_view(c: CommitteeContext, opinions: list[dict[str, Any]], debate: dict[str, Any], scenarios: dict[str, Any]) -> dict[str, Any]:
    risk_flags: list[str] = []
    for opinion in opinions:
        if opinion["stance"] in {"Concentration Warning", "Expectation Priced-In Risk", "Overheated", "Negative"}:
            risk_flags.extend(str(r) for r in opinion.get("risks", []))
    risk_flags = list(dict.fromkeys(risk_flags))[:7]
    hard_breach = any("limit" in flag for flag in risk_flags)
    if hard_breach or debate["warning_agent_count"] >= 3:
        stance, action, delta = "Watch", "즉각적 비중 확대보다는 조정 시 분할 접근", 0.0
    elif debate["positive_agent_count"] >= 4:
        stance, action, delta = "Approve", "리스크 한도 내 점진적 확대 검토", 1.0
    else:
        stance, action, delta = "Defer", "추가 근거 확인 전 보류", 0.0
    return {
        "stance": stance,
        "action": action,
        "score": 72 if stance == "Watch" else 80 if stance == "Approve" else 62,
        "confidence": 0.80,
        "summary": f"중장기 thesis는 유효하나 보험사 일반계정 관점에서는 손실 회피와 집중도 관리가 우선입니다. 권고: {action}.",
        "risk_flags": risk_flags,
        "checkpoints": ["실적 추정치 변화", "외국인/기관 수급", "업종 비중 한도", "반대 뉴스 발생 여부"],
        "insurance_constraints": {"RBC_solvency_impact": "low_direct / market_risk_watch", "liquidity_buffer": "adequate", "concentration_limit": "watch", "accounting_volatility": "watch"},
        "target_weight_delta": delta,
        "approval_gates": ["Risk Manager 확인", "PM override 기록", "다음 리뷰일 지정"],
        "next_review_trigger": "EPS revision 하향 또는 업종 RS 2주 연속 둔화",
    }


def _memo(stock: dict[str, Any], idea: str, event: str, opinions: list[dict[str, Any]], final_view: dict[str, Any], portfolio: dict[str, float], debate: dict[str, Any], scenarios: dict[str, Any]) -> str:
    lines = "\n".join(f"- **{o['agent']}**: {o['stance']} ({o['score']}) — {o['summary']}" for o in opinions)
    disagreements = "\n".join(f"- {d['point']}" for d in debate["disagreements"])
    risk_lines = "\n".join(f"- {flag}" for flag in final_view["risk_flags"]) or "- 특이 리스크 없음"
    return f"""# AI Committee Review Memo

## 1. 종목 개요
- 종목: {stock['name']} ({stock['symbol']})
- 섹터: {stock['sector']}
- 검토 아이디어: {idea}
- 이벤트: {event}

## 2. Portfolio Impact
- 종목 비중: {portfolio['current_weight']:.1f}%
- 업종 비중: {portfolio['sector_weight']:.1f}%
- 일일 손익 기여도: {portfolio['daily_pnl_bp']:.1f}bp

## 3. Agent Deliberation
{lines}

## 4. Dissenting Opinions
{disagreements}

## 5. Bull / Base / Bear
- Bull: {scenarios['bull']['assumption']} / action: {scenarios['bull']['pm_action']}
- Base: {scenarios['base']['assumption']} / action: {scenarios['base']['pm_action']}
- Bear: {scenarios['bear']['assumption']} / action: {scenarios['bear']['pm_action']}

## 6. Risk Controls
{risk_lines}

## 7. Final Committee View
{final_view['summary']}

> {DISCLAIMER}
"""
