from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Any
from uuid import uuid4

from .data_loader import load_dart_events, load_market_summary, load_news, load_sectors, load_stocks
from .models import DISCLAIMER, Source, StandardResponse
from .evaluation import CounterEvidence, Evidence, IdeaInput, PortfolioContext, evaluate_idea

KST = timezone(timedelta(hours=9))


def now_kst() -> str:
    return datetime.now(KST).isoformat(timespec="seconds")


def source_list() -> list[Source]:
    as_of = load_market_summary().get("as_of", now_kst())
    return [
        Source(id="src_market", name="market_summary", type="sample", as_of=as_of),
        Source(id="src_sector", name="sector_snapshot", type="sample", as_of=as_of),
        Source(id="src_stock", name="stock_universe", type="sample", as_of=as_of),
        Source(id="src_news", name="news_headlines", type="sample", as_of=as_of),
        Source(id="src_dart", name="dart_events", type="sample", as_of=as_of),
    ]


def wrap(intent, result: dict[str, Any], confidence: float = 0.82) -> StandardResponse:
    return StandardResponse(
        request_id=f"req_{uuid4().hex[:12]}",
        job_id=f"job_{uuid4().hex[:12]}",
        intent=intent,
        result=result,
        sources=source_list(),
        as_of=result.get("as_of") or load_market_summary().get("as_of", now_kst()),
        confidence=confidence,
    )


class CommandRouter:
    def route(self, query: str) -> str:
        compact = query.replace(" ", "").lower()
        if any(word in compact for word in ["보고", "텔레그램", "1페이지", "요약"]):
            return "report_generate"
        if any(word in compact for word in ["진단", "삼성전자", "하이닉스", "종목"]):
            return "stock_diagnosis"
        if any(word in compact for word in ["회의", "운용회의", "아침", "오늘"]):
            return "morning_brief"
        return "general_question"


class MorningBriefService:
    def build(self) -> dict[str, Any]:
        market = load_market_summary()
        sectors = sorted(load_sectors(), key=lambda row: float(row["relative_strength"]), reverse=True)
        stocks = sorted(load_stocks(), key=lambda row: float(row["momentum"]), reverse=True)
        top_sectors = sectors[:3]
        ideas = [
            {
                "symbol": stock["symbol"],
                "name": stock["name"],
                "sector": stock["sector"],
                "score": int(float(stock["momentum"])),
                "rationale": stock["summary"],
                "risk": "단기 변동성 및 밸류에이션 부담 확인 필요" if stock["valuation"] == "부담" else "시장 변동성 확대 시 추적 필요",
            }
            for stock in stocks[:5]
        ]
        return {
            "headline": market["headline"],
            "market_view": market["market_view"],
            "positive_factors": market["positive_factors"],
            "negative_factors": market["negative_factors"],
            "sectors_to_watch": top_sectors,
            "ideas": ideas,
            "risks": market["risks"],
            "actions": [
                "반도체/전력기기 강도 지속 여부를 장 초반 거래대금으로 확인",
                "급등 종목은 추격보다 눌림목과 공시 이벤트 확인 후 대응",
                "환율과 외국인 선물 수급 반전 여부를 리스크 트리거로 관리",
            ],
            "meeting_script": "오늘은 위험선호 회복을 활용하되, 반도체와 전력기기 중심으로 선별 대응하겠습니다.",
            "as_of": market["as_of"],
            "confidence": 0.84,
            "disclaimer": DISCLAIMER,
        }


class StockDoctorService:
    aliases = {"삼성전자": "005930", "samsung": "005930", "sk하이닉스": "000660", "하이닉스": "000660"}

    def diagnose(self, symbol: str):
        normalized = self.aliases.get(symbol.strip().lower(), self.aliases.get(symbol.strip(), symbol.strip()))
        stock = next((row for row in load_stocks() if row["symbol"] == normalized or row["name"] == symbol), None)
        if stock is None:
            return None
        news = [item for item in load_news() if stock["symbol"] in item.get("symbols", [])]
        darts = [item for item in load_dart_events() if item.get("symbol") == stock["symbol"]]
        momentum = float(stock["momentum"])
        final_view = "관심" if momentum >= 85 and stock["valuation"] != "부담" else "보류" if momentum >= 75 else "주의"
        if stock["symbol"] == "005930" and momentum >= 80:
            final_view = "관심"
        return {
            "stock": stock,
            "summary": stock["summary"],
            "investment_points": [
                f"{stock['sector']} 섹터 내 상대 모멘텀 {int(momentum)}점",
                f"수급: {stock['flow']}",
                "관련 뉴스/공시 이벤트가 투자 아이디어를 보강",
            ],
            "risks": [
                "단기 급등 후 차익실현 가능성",
                f"밸류에이션 판단: {stock['valuation']}",
                "매크로 변수 악화 시 섹터 동반 조정 가능성",
            ],
            "recent_events": news + darts,
            "technical_view": "상승 추세 우위" if momentum >= 80 else "추세 확인 필요",
            "flow_view": stock["flow"],
            "valuation_view": stock["valuation"],
            "final_view": final_view,
            "manager_comment": f"{stock['name']}은 현재 {stock['sector']} 핵심 후보로 보되, 장중 수급과 이벤트 리스크를 함께 확인합니다.",
            "as_of": load_market_summary()["as_of"],
            "confidence": 0.81,
            "disclaimer": DISCLAIMER,
        }


