# -*- coding: utf-8 -*-
"""
시황텔레 봇 통합 테스트 및 실행기 (run_tele_morning.py)
1. 캔들 차트 이미지 자동 생성
2. 무인 자동 데이터 수집 (지수, 섹터 등락률, ADR, 상승/하락 TOP 10, 뉴스 헤드라인)
3. Playwright 기반 A4 3페이지 시황 리포트 이미지 렌더링
4. 텔레그램 채널 자동 발송
"""

import os
import sys
import io
import argparse
from datetime import datetime

# 윈도우 인코딩 에러 방지 (UTF-8 강제 지정)
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
if sys.stderr.encoding != 'utf-8':
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# 복제 및 정의한 모듈들 임포트
import generate_candle_tele
import auto_data_fetcher
import report_renderer_tele
import send_telegram_tele


def run_morning_report(send=False):
    print("==================================================")
    print("🚀 시황텔레 봇 통합 리포트 생성 프로세스 개시")
    print(f"현재 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("==================================================")

    # 1. 경로 설정
    base_dir = os.path.dirname(os.path.abspath(__file__))
    today_str = datetime.now().strftime("%Y%m%d")
    output_dir = os.path.join(base_dir, 'output', today_str)
    os.makedirs(output_dir, exist_ok=True)
    
    print(f"📁 출력 디렉토리: {output_dir}")

    # 2. 캔들 차트 이미지 생성 (KOSPI & KOSDAQ)
    print("\n[Step 1] KOSPI/KOSDAQ 캔들 차트 이미지 생성 시작...")
    try:
        generate_candle_tele.generate_candle_charts(output_dir)
        print("✅ 캔들 차트 이미지 생성 완료!")
    except Exception as e:
        print(f"❌ 캔들 차트 생성 중 오류 발생: {e}")
        # 오류가 나더라도 다음 단계 계속 진행

    # 3. 실시간 데이터 100% 무인 자동 수집
    print("\n[Step 2] 실시간 증시 데이터 자동 수집 시작...")
    adr_history_path = os.path.join(base_dir, 'adr_history.json')
    try:
        report_data = auto_data_fetcher.get_complete_report_data(history_path=adr_history_path)
        print("✅ 실시간 증시 데이터 및 주요 헤드라인 수집 완료!")
    except Exception as e:
        print(f"❌ 데이터 수집 중 오류 발생: {e}")
        # 임시 Mock 데이터 구성
        report_data = {
            'date': datetime.now().strftime("%Y.%m.%d"),
            'reportTitle': '국내 증시 아침시황 (임시 대체)',
            'analysisText': "■ KOSPI/KOSDAQ 자동 시황 데이터 수집 중 예외가 발생했습니다.\n- 네트워크 환경을 확인해 주세요.",
            'newsHeadlines': [
                {'title': '네트워크 환경 또는 네이버 금융 RSS 파싱 지연', 'desc': '임시 대체 시황으로 렌더링을 진행합니다.'}
            ]
        }

    # 4. A4 3페이지 프리미엄 이미지 렌더링
    print("\n[Step 3] A4 3페이지 프리미엄 리포트 이미지 렌더링 시작...")
    output_report_path = os.path.join(output_dir, 'tele_report.png')
    
    try:
        page1, page2, page3 = report_renderer_tele.render_full_report(
            analysis_text=report_data.get('analysisText', ''),
            rs_data=report_data.get('rsData', []),
            top_contributors=report_data.get('topContributors', []),
            bottom_contributors=report_data.get('bottomContributors', []),
            adr_data=report_data.get('adrData', []),
            top_sectors=report_data.get('topSectors', []),
            bottom_sectors=report_data.get('bottomSectors', []),
            output_path=output_report_path,
            date=report_data.get('date'),
            sector_returns=report_data.get('sectorReturns'),
            top_gainers=report_data.get('topGainers'),
            top_losers=report_data.get('topLosers'),
            kosdaq_sectors=report_data.get('kosdaqSectors'),
            kosdaq_rs_data=report_data.get('kosdaqRsData'),
            kosdaq_top_contributors=report_data.get('kosdaqTopContributors'),
            kosdaq_bottom_contributors=report_data.get('kosdaqBottomContributors'),
            kosdaq_top_gainers=report_data.get('kosdaqTopGainers'),
            kosdaq_top_losers=report_data.get('kosdaqTopLosers'),
            kosdaq_advance=report_data.get('kosdaqAdvance', 0),
            kosdaq_decline=report_data.get('kosdaqDecline', 0),
            kosdaq_unchanged=report_data.get('kosdaqUnchanged', 0),
            kosdaq_total=report_data.get('kosdaqTotal', 0),
            kospi_advance=report_data.get('kospiAdvance', 0),
            kospi_decline=report_data.get('kospiDecline', 0),
            kospi_unchanged=report_data.get('kospiUnchanged', 0),
            kospi_total=report_data.get('kospiTotal', 0),
            news_headlines=report_data.get('newsHeadlines', [])
        )
        print("\n==================================================")
        print("🎉 모든 시황 이미지 렌더링이 성공적으로 완수되었습니다!")
        print(f"📄 Page 1 (본문 요약): {page1}")
        print(f"📊 Page 2 (KOSPI 종합): {page2}")
        print(f"📊 Page 3 (KOSDAQ 종합): {page3}")
        print("==================================================")
        
        # 5. Telegram sending is opt-in only (--send), and while testing it is
        # deliberately routed to TELEGRAM_TEST_CHAT_ID only.
        if send:
            print("\n[Step 4] Sending generated report images to private Telegram test chat only...")
            success = send_telegram_tele.send_morning_tele_report(output_dir, test_only=True)
            if success:
                print("? ???? ?? ?? ??!")
            else:
                print("? ???? ?? ?? ??.")
        else:
            print("\n[Step 4] Safe default: Telegram sending skipped. Use --send to send.")
            
    except Exception as e:
        print(f"❌ 리포트 이미지 렌더링 중 오류 발생: {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Domestic market Telegram report generator")
    parser.add_argument("--send", action="store_true", help="Send generated report to Telegram. Default is generate-only.")
    args = parser.parse_args()
    send_enabled = False
    if args.send:
        send_enabled = True
    run_morning_report(send=send_enabled)
