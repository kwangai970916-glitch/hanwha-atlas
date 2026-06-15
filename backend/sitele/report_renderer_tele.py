# -*- coding: utf-8 -*-
"""
KOSPI 리포트 렌더러 - 3페이지 A4 버전 (시황텔레 수정본)
Page 1: 분석 본문
Page 2: KOSPI 차트/데이터 시각화 (오늘의 주요 헤드라인 카드 포함)
Page 3: KOSDAQ 차트/데이터 시각화 (오늘의 주요 헤드라인 카드 포함)
"""

import os
import json
import base64
from datetime import datetime
from playwright.sync_api import sync_playwright


def render_full_report(
    analysis_text: str,
    rs_data: list = None,
    top_contributors: list = None,
    bottom_contributors: list = None,
    adr_data: list = None,
    top_sectors: list = None,
    bottom_sectors: list = None,
    output_path: str = 'report_tele.png',
    date: str = None,
    sector_returns: list = None,
    top_gainers: list = None,
    top_losers: list = None,
    kosdaq_sectors: list = None,
    kosdaq_rs_data: list = None,
    kosdaq_top_contributors: list = None,
    kosdaq_bottom_contributors: list = None,
    kosdaq_top_gainers: list = None,
    kosdaq_top_losers: list = None,
    kosdaq_advance: int = 0,
    kosdaq_decline: int = 0,
    kosdaq_unchanged: int = 0,
    kosdaq_total: int = 0,
    kospi_advance: int = 0,
    kospi_decline: int = 0,
    kospi_unchanged: int = 0,
    kospi_total: int = 0,
    news_headlines: list = None,
    # NEW: F1b visual widgets
    theme_returns: list = None,
    kosdaq_theme_returns: list = None,
    investor: dict = None,
    indices: dict = None,
):
    """
    전체 리포트를 3페이지 A4 형태로 렌더링
    - Page 1: 분석 본문 + 수급/테마 위젯
    - Page 2: KOSPI 차트 (RS, 섹터수익률, 헤드라인, 등락률, breadth)
    - Page 3: KOSDAQ 차트 (RS, 섹터등락률, 헤드라인, breadth, 테마)
    """
    base_dir = os.path.dirname(os.path.abspath(__file__))
    template_path = os.path.join(base_dir, 'report_template_tele.html')

    if not os.path.exists(template_path):
        raise FileNotFoundError(f"템플릿 파일이 없습니다: {template_path}")

    # 날짜 포맷
    if date:
        display_date = date.replace('-', '.')
    else:
        display_date = datetime.now().strftime("%Y.%m.%d")

    # 섹터 수익률 데이터 준비 (rs_data에서 추출 가능)
    if sector_returns is None and rs_data:
        sector_returns = [
            {'sector': d.get('sector', ''), 'change': d.get('rs_1d', 0)}
            for d in rs_data
            if d.get('sector') not in ['KOSPI', '미편입종목', '은행']
        ]

    # 상승/하락률 TOP 10 데이터 (없으면 빈 리스트)
    if top_gainers is None:
        top_gainers = []
    if top_losers is None:
        top_losers = []

    # KOSDAQ 데이터 기본값
    if kosdaq_sectors is None:
        kosdaq_sectors = []
    if kosdaq_rs_data is None:
        kosdaq_rs_data = []
    if kosdaq_top_contributors is None:
        kosdaq_top_contributors = []
    if kosdaq_bottom_contributors is None:
        kosdaq_bottom_contributors = []
    if kosdaq_top_gainers is None:
        kosdaq_top_gainers = []
    if kosdaq_top_losers is None:
        kosdaq_top_losers = []

    report_title = '국내 증시 아침시황'

    # 데이터 준비
    report_data = {
        'date': display_date,
        'reportTitle': report_title,
        'analysisText': analysis_text,
        'rsData': rs_data or [],
        'topContributors': top_contributors or [],
        'bottomContributors': bottom_contributors or [],
        'adrData': adr_data or [],
        'topSectors': top_sectors or [],
        'bottomSectors': bottom_sectors or [],
        'sectorReturns': sector_returns or [],
        'topGainers': top_gainers,
        'topLosers': top_losers,
        'kosdaqSectors': kosdaq_sectors,
        'kosdaqRsData': kosdaq_rs_data,
        'kosdaqTopContributors': kosdaq_top_contributors,
        'kosdaqBottomContributors': kosdaq_bottom_contributors,
        'kosdaqTopGainers': kosdaq_top_gainers,
        'kosdaqTopLosers': kosdaq_top_losers,
        'kosdaqAdvance': kosdaq_advance or 0,
        'kosdaqDecline': kosdaq_decline or 0,
        'kosdaqUnchanged': kosdaq_unchanged or 0,
        'kosdaqTotal': kosdaq_total or 0,
        'kospiAdvance': kospi_advance or 0,
        'kospiDecline': kospi_decline or 0,
        'kospiUnchanged': kospi_unchanged or 0,
        'kospiTotal': kospi_total or 0,
        'newsHeadlines': news_headlines or [],
        # NEW: F1b visual widgets
        'themeReturns': theme_returns or [],
        'kosdaqThemeReturns': kosdaq_theme_returns or [],
        'investor': investor or None,
        'indices': indices or None,
    }

    print("🎨 3페이지 A4 리포트 렌더링 시작...")

    with sync_playwright() as p:
        print("🌐 브라우저 실행 중...")
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={'width': 1280, 'height': 5400})

        # HTML 로드
        print(f"📄 템플릿 로드: {template_path}")
        page.goto(f'file:///{template_path}')

        # 데이터 주입
        print("📊 데이터 주입 중...")
        page.evaluate(f'window.reportData = {json.dumps(report_data, ensure_ascii=True)}')

        # 초기화 함수 호출
        page.evaluate('init()')

        # 캔들차트 주입 (KOSPI → Page 2, KOSDAQ → Page 3)
        output_dir_path = os.path.dirname(output_path)
        for chart_id, filename in [('kospi-candle-img', 'candle_kospi.png'),
                                    ('kosdaq-candle-img', 'candle_kosdaq.png')]:
            candle_path = os.path.join(output_dir_path, filename)
            if os.path.exists(candle_path):
                print(f"📈 {filename} 주입 중...")
                with open(candle_path, 'rb') as f:
                    candle_b64 = base64.b64encode(f.read()).decode('utf-8')
                page.evaluate(f'''
                    const img = document.getElementById('{chart_id}');
                    if (img) {{ img.src = 'data:image/png;base64,{candle_b64}'; }}
                ''')

        # 폰트 로딩 대기
        page.wait_for_timeout(2000)

        # 출력 경로 설정
        output_dir = os.path.dirname(output_path)
        base_name = os.path.splitext(os.path.basename(output_path))[0]

        # Page 1 스크린샷
        page1_path = os.path.join(output_dir, f'{base_name}_page1.png')
        print(f"📸 Page 1 캡처: {page1_path}")
        page1 = page.query_selector('#page1')
        if page1:
            page1.screenshot(path=page1_path, type='png')

        # Page 2 스크린샷
        page2_path = os.path.join(output_dir, f'{base_name}_page2.png')
        print(f"📸 Page 2 캡처: {page2_path}")
        page2 = page.query_selector('#page2')
        if page2:
            page2.screenshot(path=page2_path, type='png')

        # Page 3 스크린샷
        page3_path = os.path.join(output_dir, f'{base_name}_page3.png')
        print(f"📸 Page 3 캡처: {page3_path}")
        page3 = page.query_selector('#page3')
        if page3:
            page3.screenshot(path=page3_path, type='png')

        browser.close()

    print(f"✅ 리포트 렌더링 완료:")
    print(f"   📄 Page 1 (본문): {page1_path}")
    print(f"   📊 Page 2 (KOSPI): {page2_path}")
    print(f"   📊 Page 3 (KOSDAQ): {page3_path}")

    return page1_path, page2_path, page3_path


