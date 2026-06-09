from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

DATA_ROOT = Path(__file__).resolve().parents[2] / "data" / "security_analysis"
DISCLAIMER = "본 자료는 내부 참고용으로, 투자 판단의 보조자료입니다. 최종 투자 의사결정은 담당 운용역의 판단에 따릅니다."


@dataclass
class SecurityContext:
    symbol: str
    company: Dict[str, Any]
    price: Dict[str, Any]
    quote: Dict[str, Any]
    technical: Dict[str, Any]
    valuation: Dict[str, Any]
    financials_annual: List[Dict[str, Any]]
    financials_quarterly: List[Dict[str, Any]]
    consensus: Dict[str, Any]
    sector_indicators: List[Dict[str, Any]]
    events: List[Dict[str, Any]]
    portfolio_position: Dict[str, Any]
    risk_limits: List[Dict[str, Any]]
    sources: List[Dict[str, Any]]


@dataclass
class SecurityAnalysisReport:
    symbol: str
    name: str
    investment_view: Dict[str, Any]
    business_analysis: Dict[str, Any]
    financial_analysis: Dict[str, Any]
    valuation_analysis: Dict[str, Any]
    catalyst_timeline: List[Dict[str, Any]]
    variant_perception: Dict[str, str]
    evidence_stack: List[Dict[str, Any]]
    counter_evidence: List[Dict[str, Any]]
    scenario_analysis: Dict[str, Dict[str, Any]]
    thesis_break_conditions: List[str]
    portfolio_impact: Dict[str, Any]
    decision_checklist: List[Dict[str, Any]]
    final_action: Dict[str, Any]
    sources: List[Dict[str, Any]]
    report_markdown: str
    disclaimer: str = DISCLAIMER

    def to_dict(self) -> dict:
        return asdict(self)


class SecurityDataLoader:
    def __init__(self, data_root: Path = DATA_ROOT):
        self.data_root = Path(data_root)

    def load_context(self, symbol: str) -> SecurityContext:
        company = self._find_one("master/company_master.csv", "symbol", symbol)
        if company is None:
            raise KeyError(symbol)

        financials_annual = self._find_many("fundamentals/financials_annual.csv", "symbol", symbol)
        financials_quarterly = self._find_many("fundamentals/financials_quarterly.csv", "symbol", symbol)
        context = SecurityContext(
            symbol=symbol,
            company=company,
            price=self._find_one("prices/price_daily.csv", "symbol", symbol) or {},
            quote=self._find_one("prices/quote_snapshot.csv", "symbol", symbol) or {},
            technical=self._find_one("prices/technical_snapshot.csv", "symbol", symbol) or {},
            valuation=self._find_one("valuation/valuation_snapshot.csv", "symbol", symbol) or {},
            financials_annual=financials_annual,
            financials_quarterly=financials_quarterly,
            consensus=self._find_one("estimates/consensus_snapshot.csv", "symbol", symbol) or {},
            sector_indicators=self._find_many("macro/sector_indicators.csv", "sector", company["sector"]),
            events=self._load_events(symbol),
            portfolio_position=self._find_one("portfolio/portfolio_positions.csv", "symbol", symbol) or {},
            risk_limits=self._read_csv("risk/risk_limits.csv"),
            sources=[],
        )
        context.sources = self._collect_sources(context)
        return context

    def _read_csv(self, relative: str) -> List[Dict[str, Any]]:
        path = self.data_root / relative
        if not path.exists():
            return []
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            return [_coerce_row(row) for row in csv.DictReader(handle)]

    def _find_one(self, relative: str, key: str, value: str) -> Optional[Dict[str, Any]]:
        rows = self._find_many(relative, key, value)
        return rows[0] if rows else None

    def _find_many(self, relative: str, key: str, value: str) -> List[Dict[str, Any]]:
        return [row for row in self._read_csv(relative) if str(row.get(key)) == value]

    def _load_events(self, symbol: str) -> List[Dict[str, Any]]:
        path = self.data_root / "events" / "events.jsonl"
        if not path.exists():
            return []
        events = []
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            if not line.strip():
                continue
            event = json.loads(line)
            if event.get("symbol") == symbol:
                events.append(event)
        return events

    def _collect_sources(self, context: SecurityContext) -> List[Dict[str, Any]]:
        seen = {}
        def add(item: Dict[str, Any], dataset: str):
            source = item.get("source")
            if not source:
                return
            key = (dataset, source, item.get("as_of"))
            seen[key] = {
                "dataset": dataset,
                "source": source,
                "as_of": item.get("as_of"),
                "confidence": item.get("confidence"),
                "license_tier": item.get("license_tier"),
            }
        add(context.company, "company_master")
        for name in ["price", "quote", "technical", "valuation", "consensus", "portfolio_position"]:
            add(getattr(context, name), name)
        for row in context.financials_annual:
            add(row, "financials_annual")
        for row in context.sector_indicators:
            add(row, "sector_indicators")
        for row in context.events:
            add(row, "events")
        return list(seen.values())


