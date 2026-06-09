from app import price_service as ps
from app.sector_taxonomy import to_major_sector


def test_taxonomy_maps_known_and_unknown():
    assert to_major_sector('반도체와반도체장비') == '정보기술'
    assert to_major_sector('증권') == '금융'
    assert to_major_sector('제약') == '헬스케어'
    assert to_major_sector('석유와가스') == '에너지'
    assert to_major_sector('전기유틸리티') == '유틸리티'
    # 미등록명은 키워드 폴백
    assert to_major_sector('이차전지소재화학') == '소재'
    # 미상/미분류
    assert to_major_sector('기타') == '기타'
    assert to_major_sector('') == '기타'
    assert to_major_sector(None) == '기타'


def test_heatmap_groups_by_major_and_cap_weights(monkeypatch):
    rows = [
        {'symbol': '005930', 'display': '삼성전자', 'sector': '반도체와반도체장비', 'change': 1.0, 'market_cap': 3000.0, 'price': 70000},
        {'symbol': '000660', 'display': 'SK하이닉스', 'sector': '반도체와반도체장비', 'change': -2.0, 'market_cap': 1000.0, 'price': 200000},
        {'symbol': '055550', 'display': '신한지주', 'sector': '은행', 'change': 0.5, 'market_cap': 2000.0, 'price': 50000},
        {'symbol': 'XXXXXX', 'display': '미분류주', 'sector': '기타', 'change': 9.0, 'market_cap': 9999.0, 'price': 100},
        {'symbol': 'NOCHG', 'display': '결측주', 'sector': '은행', 'change': None, 'market_cap': 500.0, 'price': 1},
    ]
    monkeypatch.setattr(ps, '_get_kospi_market_rows', lambda: rows)

    h = ps.get_market_heatmap()
    by = {s['sector']: s for s in h['sectors']}

    # 미분류('기타')는 제외
    assert '기타' not in by
    # 정보기술 = 삼성/하이닉스 시총가중: (1*3000 + -2*1000)/4000 = 0.25
    assert by['정보기술']['change'] == 0.25
    assert by['정보기술']['count'] == 2
    # 금융 = 신한지주(결측주는 change None 이라 제외)
    assert by['금융']['change'] == 0.5
    assert by['금융']['count'] == 1
    assert h['up'] + h['down'] == len(h['sectors'])


def test_intraday_change_pct_is_self_consistent(monkeypatch):
    class FakeResp:
        status_code = 200
        def json(self):
            return [
                {'localDateTime': '20260602090000', 'currentPrice': 100.0},
                {'localDateTime': '20260602093000', 'currentPrice': 104.0},
                {'localDateTime': '20260602100000', 'currentPrice': 110.0},
            ]
    monkeypatch.setattr(ps.requests, 'get', lambda *a, **k: FakeResp())
    # 전일종가 산출용 실시간 쿼트 모킹: price=110, change=+10 → prev=100
    monkeypatch.setattr(ps, '_naver_stock', lambda code: {'price': 110.0, 'change': 10.0, 'change_pct': -99.0})

    d = ps.get_intraday('005930', points=80)
    assert d['prev_close'] == 100.0
    assert d['last'] == 110.0
    # change_pct 는 q['change_pct'](-99) 가 아니라 prev/last 로 재계산 → +10.0
    assert d['change_pct'] == 10.0
    assert len(d['points']) == 3
    assert d['points'][0]['t'] == '0900'
