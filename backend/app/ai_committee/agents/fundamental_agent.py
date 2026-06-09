from .base import CommitteeContext, source, CommitteeAgent


class FundamentalAgent(CommitteeAgent):
    name = "Fundamental"

    def analyze(self, c: CommitteeContext) -> dict:
        f = c.security_report.get("financial_analysis", {})
        model = f.get("financial_model_snapshot", {})
        eps3m = float(f.get("eps_revision_3m_pct", 0) or 0)
        op_growth = float(f.get("op_profit_growth_2026e", 0) or 0)
        score = max(40, min(95, int(62 + eps3m * 1.2 + op_growth * 0.15)))
        stance = "Positive" if score >= 72 else "Neutral"
        return self.opinion(
            stance=stance,
            score=score,
            confidence=0.82,
            summary=f"{c.stock['name']}의 핵심은 {c.stock['sector']} 업황이 EPS revision과 margin expansion으로 연결되는지입니다.",
            reasoning_steps=[
                "매출 성장보다 영업이익 성장과 margin 변화가 thesis의 중심인지 확인",
                "1개월/3개월 EPS revision으로 실적 가시성 변화 측정",
                "ROE와 FCF가 valuation premium을 정당화하는지 점검",
                "이벤트/뉴스가 실적 드라이버를 실제로 보강하는지 연결",
            ],
            evidence=[
                f"2026E OP 성장률 {f.get('op_profit_growth_2026e')}%",
                f"EPS revision 3M {f.get('eps_revision_3m_pct')}%",
                f"ROE 2026E {f.get('roe_2026e')}%",
            ],
            risks=["EPS revision 둔화", "업황 가격 지표 반락", "FCF 개선 지연"],
            analysis={
                "financial_model": {
                    "revenue_growth_2026e": f.get("revenue_growth_2026e"),
                    "op_profit_growth_2026e": f.get("op_profit_growth_2026e"),
                    "op_margin_change_pp": f.get("op_margin_change_pp"),
                    "eps_revision_1m_pct": f.get("eps_revision_1m_pct"),
                    "eps_revision_3m_pct": f.get("eps_revision_3m_pct"),
                    "roe_2026e": f.get("roe_2026e"),
                    "snapshot": model,
                },
                "thesis_quality": "earnings_revision_supported" if eps3m > 5 else "needs_more_revision",
            },
            citations=[source("financials/consensus", "security_analysis", confidence=0.7), source(c.stock["summary"], "stock_universe")],
            follow_up=["다음 컨센서스 업데이트에서 EPS/OP revision 유지 여부 확인"],
        )
