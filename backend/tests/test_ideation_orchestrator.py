from __future__ import annotations
import json
from app.ideation.orchestrator import run_committee
from app.ideation.stream import RunStream


def test_run_committee_streams_all_stages_and_assembles(tmp_path, monkeypatch):
    # LLM 무가용 → 전 단계 룰 폴백으로 결정론 동작
    monkeypatch.setattr('app.idea_engine._call_llm', lambda s, u: (None, None, ['no_llm']))
    monkeypatch.setattr('app.idea_engine.build_idea', lambda *a, **k: {})
    s = RunStream(tmp_path)
    decision = run_committee('AI 반도체', 3, s)

    # 1) 전 단계 stage가 messages.jsonl에 등장
    lines = [json.loads(x) for x in (tmp_path / 'messages.jsonl').read_text(encoding='utf-8').splitlines()]
    stages = {m['stage'] for m in lines}
    assert {'discovery', 'sector_debate', 'nomination', 'risk_review', 'decision'} <= stages
    assert [m['idx'] for m in lines] == list(range(len(lines)))  # idx 단조

    # 2) decision.json = RadarResponse 상위호환
    assert decision['engine'] == 'ideation_committee'
    for k in ('market_regime', 'sector_flow', 'top_picks', 'stock_candidates',
              'committee_minutes', 'transcript', 'news_flow'):
        assert k in decision
    assert len(decision['top_picks']) >= 1
    # committee_minutes는 실제 transcript(발언들)
    assert len(decision['committee_minutes']) >= 4
    # status done
    st = json.loads((tmp_path / 'status.json').read_text(encoding='utf-8'))
    assert st['stage'] == 'done'


def test_run_committee_top_picks_have_required_fields(tmp_path, monkeypatch):
    monkeypatch.setattr('app.idea_engine._call_llm', lambda s, u: (None, None, ['x']))
    monkeypatch.setattr('app.idea_engine.build_idea', lambda *a, **k: {})
    s = RunStream(tmp_path)
    decision = run_committee('', 3, s)
    p = decision['top_picks'][0]
    assert {'symbol', 'name', 'sector', 'score', 'thesis', 'factor_scores'} <= set(p)
