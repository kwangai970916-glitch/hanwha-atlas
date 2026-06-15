# -*- coding: utf-8 -*-
"""
미국 증시 요약 텍스트 정밀 파서 (us_data_parser.py)
- 주요 지수, 섹터별 등락, 상승/하락 TOP 5, 시장 폭, 시황 분석 정규식 기반 정밀 추출
"""

import re
import json

def parse_us_market_text(text):
    """
    미국 증시 요약 원시 텍스트를 분석하여 JSON 호환 딕셔너리로 반환
    """
    data = {
        "date": "2026.05.18", # 기본 날짜 (텍스트 파싱 실패 시)
        "indices": [],
        "sectors": [],
        "top_gainers": [],
        "top_losers": [],
        "breadth": {"advance": 0, "decline": 0, "unchanged": 0, "total": 0},
        "analysis_text": ""
    }
    
    # 0. 날짜 추출 시도
    date_match = re.search(r"(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일", text)
    if date_match:
        year, month, day = date_match.groups()
        data["date"] = f"{year}.{int(month):02d}.{int(day):02d}"
    else:
        # 백업 날짜 파싱 (2026-05-18 등)
        date_match_alt = re.search(r"(\d{4})[-.](\d{2})[-.](\d{2})", text)
        if date_match_alt:
            year, month, day = date_match_alt.groups()
            data["date"] = f"{year}.{month}.{day}"

    # 섹터별로 단락 쪼개기
    sections = re.split(r"■\s*", text)
    
    for section in sections:
        section = section.strip()
        if not section:
            continue
        
        lines = [line.strip() for line in section.split("\n") if line.strip()]
        title = lines[0]
        content_lines = lines[1:]
        
        # 1. 주요 지수
        if "주요 지수" in title:
            for line in content_lines:
                # 콜론 이전의 텍스트를 안전하게 이름으로 잡도록 Greedy 매칭 버그 수정 ([^:]+ 사용)
                match = re.match(r"^([^:]+):\s*([0-9\.,]+)\s*([▼▲]?)\s*([0-9\.]+)%", line)
                if match:
                    name, price, arrow, pct = match.groups()
                    pct_val = float(pct)
                    if arrow == "▼":
                        pct_val = -pct_val
                    data["indices"].append({
                        "name": name.strip(),
                        "close": float(price.replace(",", "")),
                        "change": pct_val
                    })
                    
        # 2. 섹터별 등락
        elif "섹터별 등락" in title:
            for line in content_lines:
                # 🟩🟩 에너지 +1.83%
                # 이름 영역에서 숫자 및 기호를 배제하고 확실한 공백 뒤 등락률을 캡처
                match = re.match(r"^([🟩🟥🟧🟨⬜\s]+)?([가-힣A-Za-z0-9\s\(\)\/\&]+)\s+([+-]?\d+\.?\d*)%", line)
                if match:
                    emojis, name, change = match.groups()
                    data["sectors"].append({
                        "sector": name.strip(),
                        "change": float(change)
                    })
                    
        # 3. 상승 TOP 5
        elif "상승 TOP" in title:
            for line in content_lines:
                # D $67.56 (+9.44%)
                match = re.match(r"^([A-Za-z0-9\s\-\.\&]+)\s*\$([0-9\.,]+)\s*\(\s*([+-]?\d+\.?\d*)%\s*\)", line)
                if match:
                    ticker, price, change = match.groups()
                    data["top_gainers"].append({
                        "name": ticker.strip(),
                        "close": float(price.replace(",", "")),
                        "change": float(change)
                    })
                    
        # 4. 하락 TOP 5
        elif "하락 TOP" in title:
            for line in content_lines:
                # FCX $60.50 (-3.98%)
                match = re.match(r"^([A-Za-z0-9\s\-\.\&]+)\s*\$([0-9\.,]+)\s*\(\s*([+-]?\d+\.?\d*)%\s*\)", line)
                if match:
                    ticker, price, change = match.groups()
                    data["top_losers"].append({
                        "name": ticker.strip(),
                        "close": float(price.replace(",", "")),
                        "change": float(change)
                    })
                    
        # 5. 시장 폭
        elif "시장 폭" in title:
            for line in content_lines:
                # 상승 359 | 하락 142 | 보합 2
                match = re.search(r"상승\s*([0-9]+)\s*\|\s*하락\s*([0-9]+)(?:\s*\|\s*보합\s*([0-9]+))?", line)
                if match:
                    adv, dec, unch = match.groups()
                    advance = int(adv) if adv else 0
                    decline = int(dec) if dec else 0
                    unchanged = int(unch) if unch else 0
                    total = advance + decline + unchanged
                    
                    # 괄호 안의 종목수 백업 확인
                    total_match = re.search(r"(\d+)종목", title)
                    if total_match:
                        total = int(total_match.group(1))
                        
                    data["breadth"] = {
                        "advance": advance,
                        "decline": decline,
                        "unchanged": unchanged,
                        "total": total
                    }
                    
        # 6. 시황 분석
        elif "시황 분석" in title:
            analysis_paragraphs = []
            for line in content_lines:
                analysis_paragraphs.append(line.strip())
            data["analysis_text"] = "\n\n".join(analysis_paragraphs)
            
    return data

if __name__ == "__main__":
    test_txt = """
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
    parsed = parse_us_market_text(test_txt)
    print(json.dumps(parsed, ensure_ascii=False, indent=2))
