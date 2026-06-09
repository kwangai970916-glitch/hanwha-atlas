from fastapi.testclient import TestClient

from app.main import app
from app.security_analysis import SecurityDataLoader, SecurityAnalysisEngine

client = TestClient(app)


def test_security_data_loader_builds_complete_context_for_samsung():
    loader = SecurityDataLoader()
    context = loader.load_context("005930")

    assert context.company["name"] == "삼성전자"
    assert context.price["close"] == 78500
    assert context.valuation["pbr"] == 1.33
    assert len(context.financials_annual) >= 3
    assert len(context.sector_indicators) >= 2
    assert len(context.events) >= 2
    assert context.portfolio_position["weight"] == 18.0
    assert len(context.risk_limits) >= 3


def test_security_analysis_engine_produces_expert_sections():
    context = SecurityDataLoader().load_context("005930")
    report = SecurityAnalysisEngine().analyze(context)

    assert report.symbol == "005930"
    assert report.investment_view["action"] in {"PM Review", "Watch", "Avoid", "Request Evidence"}
    assert "thesis" in report.investment_view
    assert report.financial_analysis["revenue_growth_2026e"] > 0
    assert report.financial_analysis["op_margin_change_pp"] > 0
    assert report.valuation_analysis["pbr_premium_to_5y_avg_pct"] != 0
    assert len(report.catalyst_timeline) >= 2
    assert len(report.variant_perception["market_view"] ) > 0
    assert len(report.evidence_stack) >= 2
    assert len(report.counter_evidence) >= 1
    assert set(report.scenario_analysis.keys()) == {"bull", "base", "bear"}
    assert len(report.thesis_break_conditions) >= 3
    assert report.portfolio_impact["sector_weight_after"] > report.portfolio_impact["sector_weight_before"]
    assert len(report.decision_checklist) >= 6
    assert "Executive Investment View" in report.report_markdown
    assert "Valuation Analysis" in report.report_markdown
    assert "Portfolio Impact" in report.report_markdown


def test_security_analysis_report_includes_financial_model_and_justified_multiple_depth():
    context = SecurityDataLoader().load_context("005930")
    report = SecurityAnalysisEngine().analyze(context)

    snapshot = report.financial_analysis["financial_model_snapshot"]
    assert snapshot["forecast_year"] == "2026E"
    assert snapshot["op_margin_pct"] == 16.2
    assert snapshot["roe_pct"] == 12.7
    assert snapshot["fcf_trillion_krw"] == 33.0
    assert snapshot["capex_trillion_krw"] == 60.0
    assert snapshot["fcf_margin_pct"] == 9.4
    assert snapshot["capex_to_sales_pct"] == 17.0

    framework = report.valuation_analysis["roe_pbr_framework"]
    assert framework["method"] == "ROE-PBR justified multiple"
    assert framework["justified_pbr"] == 1.33
    assert framework["justified_pbr_gap_pct"] == 0.0
    assert framework["target_price"] == 93000
    assert framework["upside_pct"] == 18.5
    assert framework["target_source"] == "consensus"

    assert report.valuation_analysis["target_price"] == 93000
    assert report.valuation_analysis["upside_pct"] == 18.5
    assert "Financial Model Snapshot" in report.report_markdown
    assert "ROE-PBR Justified Multiple Framework" in report.report_markdown
    assert "Target Price / Upside" in report.report_markdown
    assert "FCF margin" in report.report_markdown
    assert "Capex/Sales" in report.report_markdown


def test_security_analysis_api_returns_markdown_report():
    response = client.post("/api/research/security-analysis", json={"symbol": "005930"})

    assert response.status_code == 200
    body = response.json()
    result = body["result"]
    assert body["intent"] == "security_analysis"
    assert result["symbol"] == "005930"
    assert "report_markdown" in result
    assert "Scenario Analysis" in result["report_markdown"]
    assert len(result["sources"]) >= 5


def test_security_analysis_unknown_symbol_returns_404():
    response = client.post("/api/research/security-analysis", json={"symbol": "999999"})

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "SECURITY_CONTEXT_NOT_FOUND"
