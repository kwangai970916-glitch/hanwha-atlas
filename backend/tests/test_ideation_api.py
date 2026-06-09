from __future__ import annotations
import time
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

FAKE_UNIVERSE = {
    'regime': {'label': 'neutral', 'summary': 's', 'source': 'rules'},
    'themes': [{'sector': '반도체', 'theme': 'AI', 'score': 80, 'macro_tags': []}],
    'candidates': [{'symbol': '000660', 'name': 'SK하이닉스', 'sector': '반도체', 'theme': 'AI',
                    'score': 86, 'factor_scores': {}, 'timing_signal': {'signal': 'enter'}}],
    'sector_flow': [{'sector': '반도체', 'theme': 'AI', 'score': 80}],
    'news_flow': [], 'sector_rank': [], 'source': 'seed', '_radar': {},
}


def test_committee_run_status_messages_result(monkeypatch):
    # 실데이터 발굴을 fake로 대체해 인프로세스 스레드가 즉시 끝나도록(API 계약 검증용)
    monkeypatch.setattr('app.ideation.orchestrator.discover_universe', lambda *a, **k: FAKE_UNIVERSE)
    monkeypatch.setattr('app.idea_engine._call_llm', lambda s, u: (None, None, ['x']))
    monkeypatch.setattr('app.idea_engine.build_idea', lambda *a, **k: {})

    r = client.post('/api/idea/committee/run', params={'keywords': 'AI 반도체'})
    assert r.status_code == 200
    jid = r.json()['job_id']

    for _ in range(100):
        st = client.get('/api/idea/committee/status', params={'job_id': jid}).json()
        if st['stage'] in ('done', 'error'):
            break
        time.sleep(0.2)
    assert st['stage'] == 'done'

    msgs = client.get(f'/api/idea/committee/messages/{jid}', params={'since': 0}).json()
    assert msgs['total'] >= 5

    res = client.get('/api/idea/committee/result', params={'job_id': jid}).json()
    assert res['engine'] == 'ideation_committee'
