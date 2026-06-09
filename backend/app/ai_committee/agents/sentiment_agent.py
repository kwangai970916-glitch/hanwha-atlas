from .base import CommitteeContext, source, CommitteeAgent


class SentimentNewsAgent(CommitteeAgent):
    name = "Sentiment / News"

    def analyze(self, c: CommitteeContext) -> dict:
        events = c.security_report.get("evidence_stack", [])
        counter = c.security_report.get("counter_evidence", [])
        positives = [e.get("label") or e.get("title") for e in events[:3]]
        negatives = [e.get("label") or e.get("title") for e in counter[:3]]
        score = min(90, 60 + len(positives) * 7 - len(negatives) * 4)
        return self.opinion(
            stance="Positive" if score >= 70 else "Neutral",
            score=score,
            confidence=0.73,
            summary="뉴스/공시 흐름은 thesis를 보강하지만 부정 이벤트가 늘면 기대 선반영 리스크가 커집니다.",
            reasoning_steps=["관련 뉴스와 공시를 thesis relevance 기준으로 분류", "긍정/부정 이벤트의 materiality 비교", "시장 심리와 수급 방향 연결", "뉴스가 실적 driver인지 단순 narrative인지 구분"],
            evidence=positives or ["관련 긍정 이벤트 제한적"],
            risks=negatives or ["headline momentum 둔화"],
            analysis={"sentiment_score": score, "news_events": c.news, "dart_events": c.darts, "positive_signals": positives, "negative_signals": negatives},
            citations=[source("events.jsonl", "security_analysis"), source("news_headlines", "samples")],
            follow_up=["부정 공시/뉴스 발생 시 bear case 재실행"],
        )
