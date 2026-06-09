from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Dict, List, Literal

Decision = Literal[
    "PROMOTE_TO_PM_REVIEW",
    "WATCHLIST_WITH_SIZE_CONSTRAINT",
    "REQUEST_MORE_EVIDENCE",
    "REJECT_OR_AVOID",
    "KEEP_INVESTIGATING",
]
RiskStatus = Literal["OK", "WATCH", "BREACH"]


@dataclass
class Evidence:
    label: str
    source_type: str
    source_quality: float
    freshness_days: int
    materiality: float
    confirmatory_strength: float


@dataclass
class CounterEvidence:
    label: str
    severity: int
    probability: int
    time_proximity: int
    thesis_relevance: int


@dataclass
class PortfolioContext:
    current_weight: float
    proposed_delta: float
    sector_weight: float
    sector_limit: float
    single_name_limit: float
    top5_concentration: float
    liquidity_score: float
    correlation_cluster_penalty: float


@dataclass
class RiskException:
    risk_type: str
    current: float
    limit: float
    status: RiskStatus
    severity: str
    suggested_action: str


@dataclass
class IdeaInput:
    symbol: str
    name: str
    sector: str
    thesis: str
    signals: Dict[str, float]
    evidence: List[Evidence]
    counter_evidence: List[CounterEvidence]
    portfolio: PortfolioContext


@dataclass
class IdeaEvaluation:
    idea_id: str
    symbol: str
    name: str
    sector: str
    idea_score: int
    thesis_quality: int
    evidence_score: int
    counter_penalty: int
    portfolio_fit: int
    risk_status: RiskStatus
    decision: Decision
    risk_exceptions: List[RiskException] = field(default_factory=list)
    reason: List[str] = field(default_factory=list)
    required_checks: List[str] = field(default_factory=list)
    score_breakdown: Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def evaluate_idea(idea: IdeaInput) -> IdeaEvaluation:
    evidence_score = EvidenceScorer().score(idea.evidence)
    counter_penalty = RiskPenaltyEngine().score(idea.counter_evidence)
    thesis_quality = ThesisEvaluator().score(idea.thesis, evidence_score, idea.counter_evidence)
    portfolio_result = PortfolioFitEngine().score(idea.portfolio)
    idea_score, breakdown = IdeaEvaluator().score(idea.signals, counter_penalty)
    decision, reasons, checks = DecisionEngine().decide(
        idea=idea,
        idea_score=idea_score,
        thesis_quality=thesis_quality,
        evidence_score=evidence_score,
        counter_penalty=counter_penalty,
        portfolio_fit=portfolio_result["portfolio_fit"],
        risk_status=portfolio_result["risk_status"],
    )
    return IdeaEvaluation(
        idea_id=f"{idea.symbol}_decision_package",
        symbol=idea.symbol,
        name=idea.name,
        sector=idea.sector,
        idea_score=idea_score,
        thesis_quality=thesis_quality,
        evidence_score=evidence_score,
        counter_penalty=counter_penalty,
        portfolio_fit=portfolio_result["portfolio_fit"],
        risk_status=portfolio_result["risk_status"],
        decision=decision,
        risk_exceptions=portfolio_result["risk_exceptions"],
        reason=reasons,
        required_checks=checks,
        score_breakdown=breakdown,
    )


class IdeaEvaluator:
    weights = {
        "fundamental_revision": 0.25,
        "price_momentum": 0.20,
        "sector_leadership": 0.20,
        "flow_positioning": 0.15,
        "catalyst_quality": 0.10,
    }

    def score(self, signals: Dict[str, float], counter_penalty: int) -> tuple[int, Dict[str, int]]:
        raw = 0.0
        breakdown: Dict[str, int] = {}
        for key, weight in self.weights.items():
            contribution = float(signals.get(key, 50)) * weight
            breakdown[key] = round(contribution)
            raw += contribution
        risk_adjustment = min(10, int(counter_penalty / 50))
        breakdown["risk_adjustment"] = -risk_adjustment
        return _clamp_int(raw - risk_adjustment), breakdown


class ThesisEvaluator:
    def score(self, thesis: str, evidence_score: int, counter_evidence: List[CounterEvidence]) -> int:
        text = thesis.lower()
        length_score = 15 if len(thesis) >= 45 else 4
        earnings_driver = 20 if any(token in text for token in ["margin", "asp", "이익", "수요", "가격", "drAM".lower()]) else 6
        variant_perception = 16 if any(token in text for token in ["과소평가", "consensus", "시장", "variant", "선반영"]) else 8
        catalyst_timing = 13 if any(token in text for token in ["2h", "26", "분기", "컨콜", "실적", "today"]) else 7
        evidence_support = round(evidence_score * 0.20)
        risk_definition = 12 if counter_evidence else 4
        portfolio_fit_hint = 8 if any(token in text for token in ["수요", "margin", "가격", "업황"]) else 5
        return _clamp_int(length_score + earnings_driver + variant_perception + catalyst_timing + evidence_support + risk_definition + portfolio_fit_hint)


class EvidenceScorer:
    def score(self, evidence: List[Evidence]) -> int:
        if not evidence:
            return 0
        weighted_scores = []
        for item in evidence:
            freshness = _freshness_decay(item.freshness_days)
            source_multiplier = _source_type_multiplier(item.source_type)
            score = (
                item.source_quality
                * freshness
                * item.materiality
                * item.confirmatory_strength
                * source_multiplier
                * 100
            )
            weighted_scores.append(score)
        # 상위 evidence를 더 중시하되, 근거가 여러 개인 경우 breadth 보너스 부여
        weighted_scores.sort(reverse=True)
        top = weighted_scores[0]
        rest = sum(weighted_scores[1:]) / max(len(weighted_scores), 1)
        breadth_bonus = min(12, 4 * (len(evidence) - 1))
        return _clamp_int(top * 0.72 + rest * 0.28 + breadth_bonus)


