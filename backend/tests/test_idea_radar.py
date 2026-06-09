from fastapi.testclient import TestClient

from app.main import app
from app import idea_radar

client = TestClient(app)


def test_radar_returns_composite_top_five():
    # use_llm=false: 컴포짓/Top Picks 파이프라인만 검증(외부 LLM 호출 없이 빠르게).
    response = client.get('/api/idea/radar?use_llm=false')

    assert response.status_code == 200
    body = response.json()
    assert body['horizon_months'] == 3
    assert len(body['themes']) >= 3
    assert len(body['top_picks']) == 5
    pick = body['top_picks'][0]
    assert {'chart', 'supply_demand', 'news', 'macro', 'valuation', 'risk'} <= set(pick['factor_scores'])
    assert len(pick['evidence']) >= 4
    assert len({item['factor'] for item in pick['evidence']}) >= 4
    assert not all('RS' in item['title'] for item in pick['evidence'])
    assert pick['thesis']
    assert pick['counter_evidence']
    assert pick['checklist']


def test_radar_exposes_newsflow_topdown_contract():
    response = client.get('/api/idea/radar?use_llm=false')

    assert response.status_code == 200
    body = response.json()
    assert body['engine'] == 'newsflow_topdown'
    assert body['pipeline']['mode'] == 'newsflow_topdown'
    assert body['pipeline']['stages'] == ['Macro', 'Sector', 'Stock']
    assert body['macro_flow']['label']
    assert len(body['sector_flow']) >= 3
    assert len(body['stock_candidates']) == len(body['top_picks'])
    candidate = body['stock_candidates'][0]
    assert candidate['route'][0] == body['macro_flow']['label']
    assert {'symbol', 'name', 'sector', 'theme', 'score', 'factor_scores'} <= set(candidate)
    assert 'news_flow' in body
    assert len(body['committee_minutes']) == 4
    assert body['committee_minutes'][0]['agent'] == 'Macro PM'


def test_regime_rules_risk_on_off_neutral():
    on = idea_radar.build_radar(use_llm=False, macro_snapshot={
        'vix': {'value': 15.2, 'change': -0.5},
        'usdkrw': {'value': 1370, 'change': 0.12},
        'kospi': {'value': 2700, 'change': 0.4},
    })['market_regime']
    off = idea_radar.build_radar(use_llm=False, macro_snapshot={
        'vix': {'value': 28.0, 'change': 3.0},
        'usdkrw': {'value': 1420, 'change': 1.1},
        'kospi': {'value': 2500, 'change': -1.2},
    })['market_regime']
    empty = idea_radar.build_radar(use_llm=False, macro_snapshot={})['market_regime']

    assert 'risk-on' in on['label'].lower()
    assert 'risk-off' in off['label'].lower()
    assert on['source'] == 'rules'
    # 근거에 실제 입력 수치가 인용되는지
    assert any('VIX 15.2' in r for r in on['rationale'])
    assert on['inputs']['vix'] == 15.2
    # 매크로 미수집이면 보수적으로 폴백하고 그 사유를 근거에 남긴다
    assert any('미수집' in r for r in empty['rationale'])


def test_regime_uses_llm_when_available(monkeypatch):
    def fake_call_llm(system, user):
        return ({
            'label': 'Risk-on',
            'summary': 'LLM 요약',
            'rationale': ['VIX 12.0 인용 근거', '원화 안정 근거'],
            'news_keywords': ['AI', '전력망'],
        }, 'mimo', [])

    monkeypatch.setattr('app.idea_engine._call_llm', fake_call_llm)
    mr = idea_radar.build_radar(use_llm=True, macro_snapshot={
        'vix': {'value': 12.0, 'change': -0.2},
        'usdkrw': {'value': 1360, 'change': 0.1},
        'kospi': {'value': 2750, 'change': 0.6},
    })['market_regime']

    assert mr['source'] == 'llm:mimo'
    assert mr['summary'] == 'LLM 요약'
    assert mr['rationale'] == ['VIX 12.0 인용 근거', '원화 안정 근거']
    # 데이터 근거(숫자)는 LLM 응답과 별개로 규칙 결과를 유지
    assert any('VIX 12.0' in d for d in mr['data_basis'])


def test_history_save_list_update_with_temp_store(tmp_path, monkeypatch):
    monkeypatch.setattr(idea_radar, 'HISTORY_PATH', tmp_path / 'idea_history.json')
    pick = client.get('/api/idea/radar?use_llm=false').json()['top_picks'][0]

    saved = client.post('/api/idea/history', json={'pick': pick, 'note': '검토'}).json()

    assert saved['status'] == 'new'
    assert saved['horizon_months'] == 3
    assert saved['note'] == '검토'
    listed = client.get('/api/idea/history').json()
    assert len(listed['items']) == 1
    updated = client.patch(
        f"/api/idea/history/{saved['idea_id']}",
        json={'status': 'reviewing', 'note': '회의 상정'},
    ).json()
    assert updated['status'] == 'reviewing'
    assert updated['note'] == '회의 상정'


def test_history_missing_or_corrupt_file_is_empty(tmp_path, monkeypatch):
    store = tmp_path / 'idea_history.json'
    monkeypatch.setattr(idea_radar, 'HISTORY_PATH', store)
    assert client.get('/api/idea/history').json()['items'] == []
    store.write_text('{not json', encoding='utf-8')
    assert client.get('/api/idea/history').json()['items'] == []

