from .base import CommitteeContext, source, CommitteeAgent


class BearCaseAgent(CommitteeAgent):
    name = "Bear Case"

    def analyze(self, c: CommitteeContext) -> dict:
        breaks = c.security_report.get("thesis_break_conditions", []) or ["실적 추정 하향", "수급 반전", "섹터 RS 악화"]
        counter = c.security_report.get("counter_evidence", [])
        valuation = c.security_report.get("valuation_analysis", {})
        expected_loss = -12 if c.stock.get("valuation") == "부담" else -8
        return self.opinion(
            stance="Expectation Priced-In Risk" if c.stock.get("valuation") == "부담" else "Watch",
            score=44 if c.stock.get("valuation") == "부담" else 58,
            confidence=0.80,
            summary="투자 thesis가 틀릴 가능성을 강제로 점검하면 기대 선반영, 고객사 capex 둔화, 수급 반전이 핵심 위험입니다.",
            reasoning_steps=["bull narrative가 이미 가격에 반영되었는지 확인", "thesis break condition을 사전에 정의", "downside leading indicator를 가격/실적/뉴스로 분리", "PM action이 늦어지는 경우 손실폭 추정"],
            evidence=[x.get("label", "counter evidence") for x in counter] or ["반대 논리 seed"],
            risks=["기대 선반영", "고객사 투자 둔화", "경쟁사 공급 확대", "외국인 수급 반전"],
            analysis={"thesis_break_conditions": breaks, "downside_drivers": ["multiple de-rating", "EPS revision reversal", "sector rotation"], "leading_warning_indicators": ["RS 2주 연속 하락", "EPS revision 하향", "부정 뉴스 증가"], "expected_loss_pct": expected_loss, "valuation_pressure": valuation.get("pbr_premium_to_5y_avg_pct")},
            citations=[source("counter_evidence", "security_analysis"), source("valuation_snapshot", "security_analysis")],
            follow_up=["bear case 발생 시 축소 트리거와 보고 라인 확정"],
        )
