from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_evaluate_idea_endpoint_returns_decision_package():
    response = client.post('/api/ideas/evaluate', json={"symbol": "005930"})

    assert response.status_code == 200
    body = response.json()
    result = body['result']
    assert body['intent'] == 'idea_evaluation'
    assert result['symbol'] == '005930'
    assert result['decision'] in {
        'PROMOTE_TO_PM_REVIEW',
        'WATCHLIST_WITH_SIZE_CONSTRAINT',
        'REQUEST_MORE_EVIDENCE',
        'REJECT_OR_AVOID',
        'KEEP_INVESTIGATING',
    }
    assert result['idea_score'] >= 0
    assert result['thesis_quality'] >= 0
    assert result['evidence_score'] >= 0
    assert 'score_breakdown' in result
    assert len(result['risk_exceptions']) >= 2
    assert len(result['required_checks']) >= 3


def test_evaluate_idea_endpoint_accepts_portfolio_override():
    response = client.post('/api/ideas/evaluate', json={
        "symbol": "005930",
        "portfolio_overrides": {"sector_weight": 31.0, "proposed_delta": 3.0}
    })

    assert response.status_code == 200
    result = response.json()['result']
    assert result['risk_status'] == 'BREACH'
    assert result['decision'] == 'REJECT_OR_AVOID'
