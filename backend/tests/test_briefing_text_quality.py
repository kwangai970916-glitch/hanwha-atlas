from __future__ import annotations

from sitele.hanwha_report_text import _postprocess_sections


def test_bull_breakout_level_cannot_be_below_current_kospi() -> None:
    sections = {
        "title": "시장 방향성",
        "stance": "NEUTRAL",
        "key_issue": "반도체 강세 확인됨. 외국인 매도는 부담임. 운수장비 확산 여부 주목됨.",
        "bull_case": "반도체 강세가 확산되고 외국인 매도가 순매수 전환될 경우 KOSPI 7,950~8,000선 재돌파 가능함.",
        "bear_case": "외국인 매도가 지속될 경우 하단 테스트 가능함.",
        "macro_flow": "—",
        "kr_outlook": "—",
        "strategy": "—",
        "news_flow": "—",
    }
    market_data = {
        "kr_indices": {"kospi": {"close": 8800.0, "chg_pct": 1.2}},
        "investor": {"foreign": -35055},
        "sectors": [{"sector": "반도체", "change": 3.4}],
    }

    fixed = _postprocess_sections(sections, market_data)

    assert "7,950~8,000선 재돌파" not in fixed["bull_case"]
    assert "8,890~8,980선 재돌파" in fixed["bull_case"]
    assert fixed["title"] == "반도체 +3.40%·KOSPI +1.20%·외국인 -35,055억"


def test_key_issue_is_forced_to_three_bullets_and_brand_is_corrected() -> None:
    sections = {
        "title": "반도체·KOSPI·수급",
        "stance": "RISK-ON",
        "key_issue": "한화생명 관점에서 반도체 강세 확인됨. 수급 부담 남아 있음. 운용 시사점은 추격보다 확인 매수임.",
        "bull_case": "KOSPI 8,900선 돌파 가능함.",
        "bear_case": "KOSPI 8,600선 테스트 가능함.",
        "macro_flow": "—",
        "kr_outlook": "—",
        "strategy": "—",
        "news_flow": "—",
    }
    market_data = {"kr_indices": {"kospi": {"close": 8800.0}}}

    fixed = _postprocess_sections(sections, market_data)

    assert fixed["key_issue"].count("\n") == 2
    assert fixed["key_issue"].splitlines()[0].startswith("- 팩트:")
    assert fixed["key_issue"].splitlines()[1].startswith("- 판단:")
    assert fixed["key_issue"].splitlines()[2].startswith("- 액션:")
    assert "한화생명" not in fixed["key_issue"]
    assert "한화손해보험" in fixed["key_issue"]


def test_bull_bear_are_structured_as_trigger_level_monitoring() -> None:
    sections = {
        "title": "반도체·KOSPI·수급",
        "stance": "NEUTRAL",
        "key_issue": "- 팩트: 반도체 +3.0% 상승함\n- 판단: 외국인 매도 부담임\n- 액션: 현물 전환 확인 필요함",
        "bull_case": "반도체 강세 확산 시 KOSPI 8,950선 돌파 가능함. 외국인 순매수 전환이 핵심임.",
        "bear_case": "외국인 매도 지속 시 KOSPI 8,600선 테스트 가능함. 환율 1,370원 상회가 부담임.",
        "macro_flow": "—",
        "kr_outlook": "—",
        "strategy": "—",
        "news_flow": "—",
    }
    market_data = {"kr_indices": {"kospi": {"close": 8800.0}}}

    fixed = _postprocess_sections(sections, market_data)

    assert fixed["bull_case"].splitlines()[0].startswith("- 트리거:")
    assert fixed["bull_case"].splitlines()[1].startswith("- 레벨:")
    assert fixed["bull_case"].splitlines()[2].startswith("- 모니터링:")
    assert fixed["bear_case"].splitlines()[0].startswith("- 트리거:")
    assert fixed["bear_case"].splitlines()[1].startswith("- 레벨:")
    assert fixed["bear_case"].splitlines()[2].startswith("- 모니터링:")