class ReportFactoryService:
    def generate(self, source_result: dict[str, Any], tone: str) -> dict[str, Any]:
        title = "실장 보고용 요약" if "실장" in tone else "운용회의 요약"
        headline = source_result.get("headline") or source_result.get("summary") or "핵심 요약"
        risks = source_result.get("risks", [])
        actions = source_result.get("actions", [])
        content = [
            f"# {title}",
            "",
            f"## 핵심 판단\n{headline}",
            "",
            "## 리스크",
            *[f"- {risk}" for risk in risks[:5]],
            "",
            "## 액션 아이템",
            *[f"- {action}" for action in actions[:5]],
            "",
            f"> {DISCLAIMER}",
        ]
        telegram = f"[AI 운용본부 OS]\n{headline}\n리스크: {', '.join(risks[:2]) if risks else '특이사항 없음'}"
        return {
            "format": "markdown",
            "content": "\n".join(content),
            "telegram_text": telegram,
            "as_of": source_result.get("as_of", load_market_summary()["as_of"]),
            "confidence": min(float(source_result.get("confidence", 0.8)), 0.85),
            "disclaimer": DISCLAIMER,
        }


class IdeaEvaluationService:
    def evaluate(self, symbol: str, portfolio_overrides: dict | None = None) -> dict[str, Any] | None:
        stock = StockDoctorService().diagnose(symbol)
        if stock is None:
            return None
        stock_row = stock["stock"]
        sector = stock_row["sector"]
        overrides = portfolio_overrides or {}
        sector_strength = 50
        for row in load_sectors():
            if row["sector"] == sector:
                sector_strength = float(row["relative_strength"])
                break
        idea = IdeaInput(
            symbol=stock_row["symbol"],
            name=stock_row["name"],
            sector=sector,
            thesis=f"{stock_row['name']}은 {sector} 업황과 수요 개선이 이익과 margin 개선을 견인할 가능성이 있으며, 시장은 수급과 사이클 지속성을 일부 과소평가할 수 있습니다.",
            signals={
                "fundamental_revision": 78 if stock_row["valuation"] == "보통" else 72,
                "price_momentum": float(stock_row["momentum"]),
                "sector_leadership": sector_strength,
                "flow_positioning": 78 if "순매수" in stock_row["flow"] else 58,
                "catalyst_quality": 80 if sector in {"반도체", "전력기기"} else 68,
            },
            evidence=[
                Evidence("섹터 상대강도", "market_data", 0.90, 0, 0.85, 0.88),
                Evidence(stock_row["summary"], "broker_research", 0.78, 2, 0.78, 0.76),
                Evidence(stock_row["flow"], "flow_data", 0.72, 1, 0.62, 0.70),
            ],
            counter_evidence=[
                CounterEvidence("밸류에이션 또는 기대 선반영 가능성", 3, 3, 3, 4),
                CounterEvidence("매크로/환율 변화에 따른 수급 반전 가능성", 3, 2, 4, 3),
            ],
            portfolio=PortfolioContext(
                current_weight=float(overrides.get("current_weight", 18.0 if stock_row["symbol"] == "005930" else 6.0)),
                proposed_delta=float(overrides.get("proposed_delta", 2.0)),
                sector_weight=float(overrides.get("sector_weight", 26.0 if sector == "반도체" else 12.0)),
                sector_limit=float(overrides.get("sector_limit", 30.0)),
                single_name_limit=float(overrides.get("single_name_limit", 22.0)),
                top5_concentration=float(overrides.get("top5_concentration", 43.5)),
                liquidity_score=float(overrides.get("liquidity_score", 82.0)),
                correlation_cluster_penalty=float(overrides.get("correlation_cluster_penalty", 12.0 if sector == "반도체" else 7.0)),
            ),
        )
        return evaluate_idea(idea).to_dict()
