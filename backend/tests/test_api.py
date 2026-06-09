from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_returns_ok():
    response = client.get('/api/health')
    assert response.status_code == 200
    assert response.json()['status'] == 'ok'


def test_data_status_lists_sample_sources():
    response = client.get('/api/data-status')
    assert response.status_code == 200
    body = response.json()
    assert body['status'] == 'success'
    source_names = {source['name'] for source in body['result']['sources']}
    assert {'market_summary', 'sector_snapshot', 'stock_universe'} <= source_names


def test_command_routes_morning_brief():
    response = client.post('/api/command', json={'query': '오늘 운용회의 준비해줘'})
    assert response.status_code == 200
    body = response.json()
    assert body['intent'] == 'morning_brief'
    assert 'market_view' in body['result']
    assert body['result']['disclaimer'].startswith('본 자료는 내부 참고용')


def test_command_routes_stock_diagnosis():
    response = client.post('/api/command', json={'query': '삼성전자 진단해줘'})
    assert response.status_code == 200
    body = response.json()
    assert body['intent'] == 'stock_diagnosis'
    assert body['result']['stock']['name'] == '삼성전자'
    assert body['result']['final_view'] in {'관심', '보류', '주의'}


def test_morning_brief_contains_sources_and_actions():
    response = client.post('/api/morning-brief', json={'market': 'KR'})
    assert response.status_code == 200
    body = response.json()
    assert body['status'] == 'success'
    assert len(body['result']['sectors_to_watch']) >= 2
    assert len(body['result']['actions']) >= 2
    assert len(body['sources']) >= 3
    assert body['confidence'] > 0


def test_stock_diagnosis_for_unknown_stock_returns_404():
    response = client.post('/api/stock-diagnosis', json={'symbol': '없는종목'})
    assert response.status_code == 404
    assert response.json()['detail']['code'] == 'STOCK_NOT_FOUND'


def test_report_generate_returns_markdown_and_telegram_text():
    brief = client.post('/api/morning-brief', json={'market': 'KR'}).json()['result']
    response = client.post('/api/report-generate', json={
        'report_type': 'executive_summary',
        'source_result': brief,
        'tone': '실장 보고'
    })
    assert response.status_code == 200
    body = response.json()
    assert body['result']['format'] == 'markdown'
    assert '# 실장 보고용 요약' in body['result']['content']
    assert 'telegram_text' in body['result']
    assert body['result']['disclaimer'].startswith('본 자료는 내부 참고용')


def test_market_stream_exposes_sse_contract():
    with client.stream('GET', '/api/market/stream?limit=1') as response:
        assert response.status_code == 200
        assert response.headers['content-type'].startswith('text/event-stream')
        first_line = next(response.iter_lines())
        assert first_line.startswith('data: ')
        assert 'provider_status' in first_line
        assert 'ticks' in first_line
