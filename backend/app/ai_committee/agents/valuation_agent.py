from .base import CommitteeContext, source, CommitteeAgent


class ValuationAgent(CommitteeAgent):
    name = "Valuation"

    def analyze(self, c: CommitteeContext) -> dict:
        v = c.security_report.get("valuation_analysis", {})
        upside = float(v.get("upside_pct", 0) or 0)
        premium = float(v.get("pbr_premium_to_5y_avg_pct", 0) or 0)
        score = max(35, min(90, int(65 + upside * 0.4 - max(premium, 0) * 0.25)))
        stance = "Positive" if score >= 72 else "Neutral" if score >= 55 else "Negative"
        return self.opinion(
            stance=stance,
            score=score,
            confidence=0.78,
            summary="업사이드는 남아 있으나 역사 밴드 대비 premium을 이익 개선으로 정당화해야 합니다.",
            reasoning_steps=[
                "PER/PBR/EV-EBITDA 현재 수준 확인",
                "PBR 5년 평균 대비 premium 또는 discount 계산",
                "peer PBR 대비 상대 valuation 확인",
                "target price upside와 ROE-PBR framework로 정당화 가능성 평가",
            ],
            evidence=[f"PER {v.get('per')}x", f"PBR {v.get('pbr')}x", f"Upside {v.get('upside_pct')}%"],
            risks=["기대 선반영", "ROE 개선 미달", "peer multiple 하락"],
            analysis={"valuation_model": {"per": v.get("per"), "pbr": v.get("pbr"), "ev_ebitda": v.get("ev_ebitda"), "upside_pct": v.get("upside_pct"), "pbr_premium_to_5y_avg_pct": v.get("pbr_premium_to_5y_avg_pct"), "roe_pbr_framework": v.get("roe_pbr_framework")}, "margin_of_safety": "limited" if premium > 5 else "acceptable"},
            citations=[source("valuation_snapshot", "security_analysis", confidence=0.6), source("consensus target", "security_analysis")],
            follow_up=["목표가 상향이 이익 추정 상향인지 multiple 확장인지 분해"],
        )