class RiskPenaltyEngine:
    def score(self, counter_evidence: List[CounterEvidence]) -> int:
        total = 0
        for risk in counter_evidence:
            raw = risk.severity * risk.probability * risk.time_proximity * risk.thesis_relevance
            total += raw
        return _clamp_int(total / 6)


class PortfolioFitEngine:
    def score(self, portfolio: PortfolioContext) -> dict:
        proposed_weight = portfolio.current_weight + portfolio.proposed_delta
        proposed_sector = portfolio.sector_weight + portfolio.proposed_delta
        sector_room_after = portfolio.sector_limit - proposed_sector
        single_room_after = portfolio.single_name_limit - proposed_weight

        diversification = _clamp_int(100 - max(0, proposed_sector - 20) * 3.0)
        risk_budget_room = _clamp_int(50 + sector_room_after * 8 + single_room_after * 5)
        liquidity_fit = _clamp_int(portfolio.liquidity_score)
        concentration_penalty = max(0, portfolio.top5_concentration + portfolio.proposed_delta * 0.8 - 45) * 2.5
        overlap_penalty = portfolio.correlation_cluster_penalty

        portfolio_fit = _clamp_int(
            diversification * 0.25
            + risk_budget_room * 0.35
            + liquidity_fit * 0.25
            + 70 * 0.15
            - concentration_penalty
            - overlap_penalty
        )

        exceptions: List[RiskException] = []
        exceptions.append(_exception("sector_concentration", proposed_sector, portfolio.sector_limit, "섹터 비중 limit 근접 여부 확인"))
        exceptions.append(_exception("single_name_weight", proposed_weight, portfolio.single_name_limit, "단일 종목 비중 한도 확인"))
        exceptions.append(_exception("top5_concentration", portfolio.top5_concentration + portfolio.proposed_delta * 0.8, 48.0, "상위 보유종목 집중도 확인"))

        if any(item.status == "BREACH" for item in exceptions):
            risk_status: RiskStatus = "BREACH"
        elif any(item.status == "WATCH" for item in exceptions):
            risk_status = "WATCH"
        else:
            risk_status = "OK"

        return {"portfolio_fit": portfolio_fit, "risk_status": risk_status, "risk_exceptions": exceptions}


class DecisionEngine:
    def decide(
        self,
        idea: IdeaInput,
        idea_score: int,
        thesis_quality: int,
        evidence_score: int,
        counter_penalty: int,
        portfolio_fit: int,
        risk_status: RiskStatus,
    ) -> tuple[Decision, List[str], List[str]]:
        reasons: List[str] = []
        checks = [
            "장 초반 외국인 선물 수급 확인",
            "핵심 업황/가격 데이터 업데이트 확인",
            f"{idea.sector} 섹터 거래대금 지속 여부 확인",
        ]

        if risk_status == "BREACH" or counter_penalty >= 45:
            reasons.append("Risk budget or limit breach blocks promotion to PM review.")
            reasons.append("Counter-evidence penalty is too high relative to thesis support.")
            return "REJECT_OR_AVOID", reasons, checks

        if thesis_quality < 70:
            reasons.append("Thesis quality is below institutional review threshold; request more evidence before PM review.")
            return "REQUEST_MORE_EVIDENCE", reasons, checks + ["variant perception과 thesis break condition 보강"]

        if evidence_score < 45:
            reasons.append("Evidence stack is too weak or stale for institutional decision support.")
            return "REQUEST_MORE_EVIDENCE", reasons, checks + ["최신 공시/컨센서스/가격 데이터 보강"]

        if idea_score >= 75 and portfolio_fit >= 70 and risk_status == "OK":
            reasons.append("Idea score, thesis quality, evidence, and portfolio fit clear PM review gates.")
            return "PROMOTE_TO_PM_REVIEW", reasons, checks

        if idea_score >= 75 and (portfolio_fit < 70 or risk_status == "WATCH"):
            reasons.append("Idea score is high, but portfolio fit is constrained by sector concentration or risk budget.")
            reasons.append("섹터/종목 익스포저가 limit에 근접하므로 size constraint가 필요합니다.")
            return "WATCHLIST_WITH_SIZE_CONSTRAINT", reasons, checks

        reasons.append("Signals are not strong enough for PM review; keep investigating until evidence improves.")
        return "KEEP_INVESTIGATING", reasons, checks


def _exception(risk_type: str, current: float, limit: float, suggested_action: str) -> RiskException:
    ratio = current / limit if limit else 0
    if current > limit:
        status: RiskStatus = "BREACH"
        severity = "high"
    elif ratio >= 0.90:
        status = "WATCH"
        severity = "medium"
    else:
        status = "OK"
        severity = "low"
    return RiskException(risk_type, round(current, 2), limit, status, severity, suggested_action)


def _freshness_decay(days: int) -> float:
    if days <= 1:
        return 1.0
    if days <= 3:
        return 0.85
    if days <= 7:
        return 0.65
    if days <= 14:
        return 0.45
    return 0.25


def _source_type_multiplier(source_type: str) -> float:
    multipliers = {
        "company_guidance": 1.18,
        "dart_filing": 1.15,
        "market_data": 1.10,
        "broker_research": 1.03,
        "flow_data": 0.95,
        "news": 0.80,
        "social": 0.55,
    }
    return multipliers.get(source_type, 0.85)


def _clamp_int(value: float) -> int:
    return max(0, min(100, round(value)))



