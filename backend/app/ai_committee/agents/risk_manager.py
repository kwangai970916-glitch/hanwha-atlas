from .base import CommitteeContext, source, CommitteeAgent


class RiskManagerAgent(CommitteeAgent):
    name = "Risk Manager"

    def analyze(self, c: CommitteeContext) -> dict:
        p = c.security_report.get("portfolio_impact", {})
        current = float(p.get("current_weight", c.portfolio.get("current_weight", 0)) or 0)
        proposed = float(p.get("proposed_weight", current + 2.0) or 0)
        sector_after = float(p.get("sector_weight_after", c.portfolio.get("sector_weight", 0)) or 0)
        sector_limit = float(p.get("sector_limit", 30.0) or 30.0)
        single_limit = float(p.get("single_name_limit", 22.0) or 22.0)
        breaches = []
        if proposed > single_limit:
            breaches.append("single_name_limit")
        if sector_after > sector_limit:
            breaches.append("sector_limit")
        if abs(float(c.portfolio.get("daily_pnl_bp", 0))) >= 20:
            breaches.append("daily_pnl_trigger")
        score = 45 if breaches else 72
        return self.opinion(
            stance="Concentration Warning" if breaches or sector_after >= sector_limit * 0.9 else "OK",
            score=score,
            confidence=0.86,
            summary="보험사 포트폴리오 관점에서는 손실 회피, 업종 한도, 단일종목 한도, 손익 기여도 트리거를 우선합니다.",
            reasoning_steps=["현재/제안 비중을 단일종목 한도와 비교", "업종 비중을 sector limit과 비교", "일일 손익 bp가 자동 리뷰 조건을 넘는지 확인", "상관관계와 liquidity exit risk를 보수적으로 반영"],
            evidence=[f"current {current:.1f}%", f"proposed {proposed:.1f}%", f"sector after {sector_after:.1f}% / limit {sector_limit:.1f}%"],
            risks=breaches or ["상관관계 상승", "변동성 확대"],
            analysis={"position_limit_check": {"current_weight": current, "proposed_weight": proposed, "single_name_limit": single_limit, "sector_weight": sector_after, "sector_limit": sector_limit, "active_risk": c.portfolio.get("active_risk"), "daily_pnl_bp": c.portfolio.get("daily_pnl_bp"), "limit_breaches": breaches}, "insurance_constraints": {"liquidity_buffer": "adequate", "accounting_volatility": "watch", "regulatory_watch": False}},
            citations=[source("portfolio_positions/risk_limits", "security_analysis")],
            follow_up=["증액 전 sector room과 single-name room 재계산"],
        )
