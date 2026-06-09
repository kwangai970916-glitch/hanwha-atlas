from .base import CommitteeContext, source, CommitteeAgent


class MacroAgent(CommitteeAgent):
    name = "Macro"

    def analyze(self, c: CommitteeContext) -> dict:
        indicators = c.security_report.get("business_analysis", {}).get("key_drivers", [])
        rs = float(c.sector.get("relative_strength", 50) or 50)
        supportive = rs >= 80
        return self.opinion(
            stance="Supportive" if supportive else "Neutral",
            score=78 if supportive else 60,
            confidence=0.70,
            summary=f"{c.stock['sector']} 섹터 상대강도와 글로벌 capex/금리/환율 레짐이 투자 타이밍의 배경 변수입니다.",
            reasoning_steps=["시장 레짐과 업종 상대강도를 먼저 확인", "금리/환율이 외국인 수급에 미치는 영향 점검", "섹터 로테이션 지속성 평가", "macro shock 발생 시 포트폴리오 beta 확대 여부 확인"],
            evidence=[f"섹터 RS {rs:.0f}"] + [str(x) for x in indicators[:2]],
            risks=["달러 강세", "장기금리 상승", "AI CAPEX 둔화"],
            analysis={"macro_regime": "risk-on selective growth" if supportive else "mixed", "sector_relative_strength": rs, "fx_sensitivity": "medium-high", "rate_sensitivity": "medium", "cycle_view": c.sector.get("comment", "중립")},
            citations=[source("sector_snapshot", "samples"), source("sector_indicators", "security_analysis")],
            follow_up=["미국 금리/환율 급변 시 외국인 수급과 동시 점검"],
        )
