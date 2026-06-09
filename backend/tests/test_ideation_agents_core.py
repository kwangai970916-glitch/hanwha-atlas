from __future__ import annotations
from app.ideation import agents


def test_speak_json_uses_fallback_when_llm_unavailable(monkeypatch):
    # _call_llm이 (None, None, errors) → 폴백 반환
    monkeypatch.setattr('app.idea_engine._call_llm', lambda s, u: (None, None, ['no_llm_key']))
    parsed, provider = agents._speak_json('sys', 'user', fallback={'speech': 'fb', 'x': 1})
    assert parsed == {'speech': 'fb', 'x': 1}
    assert provider == 'rules'


def test_speak_json_returns_llm_dict(monkeypatch):
    monkeypatch.setattr('app.idea_engine._call_llm',
                        lambda s, u: ({'speech': 'real', 'favored_lanes': ['반도체']}, 'mimo', []))
    parsed, provider = agents._speak_json('sys', 'user', fallback={'speech': 'fb'})
    assert parsed['favored_lanes'] == ['반도체']
    assert provider == 'mimo'


def test_speak_text_falls_back(monkeypatch):
    monkeypatch.setattr('app.idea_engine._call_llm', lambda s, u: (None, None, ['x']))
    text, provider = agents._speak_text('sys', 'user', fallback_text='규칙 발언')
    assert text == '규칙 발언' and provider == 'rules'
