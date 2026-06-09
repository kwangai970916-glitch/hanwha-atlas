from app.security_analysis import SecurityDataLoader, SecurityAnalysisEngine


def test_korean_dataset_text_is_not_mojibake():
    context = SecurityDataLoader().load_context("005930")
    report = SecurityAnalysisEngine().analyze(context)

    assert context.company["name"] == "삼성전자"
    assert context.company["sector"] == "반도체"
    assert "�" not in context.company["name"]
    assert "ì" not in context.company["name"]
    assert "삼성전자 전문가형 증권분석 보고서" in report.report_markdown
    assert "반도체" in report.report_markdown
