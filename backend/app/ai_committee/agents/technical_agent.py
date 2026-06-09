from .base import CommitteeContext, source, CommitteeAgent


class TechnicalAgent(CommitteeAgent):
    name = "Technical"

    def analyze(self, c: CommitteeContext) -> dict:
        t = c.security_report.get("sources_context", {}).get("technical", {}) or c.security_report.get("technical_snapshot", {})
        if not t:
            t = c.security_report.get("raw_context", {}).get("technical", {})
        rsi = float(t.get("rsi_14", 63) or 63)
        rs = float(t.get("relative_strength_3m", c.sector.get("relative_strength", 50)) or 50)
        score = max(30, min(95, int((rs * 0.7) + (70 - abs(rsi - 55)) * 0.3)))
        stance = "Overheated" if rsi >= 68 or rs >= 88 else "Positive" if score >= 70 else "Neutral"
        return self.opinion(
            stance=stance,
            score=score,
            confidence=0.74,
            summary="추세와 상대강도는 우호적이나 RSI/이격이 높을 경우 신규 확대 타이밍은 분할 접근이 필요합니다.",
            reasoning_steps=["RSI로 단기 과열 확인", "20/60일선 이격으로 추세 강도 확인", "52주 고점 근접도 점검", "유동성 점수로 exit 가능성 확인"],
            evidence=[f"RSI {rsi:.0f}", f"3M RS {rs:.0f}", f"20D gap {t.get('sma_20_gap_pct', 'N/A')}%"],
            risks=["단기 과열 후 mean reversion", "거래대금 급증 뒤 변동성 확대"],
            analysis={"technical_indicators": {"rsi": rsi, "ma_20": t.get("sma_20_gap_pct"), "ma_60": t.get("sma_60_gap_pct"), "relative_strength": rs, "high_52w_distance_pct": t.get("high_52w_distance_pct"), "liquidity_score": t.get("liquidity_score")}},
            citations=[source("technical_snapshot", "security_analysis", confidence=0.7)],
            follow_up=["RSI 70 상회 또는 20D 이격 확대 시 chase 금지"],
        )
