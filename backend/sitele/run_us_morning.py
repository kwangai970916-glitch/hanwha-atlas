# -*- coding: utf-8 -*-
"""
미국 증시 데일리 텔레리포트 통합 실행기 (run_us_morning.py)
- 원시 텍스트 입력 ➔ 파싱 ➔ HTML 데이터 주입 ➔ Playwright 이미지 렌더링 ➔ 텔레그램 전송을 원클릭으로 처리
"""

import os
import sys
import argparse
from us_data_parser import parse_us_market_text
from us_report_renderer import render_us_report
from send_telegram_us import send_us_market_photo
from fetch_us_market_data import fetch_us_market_data, format_us_market_text

# Windows 콘솔 인코딩 에러 방지 (Pre-emptive Unicode handling)
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

# 기본 예시 데이터 (2026-05-20 미국증시 요약)
DEFAULT_TEXT = """
2026-05-20 미국증시 요약

■ 주요 지수
  S&P500: 7,432.97 ▲1.08%
  나스닥: 26,270.36 ▲1.54%
  다우: 50,009.34 ▲1.31%
  러셀2000: 2,817.36 ▲2.60%

■ 섹터별 등락 (가중평균)
  🟩🟩 에너지 +2.10%
  🟩🟩 기술 +1.65%
  🟩 필수소비재 +1.45%
  🟩 커뮤니케이션 +1.20%
  🟩 금융 +1.15%
  🟩 산업재 +0.95%
  🟩 헬스케어 +0.80%
  🟩 소재 +0.70%
  🟩 부동산 +0.35%
  🟥 경기소비재 -0.15%
  🟥 유틸리티 -0.40%

■ 상승 TOP 5
  RRGB $12.34 (+18.20%)
  UAL $58.20 (+10.01%)
  SMCI $890.50 (+9.49%)
  DAL $45.60 (+9.39%)
  CCL $16.50 (+8.96%)

■ 하락 TOP 5
  ENGN $1.20 (-80.56%)
  GDC $0.55 (-79.30%)
  BTM $0.45 (-73.24%)
  HON $192.40 (-4.20%)
  INTU $610.50 (-3.85%)

■ 시장 폭 (S&P 500 503종목)
  상승 412 | 하락 88 | 보합 3

■ 시황 분석
2026년 5월 20일 미국 증시는 연방공개시장위원회(FOMC) 회의록 공개를 앞두고 국채 금리가 안정적 하향 흐름을 보인 가운데, 주요 거시 인플레이션 지표의 둔화 조짐이 유입되며 3대 지수가 일제히 사상 최고치를 경신하는 강력한 랠리를 펼쳤습니다. 다우존스 산업평균지수는 역사상 최초로 마의 50,000달러 선을 상향 돌파하며 상징적인 이정표를 세웠고, S&P 500과 나스닥 역시 초대형 AI 반도체 강세를 등에 업고 전고점을 단숨에 넘어섰습니다.

이날 시장의 핵심 동력은 엔비디아의 실적 발표를 목전에 둔 AI 하드웨어 밸류체인으로의 투기적 매수세 재유입이었습니다. Super Micro Computer(+9.49%)와 AMD(+8.1%)가 거래대금 최상위를 기록하며 시장 전반의 위험 선호(Risk-on) 심리를 자극했고, 금리에 민감한 성장주 전반으로 온기가 확산되었습니다. 또한 국제 유가의 하락 안정화 기조는 델타항공(+9.39%)을 비롯한 항공·운송 섹터의 가파른 수익성 개선 기대감을 자아내며 경기 순환주로의 뚜렷한 순환매를 이끌어냈습니다.

종목별로는 Red Robin(+18.20%)과 TJX 등 소매유통 섹터가 시장 예상을 뛰어넘는 어닝 서프라이즈를 달성하며 내수 소비력의 건전함을 방증했고, 이는 다우 지수의 상방 지지력을 전폭적으로 보강했습니다. 매크로 관점에서 가장 고무적인 신호는 S&P 500 내 412개 종목이 일제히 상승하며 마켓 브레드(시장 폭)가 81.9%에 달하는 압도적 매수 우위를 보여주었다는 점입니다. 이는 소수 빅테크에만 의존하던 '좁은 상승'에서 벗어나 시장 전반의 기초체력(Fundamental)이 뒷받침되는 '건강한 광범위한 랠리'로 질적 전환을 이루고 있음을 시사합니다.
"""

