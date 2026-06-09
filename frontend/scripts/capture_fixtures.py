"""라이브 백엔드(:8000)에서 전 GET 엔드포인트 응답을 캡처해 오프라인 fixture로 저장.

실행: cd frontend && python scripts/capture_fixtures.py
산출: frontend/src/offline/fixtures.json  (키=pathname 또는 와일드카드)
"""
import json
import os
import urllib.request

BASE = 'http://127.0.0.1:8000'

GETS = [
    '/api/health', '/api/data-status',
    '/api/market/snapshot', '/api/market/sectors', '/api/market/breadth',
    '/api/market/heatmap', '/api/market/universe', '/api/market/table',
    '/api/market/kpi', '/api/market/news',
    '/api/pnl', '/api/pnl/curve', '/api/pnl/risk', '/api/pnl/attribution',
    '/api/pnl/trades', '/api/pnl/rolling-risk', '/api/pnl/holding-series', '/api/pnl/news',
    '/api/briefing/history', '/api/briefing/schedule', '/api/briefing/latest',
    '/api/committee/latest', '/api/idea/committee/latest', '/api/idea/history',
]

# 경로 파라미터 라우트: 대표값으로 캡처하고 와일드카드 키에 저장
PARAM = {
    '/api/market/intraday/*': '/api/market/intraday/005930',
    '/api/market/candles/*': '/api/market/candles/005930',
    '/api/briefing/*/status': '/api/briefing/close/status',
}


def get(path, timeout=40):
    try:
        with urllib.request.urlopen(BASE + path, timeout=timeout) as r:
            return json.loads(r.read().decode('utf-8'))
    except Exception as e:
        print('  WARN', path, '->', repr(e)[:120])
        return None


def main():
    out = {}
    for p in GETS:
        out[p] = get(p)
        print('captured', p, '->', 'ok' if out[p] is not None else 'FAIL')
    for key, p in PARAM.items():
        out[key] = get(p)
        print('captured', key, '<-', p, '->', 'ok' if out[key] is not None else 'FAIL')

    dst = os.path.join(os.path.dirname(__file__), '..', 'src', 'offline', 'fixtures.json')
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    with open(dst, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False)
    got = sum(1 for v in out.values() if v is not None)
    print(f'WROTE {os.path.abspath(dst)} | keys={len(out)} captured={got}')


if __name__ == '__main__':
    main()
