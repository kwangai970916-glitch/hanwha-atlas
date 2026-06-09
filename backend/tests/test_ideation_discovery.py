from __future__ import annotations
from app.ideation import discovery


def test_discover_universe_shape_rule_mode():
    # use_llm 경로를 타지 않도록 라이브/LLM 없이도 동작해야 한다(폴백 결정론).
    u = discovery.discover_universe('AI 반도체', horizon_months=3)
    assert set(u) >= {'regime', 'themes', 'candidates', 'sector_flow', 'news_flow', 'source'}
    assert isinstance(u['candidates'], list) and len(u['candidates']) >= 1
    c = u['candidates'][0]
    assert {'symbol', 'name', 'sector', 'theme', 'score', 'factor_scores'} <= set(c)
    assert u['source'] in {'live', 'seed'}
    assert isinstance(u['regime'], dict) and 'label' in u['regime']


def test_lanes_in_themes_have_sector():
    u = discovery.discover_universe('', horizon_months=3)
    assert all('sector' in t for t in u['themes'])
