# -*- coding: utf-8 -*-
"""
미국 증시 리포트 Playwright 렌더러 (us_report_renderer.py)
- JSON 데이터를 HTML 템플릿에 동적 주입하고 1200x1600 고해상도 PNG 이미지로 렌더링
"""

import os
import json
from playwright.sync_api import sync_playwright

def render_us_report(data, template_path="us_report_template.html", output_path="us_market_summary.png"):
    """
    JSON 데이터를 받아 HTML 템플릿에 인젝션하고, Playwright로 고화질 PNG 렌더링
    """
    print("[INFO] 미국 증시 인포그래픽 이미지 렌더링 시작...")
    
    # 1. 템플릿 파일 로드
    if not os.path.exists(template_path):
        raise FileNotFoundError(f"템플릿 파일을 찾을 수 없습니다: {template_path}")
        
    with open(template_path, 'r', encoding='utf-8') as f:
        html_content = f.read()
        
    # 2. window.usReportData 데이터 치환 주입
    # 데이터 인젝션을 위해 JSON 문자열로 변환
    json_data_str = json.dumps(data, ensure_ascii=False, indent=4)
    
    # HTML 내 window.usReportData = window.usReportData || { ... }; 부분을 타겟으로 치환
    target_pattern = "window.usReportData = window.usReportData || {"
    if target_pattern in html_content:
        # 데이터가 정의되는 블록 전체를 window.usReportData = { ... }; 형식으로 심플하게 덮어씁니다.
        # 템플릿의 script 태그 내부에서 window.usReportData 선언부를 안전하게 교체
        replace_code = f"window.usReportData = {json_data_str};"
        # window.usReportData = window.usReportData || { ... }; 대괄호 묶음 전체를 교체하기 위해 안전하게 스크립트 바인딩
        # 템플릿 안에서 데이터 주입 시작 주석이나 선언부를 날카롭게 치환
        start_idx = html_content.find("window.usReportData = window.usReportData || {")
        end_idx = html_content.find("};", start_idx) + 2
        
        if start_idx != -1 and end_idx != -1:
            html_content = html_content[:start_idx] + replace_code + html_content[end_idx:]
            print("[SUCCESS] 데이터 인젝션 성공!")
    else:
        print("[WARNING] 데이터 선언 영역 매칭 실패. 백업 치환 시도...")
        # 백업 대체용 (간단한 문자열 치환)
        html_content = html_content.replace("// Python에서 수집한 데이터가 여기에 안전하게 바인딩됩니다.", f"window.usReportData = {json_data_str};")
        
    # 3. 임시 렌더링용 HTML 파일 작성
    temp_html_path = os.path.abspath("temp_render_us.html")
    with open(temp_html_path, 'w', encoding='utf-8') as f:
        f.write(html_content)
        
    # 4. Playwright 브라우저 기동 및 캡처
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.on("console", lambda msg: print(f"[JS CONSOLE] {msg.text}"))
            
            # 고정 인포그래픽 해상도 크기 설정 (세로형 대시보드 규격 1200x1160)
            page.set_viewport_size({"width": 1200, "height": 1160})
            
            # 로컬 파일 열기
            file_url = f"file:///{temp_html_path.replace(os.sep, '/')}"
            page.goto(file_url, wait_until="networkidle")
            
            # 외부 구글 폰트 로드를 위해 추가 여유 대기(1000ms)
            page.wait_for_timeout(1000)
            
            # 스크린샷 캡처
            element = page.query_selector(".infographic-canvas")
            if element:
                element.screenshot(path=output_path, type="png")
                print(f"[SUCCESS] 프리미엄 인포그래픽 이미지 저장 완료: {output_path}")
            else:
                page.screenshot(path=output_path, full_page=True)
                print(f"[WARNING] .infographic-canvas 클래스를 찾지 못해 전체 페이지 스크린샷 캡처: {output_path}")
                
            browser.close()
    except Exception as e:
        print(f"[ERROR] Playwright 렌더링 실패: {e}")
        raise e
    finally:
        # 5. 임시 렌더링 파일 안전 삭제
        if os.path.exists(temp_html_path):
            pass # os.remove(temp_html_path)
            
    return output_path

if __name__ == "__main__":
    # 단독 기능 테스트용 더미 데이터
    dummy_data = {
        "date": "2026.05.18",
        "indices": [
            { "name": "S&P500", "close": 5738.65, "change": -0.07 },
            { "name": "나스닥", "close": 18705.88, "change": -0.43 },
            { "name": "다우", "close": 43497.01, "change": 0.33 },
            { "name": "러셀2000", "close": 2275.97, "change": -0.59 }
        ],
        "sectors": [
            { "sector": "에너지", "change": 1.83 },
            { "sector": "부동산", "change": 1.71 },
            { "sector": "금융", "change": 1.29 },
            { "sector": "필수소비재", "change": 1.23 },
            { "sector": "산업재", "change": 0.56 },
            { "sector": "헬스케어", "change": 0.54 },
            { "sector": "커뮤니케이션", "change": 0.39 },
            { "sector": "소재", "change": 0.16 },
            { "sector": "유틸리티", "change": -0.12 },
            { "sector": "경기소비재", "change": -0.17 },
            { "sector": "기술", "change": -0.29 }
        ],
        "top_gainers": [
            { "name": "D", "close": 67.56, "change": 9.44 },
            { "name": "NOW", "close": 103.42, "change": 8.78 },
            { "name": "BSX", "close": 55.92, "change": 6.15 },
            { "name": "ACN", "close": 177.55, "change": 5.17 },
            { "name": "ISRG", "close": 439.92, "change": 4.46 }
        ],
        "top_losers": [
            { "name": "FCX", "close": 60.50, "change": -3.98 },
            { "name": "ETN", "close": 381.87, "change": -4.40 },
            { "name": "NEE", "close": 89.04, "change": -4.63 },
            { "name": "AMAT", "close": 413.57, "change": -5.28 },
            { "name": "MU", "close": 681.54, "change": -5.95 }
        ],
        "breadth": { "advance": 359, "decline": 142, "unchanged": 2, "total": 503 },
        "analysis_text": "2026년 5월 18일 미증시는 혼조세로 마감했음. 다우만 +0.33% 상승, S&P500과 나스닥은 각각 -0.07%, -0.43% 하락하며 종목별 차별화가 극심했음. 시장 폭은 상승 359 대 하락 142로 양호했으나, 시총 상위 빅테크 약세가 지수를 짓눌렀음."
    }
    render_us_report(dummy_data)
