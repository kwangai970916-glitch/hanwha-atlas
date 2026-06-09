from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_committee_review_returns_agent_opinions_and_pm_summary():
    response = client.post(
        "/api/committee/review",
        json={"symbol": "005930", "idea": "HBM 사이클 기반 비중 확대 검토"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert body["intent"] == "ai_committee_review"
    result = body["result"]
    assert result["symbol"] == "005930"
    assert result["name"] == "삼성전자"
    assert len(result["agent_opinions"]) == 8
    assert {opinion["agent"] for opinion in result["agent_opinions"]} == {
        "Fundamental",
        "Valuation",
        "Technical",
        "Sentiment / News",
        "Macro",
        "Risk Manager",
        "Bear Case",
        "Insurance PM",
    }
    assert result["final_view"]["stance"] in {"Approve", "Watch", "Defer", "Reject"}
    assert "AI Committee Review Memo" in result["committee_memo"]
    assert result["disclaimer"].startswith("본 자료는 내부 참고용")


def test_committee_review_has_deep_ai_hedge_fund_style_agent_contract():
    response = client.post(
        "/api/committee/review",
        json={"symbol": "005930", "idea": "HBM 사이클 기반 비중 확대 검토"},
    )

    assert response.status_code == 200
    result = response.json()["result"]
    assert result["depth_profile"]["level"] == "deep_multi_agent"
    assert result["source_inspiration"] == "virattt/ai-hedge-fund customized for insurance PM"
    assert {"bull", "base", "bear"} <= set(result["scenario_analysis"])
    assert len(result["debate"]["agreements"]) >= 2
    assert len(result["debate"]["disagreements"]) >= 2

    by_agent = {opinion["agent"]: opinion for opinion in result["agent_opinions"]}
    fundamental = by_agent["Fundamental"]
    assert len(fundamental["reasoning_steps"]) >= 4
    assert "financial_model" in fundamental["analysis"]
    assert "eps_revision_3m_pct" in fundamental["analysis"]["financial_model"]
    assert len(fundamental["citations"]) >= 2

    valuation = by_agent["Valuation"]
    assert "valuation_model" in valuation["analysis"]
    assert {"per", "pbr", "upside_pct"} <= set(valuation["analysis"]["valuation_model"])

    technical = by_agent["Technical"]
    assert "technical_indicators" in technical["analysis"]
    assert {"rsi", "ma_20", "ma_60", "relative_strength"} <= set(technical["analysis"]["technical_indicators"])

    risk = by_agent["Risk Manager"]
    assert "position_limit_check" in risk["analysis"]
    assert risk["analysis"]["position_limit_check"]["sector_limit"] > 0

    bear = by_agent["Bear Case"]
    assert len(bear["analysis"]["thesis_break_conditions"]) >= 3


def test_committee_agents_are_split_into_importable_modules():
    from app.ai_committee.agents.fundamental_agent import FundamentalAgent
    from app.ai_committee.agents.valuation_agent import ValuationAgent
    from app.ai_committee.agents.technical_agent import TechnicalAgent

    assert FundamentalAgent.name == "Fundamental"
    assert ValuationAgent.name == "Valuation"
    assert TechnicalAgent.name == "Technical"


def test_committee_triggers_include_pnl_and_price_alerts():
    response = client.get("/api/committee/triggers")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    triggers = body["result"]["triggers"]
    assert len(triggers) >= 2
    assert {"symbol", "name", "trigger_type", "severity", "reason"} <= set(triggers[0])