if __name__ == "__main__":
    # 테스트
    test_analysis = """■ 1월 13일 KOSPI 아침 시황
- 코스피는 전일 대비 상승 출발하며 운송장비/부품, 금속 섹터가 강세를 보임.
- 간밤 미국 증시는 혼조세로 마감했으며, 다우와 S&P500은 상승함.

■ 운송장비/부품, 현대차그룹 HEV 라인업 강세
- 현대차(+7.535p), 현대모비스(+6.897p) 등이 지수 상승을 주도함.
- AI 로보틱스 및 SDV 전환 스토리가 부각됨.

■ 건설, PF 위기 지속
- 건설 섹터는 -1.60%로 가장 부진한 흐름을 보임."""

    test_rs = [
        {'sector': '운송장비', 'rs_1d': 3.5, 'rs_5d': 8.2, 'quadrant': '리더'},
        {'sector': '금속', 'rs_1d': 2.8, 'rs_5d': 5.1, 'quadrant': '리더'},
        {'sector': '건설', 'rs_1d': -1.2, 'rs_5d': -3.5, 'quadrant': '약세 지속'},
    ]

    test_top = [
        {'name': '현대차', 'contribution': 7.535},
        {'name': '현대모비스', 'contribution': 6.897},
        {'name': 'LG에너지솔루션', 'contribution': 3.673},
    ]

    test_bottom = [
        {'name': '삼성전자', 'contribution': -33.625},
        {'name': 'SK하이닉스', 'contribution': -11.847},
    ]

    test_adr = [
        {'date': '2026-01-10', 'kospi': 85.5, 'kosdaq': 72.3},
        {'date': '2026-01-11', 'kospi': 88.2, 'kosdaq': 75.1},
        {'date': '2026-01-12', 'kospi': 92.1, 'kosdaq': 78.5},
        {'date': '2026-01-13', 'kospi': 95.3, 'kosdaq': 82.1},
    ]

    test_sector_returns = [
        {'sector': '운송장비', 'change': 4.82},
        {'sector': '금속', 'change': 4.67},
        {'sector': '전기전자', 'change': -0.50},
        {'sector': '건설', 'change': -1.46},
    ]

    test_gainers = [
        {'name': '현대모비스', 'change': 15.10},
        {'name': '현대오토에버', 'change': 11.09},
        {'name': 'POSCO홀딩스', 'change': 9.61},
        {'name': '현대차', 'change': 8.45},
    ]

    test_losers = [
        {'name': '삼성전자', 'change': -3.40},
        {'name': 'SK하이닉스', 'change': -1.74},
        {'name': '네이버', 'change': -1.52},
    ]

    test_kosdaq_sectors = [
        {'sector': '기계/장비', 'change': -4.78, 'contribution': -8.931, 'weight': 16.02},
        {'sector': '제약', 'change': -4.01, 'contribution': -7.215, 'weight': 15.56},
        {'sector': '전기/전자', 'change': -3.40, 'contribution': -7.148, 'weight': 18.13},
    ]

    test_kosdaq_contributors = [
        {'name': '파두', 'change': 27.2, 'contribution': 0.9, 'weight': 0.5},
        {'name': '디어유', 'change': 19.08, 'contribution': 0.324, 'weight': 0.3},
        {'name': 'ISC', 'change': 3.98, 'contribution': 0.229, 'weight': 0.8},
    ]

    test_headlines = [
        {'title': "글로벌 금리 인하 기대감 지속에 코스피 강보합 출발", 'desc': "미 연준 위원들의 온건적 발언이 지수 지지력으로 작용."},
        {'title': "반도체주 외국인 매수세 유입... 엔비디아 영향 모니터링", 'desc': "SK하이닉스, 삼성전자 동반 반등 흐름 모색."},
        {'title': "원달러 환율 1,365원 선에서 하향 안정화 지속", 'desc': "달러 인덱스 소폭 하락과 위험 선호 심리 회복세."},
        {'title': "2차전지 섹터, 리튬 가격 상승에 반등 모멘텀 부각", 'desc': "에코프로 및 에코프로비엠 장중 동반 3% 이상 급등."}
    ]

    render_full_report(
        analysis_text=test_analysis,
        rs_data=test_rs,
        top_contributors=test_top,
        bottom_contributors=test_bottom,
        adr_data=test_adr,
        top_sectors=[],
        bottom_sectors=[],
        output_path='test_report.png',
        sector_returns=test_sector_returns,
        top_gainers=test_gainers,
        top_losers=test_losers,
        kosdaq_sectors=test_kosdaq_sectors,
        kosdaq_top_contributors=test_kosdaq_contributors,
        kosdaq_advance=375,
        kosdaq_decline=1302,
        kosdaq_unchanged=61,
        kosdaq_total=1803,
        news_headlines=test_headlines,
    )
