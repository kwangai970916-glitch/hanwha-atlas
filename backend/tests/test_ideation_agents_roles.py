from __future__ import annotations
from app.ideation import agents

REGIME = {'label': 'Selective risk-on', 'summary': '위험선호 우호', 'data_basis': ['VIX 16.2 안정']}
LANES = [
    {'sector': '반도체', 'theme': 'AI 인프라', 'score': 82, 'news_score': 80, 'macro_tags': ['AI capex']},
    {'sector': '방산', 'theme': '방산·우주', 'score': 70, 'news_score': 74, 'macro_tags': ['지정학']},
]
CANDS = [
    {'symbol': '000660', 'name': 'SK하이닉스', 'sector': '반도체', 'theme': 'AI 인프라', 'score': 86,
     'factor_scores': {'chart': 86, 'news': 87, 'risk': 63}},
]


def test_macro_brief_fallback(monkeypatch):
    monkeypatch.setattr('app.idea_engine._call_llm', lambda s, u: (None, None, ['x']))
    speech, regime = agents.macro_brief(REGIME)
    assert isinstance(speech, str) and speech
    assert regime is REGIME


def test_sector_bull_bear_manager_fallback(monkeypatch):
    monkeypatch.setattr('app.idea_engine._call_llm', lambda s, u: (None, None, ['x']))
    bull_speech, bull = agents.sector_bull(REGIME, LANES, prior='')
    bear_speech, bear = agents.sector_bear(REGIME, LANES, prior=bull_speech)
    mgr_speech, mgr = agents.research_manager(REGIME, LANES, bull_speech, bear_speech)
    assert bull['favored_lanes'] and bear['risky_lanes']
    assert mgr['winning_lanes']  # 폴백은 점수 상위 레인
    assert mgr['winning_lanes'][0] in {l['sector'] for l in LANES}


def test_stock_picker_nominates(monkeypatch):
    monkeypatch.setattr('app.idea_engine._call_llm', lambda s, u: (None, None, ['x']))
    # build_idea grounding은 best-effort; 실패해도 후보 자체로 지명되어야 한다.
    monkeypatch.setattr('app.idea_engine.build_idea', lambda *a, **k: {})
    speech, out = agents.stock_picker('반도체', CANDS)
    assert out['nominations'][0]['symbol'] == '000660'


def test_risk_threeway_and_manager_fallback(monkeypatch):
    monkeypatch.setattr('app.idea_engine._call_llm', lambda s, u: (None, None, ['x']))
    nominee = {'symbol': '000660', 'name': 'SK하이닉스',
               'timing_signal': {'signal': 'wait', 'rsi': 72, 'reason': 'RSI 72 과매수'}}
    a, _ = agents.risk_aggressive(nominee, prior='')
    b, _ = agents.risk_conservative(nominee, prior=a)
    c, _ = agents.risk_neutral(nominee, prior=b)
    speech, mgr = agents.risk_manager([nominee], debate_hist=f'{a}\n{b}\n{c}')
    assert isinstance(mgr['blocked_symbols'], list)


def test_pm_chair_ranks(monkeypatch):
    monkeypatch.setattr('app.idea_engine._call_llm', lambda s, u: (None, None, ['x']))
    nominees = [dict(CANDS[0]), {'symbol': '012450', 'name': '한화에어로스페이스',
                'sector': '방산', 'theme': '방산·우주', 'score': 84, 'factor_scores': {}}]
    speech, out = agents.pm_chair(REGIME, ['반도체'], nominees, risk_notes={'blocked_symbols': []})
    assert out['ranked'] and out['ranked'][0] in {n['symbol'] for n in nominees}