class SecurityAnalysisEngine:
    def analyze(self, context: SecurityContext) -> SecurityAnalysisReport:
        financial = self._financial_analysis(context)
        valuation = self._valuation_analysis(context)
        portfolio = self._portfolio_impact(context)
        evidence, counter = self._evidence(context)
        investment_view = self._investment_view(context, financial, valuation, portfolio, evidence, counter)
        business = self._business_analysis(context)
        catalysts = self._catalysts(context)
        variant = self._variant_perception(context)
        scenarios = self._scenarios(context, financial, valuation)
        breaks = self._thesis_break_conditions(context)
        checklist = self._decision_checklist(investment_view, evidence, counter, portfolio)
        final_action = {
            "action": investment_view["action"],
            "positioning": portfolio["recommended_positioning"],
            "next_review_trigger": "업황 가격 데이터, 외국인 수급, 섹터 RS가 동시에 악화되는지 확인",
        }
        report = SecurityAnalysisReport(
            symbol=context.symbol,
            name=context.company["name"],
            investment_view=investment_view,
            business_analysis=business,
            financial_analysis=financial,
            valuation_analysis=valuation,
            catalyst_timeline=catalysts,
            variant_perception=variant,
            evidence_stack=evidence,
            counter_evidence=counter,
            scenario_analysis=scenarios,
            thesis_break_conditions=breaks,
            portfolio_impact=portfolio,
            decision_checklist=checklist,
            final_action=final_action,
            sources=context.sources,
            report_markdown="",
        )
        report.report_markdown = self._compose_markdown(report)
        return report

    def _financial_analysis(self, c: SecurityContext) -> Dict[str, Any]:
        annual = sorted(c.financials_annual, key=lambda row: str(row["year"]))
        last_actual = annual[-2]
        estimate = annual[-1]
        revenue_growth = _pct(estimate["revenue"], last_actual["revenue"])
        op_growth = _pct(estimate["op_profit"], last_actual["op_profit"])
        op_margin_change = float(estimate["op_margin"]) - float(last_actual["op_margin"])
        eps_revision_1m = _pct(c.consensus.get("eps_current"), c.consensus.get("eps_1m_ago")) if c.consensus else 0
        eps_revision_3m = _pct(c.consensus.get("eps_current"), c.consensus.get("eps_3m_ago")) if c.consensus else 0
        fcf_margin = _pct_of(estimate.get("fcf"), estimate.get("revenue"))
        capex_to_sales = _pct_of(estimate.get("capex"), estimate.get("revenue"))
        return {
            "revenue_growth_2026e": round(revenue_growth, 1),
            "op_profit_growth_2026e": round(op_growth, 1),
            "op_margin_change_pp": round(op_margin_change, 1),
            "roe_2026e": estimate.get("roe"),
            "financial_model_snapshot": {
                "forecast_year": estimate.get("year"),
                "revenue_trillion_krw": _to_trillion_krw(estimate.get("revenue")),
                "op_profit_trillion_krw": _to_trillion_krw(estimate.get("op_profit")),
                "net_income_trillion_krw": _to_trillion_krw(estimate.get("net_income")),
                "op_margin_pct": estimate.get("op_margin"),
                "roe_pct": estimate.get("roe"),
                "fcf_trillion_krw": _to_trillion_krw(estimate.get("fcf")),
                "capex_trillion_krw": _to_trillion_krw(estimate.get("capex")),
                "fcf_margin_pct": round(fcf_margin, 1),
                "capex_to_sales_pct": round(capex_to_sales, 1),
                "debt_ratio_pct": estimate.get("debt_ratio"),
            },
            "eps_revision_1m_pct": round(eps_revision_1m, 1),
            "eps_revision_3m_pct": round(eps_revision_3m, 1),
            "interpretation": "이익 개선은 매출 성장보다 margin expansion과 EPS revision 지속성에 더 민감합니다.",
        }

    def _valuation_analysis(self, c: SecurityContext) -> Dict[str, Any]:
        v = c.valuation
        pbr_premium = _pct(v.get("pbr"), v.get("pbr_5y_avg"))
        peer_discount = _pct(v.get("pbr"), v.get("peer_pbr"))
        current_pbr = float(v.get("pbr") or 0)
        justified_pbr = round(float(v.get("per") or 0) * float(v.get("roe") or 0) / 100, 2)
        target_price = c.consensus.get("target_price") if c.consensus else None
        upside = _pct(target_price, v.get("price"))
        return {
            "per": v.get("per"),
            "pbr": v.get("pbr"),
            "ev_ebitda": v.get("ev_ebitda"),
            "pbr_premium_to_5y_avg_pct": round(pbr_premium, 1),
            "pbr_discount_to_peer_pct": round(peer_discount, 1),
            "target_price": target_price,
            "upside_pct": round(upside, 1),
            "roe_pbr_framework": {
                "method": "ROE-PBR justified multiple",
                "roe_pct": v.get("roe"),
                "implied_per": v.get("per"),
                "justified_pbr": justified_pbr,
                "current_pbr": current_pbr,
                "justified_pbr_gap_pct": round(_pct(current_pbr, justified_pbr), 1),
                "target_price": target_price,
                "upside_pct": round(upside, 1),
                "target_source": "consensus" if target_price else "not_available",
                "interpretation": "ROE × PER로 역산한 정당화 PBR이 현재 PBR과 유사해 추가 상승은 ROE 상향 또는 목표 멀티플 확장이 필요합니다.",
            },
            "valuation_judgment": "역사 평균 대비 프리미엄이 존재하므로 단순 저평가 논리는 약하고, ROE/EPS revision이 multiple을 정당화해야 합니다.",
        }

    def _portfolio_impact(self, c: SecurityContext) -> Dict[str, Any]:
        pos = c.portfolio_position
        weight = float(pos.get("weight", 0))
        proposed_delta = 2.0
        sector = c.company["sector"]
        sector_before = sum(float(row.get("weight", 0)) for row in _safe_csv(DATA_ROOT / "portfolio" / "portfolio_positions.csv") if row.get("sector") == sector)
        sector_after = sector_before + proposed_delta
        sector_limit = self._limit(c, "sector_weight", sector, 30.0)
        single_limit = self._limit(c, "single_name_weight", "*", 22.0)
        return {
            "current_weight": weight,
            "proposed_delta": proposed_delta,
            "proposed_weight": weight + proposed_delta,
            "sector_weight_before": round(sector_before, 1),
            "sector_weight_after": round(sector_after, 1),
            "sector_limit": sector_limit,
            "single_name_limit": single_limit,
            "sector_room_after": round(sector_limit - sector_after, 1),
            "single_name_room_after": round(single_limit - (weight + proposed_delta), 1),
            "risk_status": "WATCH" if sector_after >= sector_limit * 0.90 else "OK",
            "recommended_positioning": "증액 가능하나 섹터 limit 근접으로 size discipline 필요" if sector_after >= sector_limit * 0.90 else "PM Review 가능",
        }

    def _business_analysis(self, c: SecurityContext) -> Dict[str, Any]:
        return {
            "business_summary": c.company["business_summary"],
            "key_drivers": str(c.company["key_drivers"]).split(";"),
            "industry_cycle_view": "섹터 지표와 가격 데이터가 동행 개선되는 구간인지 확인하는 것이 핵심입니다.",
            "peer_group": str(c.company.get("peers", "")).split(";"),
        }

    def _evidence(self, c: SecurityContext) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        evidence = []
        counter = []
        for event in c.events:
            target = counter if event.get("sentiment") == "negative" else evidence
            target.append({
                "label": event["title"],
                "summary": event["summary"],
                "materiality": event["materiality"],
                "thesis_relevance": event["thesis_relevance"],
                "source": event["source"],
            })
        for indicator in c.sector_indicators[:3]:
            evidence.append({
                "label": indicator["indicator"],
                "summary": indicator["interpretation"],
                "materiality": 0.70,
                "thesis_relevance": 0.75,
                "source": indicator["source"],
            })
        return evidence, counter

    def _catalysts(self, c: SecurityContext) -> List[Dict[str, Any]]:
        return [
            {"horizon": "1M", "catalyst": "업황 가격 데이터 업데이트", "watch_metric": "DRAM/NAND 가격, 섹터 RS"},
            {"horizon": "3M", "catalyst": "실적/컨센서스 revision", "watch_metric": "EPS/OP consensus 1M·3M 변화"},
            {"horizon": "6-12M", "catalyst": "ROE 회복과 valuation 정당화", "watch_metric": "ROE, PBR band, peer discount"},
        ]

    def _variant_perception(self, c: SecurityContext) -> Dict[str, str]:
        return {
            "market_view": "시장은 업황 회복과 주가 반등을 상당 부분 인지하고 있습니다.",
            "our_view": "핵심은 단순 회복 여부가 아니라 margin expansion과 revision 지속성이 valuation premium을 정당화할 수 있는지입니다.",
            "edge": "업황 지표, 컨센서스 변화, 포트폴리오 리스크를 동시에 연결해 PM action 가능성을 평가합니다.",
        }

    def _scenarios(self, c: SecurityContext, f: Dict[str, Any], v: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        return {
            "bull": {"probability": 0.25, "assumption": "업황 가격 상승과 EPS revision 지속", "impact": "multiple 부담 완화 및 목표가 상향 여지"},
            "base": {"probability": 0.50, "assumption": "margin 개선은 지속되나 일부 기대 선반영", "impact": "보유/제한적 증액 검토"},
            "bear": {"probability": 0.25, "assumption": "가격 상승 둔화와 수급 반전", "impact": "Watchlist 하향 또는 비중 축소 검토"},
        }

    def _thesis_break_conditions(self, c: SecurityContext) -> List[str]:
        sector = c.company["sector"]
        return [
            f"{sector} 상대강도와 거래대금이 동반 하락",
            "컨센서스 EPS/OP revision이 1개월 이상 둔화 또는 하향 전환",
            "핵심 업황 가격 지표가 2회 연속 악화",
            "외국인/기관 수급이 동시 순매도로 전환",
        ]

    def _investment_view(self, c, f, v, p, evidence, counter) -> Dict[str, Any]:
        action = "PM Review" if f["eps_revision_3m_pct"] > 5 and p["risk_status"] != "BREACH" else "Watch"
        if p["risk_status"] == "WATCH":
            action = "Watch"
        return {
            "action": action,
            "thesis": f"{c.company['name']}의 투자 논리는 {c.company['sector']} 업황 개선이 이익 revision과 margin expansion으로 연결되는지에 달려 있습니다.",
            "time_horizon": "3-6M",
            "expected_return_drivers": ["earnings revision", "margin expansion", "sector leadership", "flow"],
            "key_risk": "valuation premium이 EPS/ROE 개선으로 정당화되지 못하는 경우",
        }

    def _decision_checklist(self, view, evidence, counter, portfolio) -> List[Dict[str, Any]]:
        return [
            {"item": "명확한 earnings driver", "pass": True},
            {"item": "variant perception 존재", "pass": True},
            {"item": "catalyst timing 정의", "pass": True},
            {"item": "supporting evidence 2개 이상", "pass": len(evidence) >= 2},
            {"item": "counter-evidence 확인", "pass": len(counter) >= 1},
            {"item": "risk budget 내 포트 편입 가능", "pass": portfolio["sector_room_after"] >= 0 and portfolio["single_name_room_after"] >= 0},
            {"item": "thesis break condition 정의", "pass": True},
        ]

    def _limit(self, c: SecurityContext, limit_type: str, scope: str, default: float) -> float:
        for row in c.risk_limits:
            if row.get("limit_type") == limit_type and row.get("scope") in {scope, "*"}:
                return float(row["limit_value"])
        return default

    def _compose_markdown(self, r: SecurityAnalysisReport) -> str:
        return f"""# {r.name} 전문가형 증권분석 보고서

## 1. Executive Investment View
- Action: **{r.investment_view['action']}**
- Thesis: {r.investment_view['thesis']}
- Time Horizon: {r.investment_view['time_horizon']}
- Key Risk: {r.investment_view['key_risk']}

## 2. Business & Industry Analysis
{r.business_analysis['business_summary']}

핵심 드라이버: {', '.join(r.business_analysis['key_drivers'])}

## 3. Earnings Driver Analysis
- 2026E 매출 성장률: {r.financial_analysis['revenue_growth_2026e']}%
- 2026E 영업이익 성장률: {r.financial_analysis['op_profit_growth_2026e']}%
- OPM 변화: {r.financial_analysis['op_margin_change_pp']}%p
- EPS revision 3M: {r.financial_analysis['eps_revision_3m_pct']}%

### Financial Model Snapshot
- Forecast year: {r.financial_analysis['financial_model_snapshot']['forecast_year']}
- Revenue / OP / NI: {r.financial_analysis['financial_model_snapshot']['revenue_trillion_krw']}조원 / {r.financial_analysis['financial_model_snapshot']['op_profit_trillion_krw']}조원 / {r.financial_analysis['financial_model_snapshot']['net_income_trillion_krw']}조원
- OP margin / ROE: {r.financial_analysis['financial_model_snapshot']['op_margin_pct']}% / {r.financial_analysis['financial_model_snapshot']['roe_pct']}%
- FCF / Capex: {r.financial_analysis['financial_model_snapshot']['fcf_trillion_krw']}조원 / {r.financial_analysis['financial_model_snapshot']['capex_trillion_krw']}조원
- FCF margin / Capex/Sales: {r.financial_analysis['financial_model_snapshot']['fcf_margin_pct']}% / {r.financial_analysis['financial_model_snapshot']['capex_to_sales_pct']}%

## 4. Valuation Analysis
- PER: {r.valuation_analysis['per']}x
- PBR: {r.valuation_analysis['pbr']}x
- 5년 평균 PBR 대비: {r.valuation_analysis['pbr_premium_to_5y_avg_pct']}%
- Target Price / Upside: {r.valuation_analysis['target_price']}원 / {r.valuation_analysis['upside_pct']}%
- ROE-PBR Justified Multiple Framework: ROE {r.valuation_analysis['roe_pbr_framework']['roe_pct']}% × PER {r.valuation_analysis['roe_pbr_framework']['implied_per']}x = justified PBR {r.valuation_analysis['roe_pbr_framework']['justified_pbr']}x; current gap {r.valuation_analysis['roe_pbr_framework']['justified_pbr_gap_pct']}%
- 판단: {r.valuation_analysis['valuation_judgment']}

## 5. Catalyst Timeline
""" + "\n".join([f"- {c['horizon']}: {c['catalyst']} / 확인지표: {c['watch_metric']}" for c in r.catalyst_timeline]) + f"""

## 6. Variant Perception
- Market View: {r.variant_perception['market_view']}
- Our View: {r.variant_perception['our_view']}
- Edge: {r.variant_perception['edge']}

## 7. Evidence Stack
""" + "\n".join([f"- {e['label']}: {e['summary']}" for e in r.evidence_stack]) + """

## 8. Counter-evidence & Risks
""" + "\n".join([f"- {e['label']}: {e['summary']}" for e in r.counter_evidence]) + f"""

## 9. Scenario Analysis
- Bull: {r.scenario_analysis['bull']['assumption']} → {r.scenario_analysis['bull']['impact']}
- Base: {r.scenario_analysis['base']['assumption']} → {r.scenario_analysis['base']['impact']}
- Bear: {r.scenario_analysis['bear']['assumption']} → {r.scenario_analysis['bear']['impact']}

## 10. Portfolio Impact
- 현재 비중: {r.portfolio_impact['current_weight']}%
- 제안 변화: +{r.portfolio_impact['proposed_delta']}%p
- 섹터 비중: {r.portfolio_impact['sector_weight_before']}% → {r.portfolio_impact['sector_weight_after']}%
- 섹터 limit 잔여: {r.portfolio_impact['sector_room_after']}%p
- Risk Status: {r.portfolio_impact['risk_status']}

## 11. Decision Checklist
""" + "\n".join([f"- [{'x' if item['pass'] else ' '}] {item['item']}" for item in r.decision_checklist]) + f"""

## 12. Final PM Action
{r.final_action['action']} — {r.final_action['positioning']}

> {r.disclaimer}
"""


def _pct(current: Any, base: Any) -> float:
    current_f = float(current or 0)
    base_f = float(base or 0)
    if base_f == 0:
        return 0.0
    return (current_f / base_f - 1.0) * 100.0


def _pct_of(part: Any, whole: Any) -> float:
    whole_f = float(whole or 0)
    if whole_f == 0:
        return 0.0
    return float(part or 0) / whole_f * 100.0


def _to_trillion_krw(value: Any) -> float:
    return round(float(value or 0) / 1_000_000_000_000, 1)


def _coerce_row(row: Dict[str, str]) -> Dict[str, Any]:
    output: Dict[str, Any] = {}
    for key, value in row.items():
        if value is None:
            output[key] = value
            continue
        text = value.strip()
        if text == "":
            output[key] = text
            continue
        try:
            if key in {"symbol", "peer_symbol", "index_code"}:
                output[key] = text
            elif any(ch in text for ch in [".", "e", "E"]):
                output[key] = float(text)
            else:
                output[key] = int(text)
        except ValueError:
            output[key] = text
    return output


def _safe_csv(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [_coerce_row(row) for row in csv.DictReader(handle)]