def main():
    parser = argparse.ArgumentParser(description="미국 증시 데일리 텔레리포트 통합 실행 봇")
    parser.add_argument('--text_file', type=str, default=None, help='파싱할 미국 증시 원시 텍스트 파일 경로')
    parser.add_argument('--direct_text', type=str, default=None, help='파싱할 미국 증시 원시 텍스트 직접 입력')
    parser.add_argument('--template', type=str, default='us_report_template.html', help='HTML 템플릿 파일 경로')
    parser.add_argument('--output', type=str, default='us_market_summary.png', help='저장할 아웃풋 이미지 경로')
    parser.add_argument('--send', action='store_true', help='Send generated report to Telegram. Default is generate-only.')
    parser.add_argument('--skip_send', action='store_true', help='Compatibility option. Sending is already disabled by default.')
    parser.add_argument('--chat_id', type=str, default=None, help='전송할 텔레그램 채팅방 ID (쉼표로 구분하여 여러 개 지정 가능)')
    
    args = parser.parse_args()
    
    print("[INFO] ===============================================")
    print("[INFO] 미국 증시 텔레리포트 파이프라인 가동을 시작합니다.")
    print("[INFO] ===============================================")
    
    raw_text = ""
    
    # 1. 텍스트 소스 확보
    if args.direct_text:
        print("[INFO] 명령줄 인자로부터 텍스트를 직접 획득했습니다.")
        raw_text = args.direct_text
    elif args.text_file:
        if not os.path.exists(args.text_file):
            print(f"[ERROR] 지정된 텍스트 파일을 찾을 수 없습니다: {args.text_file}")
            sys.exit(1)
        print(f"[INFO] 텍스트 파일 로드 중: {args.text_file}")
        with open(args.text_file, 'r', encoding='utf-8') as f:
            raw_text = f.read()
    else:
        # 인자가 없으면 하드코딩 샘플이 아니라 미장 마감 데이터 수집기로 생성합니다.
        # 휴장일이면 휴장 리포트 텍스트가 생성됩니다.
        print("[INFO] 텍스트 입력 인자가 없어 미국 마감 데이터 자동 수집을 실행합니다.")
        market_data = fetch_us_market_data(use_previous_if_closed=True)
        raw_text = format_us_market_text(market_data)
            
    # 2. 텍스트 파싱
    print("[INFO] [1단계] 미국 증시 데이터 정밀 파싱을 개시합니다...")
    try:
        parsed_data = parse_us_market_text(raw_text)
        print("[SUCCESS] 텍스트 파싱이 정상적으로 완수되었습니다.")
        print(f"[SUCCESS] 날짜: {parsed_data.get('date')}")
        print(f"[SUCCESS] 파싱된 지수 수: {len(parsed_data.get('indices', []))}")
        print(f"[SUCCESS] 파싱된 섹터 수: {len(parsed_data.get('sectors', []))}")
    except Exception as e:
        print(f"[ERROR] 파싱 단계에서 예외가 분출되었습니다: {e}")
        sys.exit(1)
        
    # 3. 프리미엄 인포그래픽 이미지 렌더링
    print("[INFO] [2단계] Playwright 기반 프리미엄 HTML 렌더링을 가동합니다...")
    try:
        output_image_path = render_us_report(
            data=parsed_data,
            template_path=args.template,
            output_path=args.output
        )
        print(f"[SUCCESS] 초프리미엄 리포트 이미지 생성 완료! -> {output_image_path}")
    except Exception as e:
        print(f"[ERROR] Playwright 이미지 생성 실패: {e}")
        sys.exit(1)
        
    # 4. ???? ??: ??? ?? --send? ?? ?? ??
    if args.send:
        if args.skip_send:
            print("[INFO] --send? --skip_send? ?? ???? ???? ??? ?????.")
        else:
            # ???? ??? ?? ??? ??? ???? ???? ??? ???? ??
            caption = raw_text
            success = send_us_market_photo(output_image_path, caption=caption, chat_id=args.chat_id, test_only=True)
            if success:
                print("[SUCCESS] ?? ????? ??? ????? ????????.")
            else:
                print("[ERROR] ???? ??? ???? ?? ??? ???????.")
                sys.exit(1)
    else:
        print("[INFO] ?? ?? ??: ???? ??? ?????. ????? --send ??? ?????.")

if __name__ == '__main__':
    main()
