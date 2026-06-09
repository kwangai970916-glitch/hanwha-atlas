from app.evaluation import (
    CounterEvidence,
    Evidence,
    IdeaInput,
    PortfolioContext,
    evaluate_idea,
)


def samsung_input(portfolio_semis_weight=26.0):
    return IdeaInput(
        symbol="005930",
        name="삼성전자",
        sector="반도체",
        thesis="HBM/서버 DRAM 수요가 2H26 ASP와 margin 개선을 견인한다.",
        signals={
            "fundamental_revision": 82,
            "price_momentum": 84,
            "sector_leadership": 92,
            "flow_positioning": 78,
            "catalyst_quality": 80,
        },
        evidence=[
            Evidence(
                label="반도체 상대강도 1위권",
                source_type="market_data",
                source_quality=0.90,
                freshness_days=0,
                materiality=0.85,
                confirmatory_strength=0.90,
            ),
            Evidence(
                label="메모리 가격 개선 코멘트",
                source_type="broker_research",
                source_quality=0.80,
                freshness_days=2,
                materiality=0.82,
                confirmatory_strength=0.78,
            ),
            Evidence(
                label="외국인 순매수 지속",
                source_type="flow_data",
                source_quality=0.72,
                freshness_days=1,
                materiality=0.64,
                confirmatory_strength=0.70,
            ),
        ],
        counter_evidence=[
            CounterEvidence(
                label="밸류에이션 리레이팅 선반영 가능성",
                severity=3,
                probability=3,
                time_proximity=3,
                thesis_relevance=4,
            ),
            CounterEvidence(
                label="환율 급변 시 외국인 수급 반전 가능성",
                severity=3,
                probability=2,
                time_proximity=4,
                thesis_relevance=3,
            ),
        ],
        portfolio=PortfolioContext(
            current_weight=18.0,
            proposed_delta=2.0,
            sector_weight=portfolio_semis_weight,
            sector_limit=30.0,
            single_name_limit=22.0,
            top5_concentration=43.5,
            liquidity_score=82,
            correlation_cluster_penalty=12,
        ),
    )


def test_evaluate_idea_returns_explainable_scores_and_decision():
    result = evaluate_idea(samsung_input())

    assert result.idea_score >= 75
    assert result.thesis_quality >= 70
    assert result.evidence_score >= 70
    assert result.portfolio_fit < result.idea_score
    assert result.risk_status == "WATCH"
    assert result.decision == "WATCHLIST_WITH_SIZE_CONSTRAINT"
    assert any("sector concentration" in reason.lower() or "섹터" in reason for reason in result.reason)
    assert len(result.required_checks) >= 3


def test_low_thesis_quality_requests_more_evidence_even_with_good_signals():
    idea = samsung_input()
    idea.thesis = "좋아 보인다"

    result = evaluate_idea(idea)

    assert result.thesis_quality < 70
    assert result.decision == "REQUEST_MORE_EVIDENCE"
    assert "thesis" in " ".join(result.reason).lower()


def test_risk_breach_rejects_or_avoids_high_concentration_case():
    idea = samsung_input(portfolio_semis_weight=31.0)
    idea.portfolio.proposed_delta = 3.0

    result = evaluate_idea(idea)

    assert result.risk_status == "BREACH"
    assert result.decision == "REJECT_OR_AVOID"
    assert any(exception.status == "BREACH" for exception in result.risk_exceptions)


def test_evidence_weight_penalizes_stale_low_quality_sources():
    idea = samsung_input()
    idea.evidence = [
        Evidence(
            label="오래된 뉴스 헤드라인",
            source_type="news",
            source_quality=0.35,
            freshness_days=21,
            materiality=0.35,
            confirmatory_strength=0.30,
        )
    ]

    result = evaluate_idea(idea)

    assert result.evidence_score < 35
    assert result.decision == "REQUEST_MORE_EVIDENCE"


def test_portfolio_fit_improves_when_sector_has_room_and_liquidity_is_high():
    constrained = evaluate_idea(samsung_input(portfolio_semis_weight=28.5))
    roomy = evaluate_idea(samsung_input(portfolio_semis_weight=18.0))

    assert roomy.portfolio_fit > constrained.portfolio_fit
    assert roomy.decision in {"PROMOTE_TO_PM_REVIEW", "WATCHLIST_WITH_SIZE_CONSTRAINT"}
