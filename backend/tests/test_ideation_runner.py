from __future__ import annotations
import time
from app.ideation import runner

FAKE_UNIVERSE = {
    'regime': {'label': 'neutral', 'summary': 's', 'source': 'rules'},
    'themes': [{'sector': '반도체', 'theme': 'AI', 'score': 80, 'macro_tags': []}],
    'candidates': [{'symbol': '000660', 'name': 'SK하이닉스', 'sector': '반도체', 'theme': 'AI',
                    'score': 86, 'factor_scores': {}, 'timing_signal': {'signal': 'enter'}}],
    'sector_flow': [{'sector': '반도체', 'theme': 'AI', 'score': 80}],
    'news_flow': [], 'sector_rank': [], 'source': 'seed', '_radar': {},
}


def _fast_committee(monkeypatch):
    # 실데이터 발굴을 fake로 대체 → 스레드가 즉시 끝나도록(러너 기계 검증용)
    monkeypatch.setattr('app.ideation.orchestrator.discover_universe', lambda *a, **k: FAKE_UNIVERSE)
    monkeypatch.setattr('app.idea_engine._call_llm', lambda s, u: (None, None, ['x']))
    monkeypatch.setattr('app.idea_engine.build_idea', lambda *a, **k: {})


def _wait_done(jid, timeout=20):
    for _ in range(timeout * 5):
        st = runner.get_status(jid)
        if st.get('stage') in ('done', 'error'):
            return st
        time.sleep(0.2)
    return runner.get_status(jid)


def test_start_run_completes_and_returns_result(monkeypatch, tmp_path):
    _fast_committee(monkeypatch)
    monkeypatch.setattr(runner, 'OUT_ROOT', tmp_path)

    started = runner.start_run('AI 반도체', horizon_months=3)
    jid = started['job_id']
    st = _wait_done(jid)
    assert st['stage'] == 'done'

    msgs = runner.get_messages(jid, since=0)
    assert msgs['total'] >= 5
    later = runner.get_messages(jid, since=msgs['messages'][-1]['idx'])
    assert all(m['idx'] >= msgs['messages'][-1]['idx'] for m in later['messages'])

    res = runner.get_result(jid)
    assert res['engine'] == 'ideation_committee' and res['top_picks']


def test_unknown_job_is_safe():
    assert runner.get_status('nope')['stage'] == 'unknown'
    assert runner.get_messages('nope')['messages'] == []


def test_latest_falls_back_to_seed_when_no_live(monkeypatch, tmp_path):
    # 라이브 done 잡이 없으면 seed/*.json 으로 폴백(데모 빈화면 방지)
    monkeypatch.setattr(runner, 'OUT_ROOT', tmp_path)
    monkeypatch.setattr(runner, 'SEED_DIR', tmp_path / 'seed')
    (tmp_path / 'seed').mkdir(parents=True)
    (tmp_path / 'seed' / 's.json').write_text(
        '{"engine":"ideation_committee","top_picks":[1]}', encoding='utf-8')
    runner._jobs.clear()
    res = runner.get_latest_result()
    assert res['engine'] == 'ideation_committee'
