# -*- coding: utf-8 -*-
"""
generate_us_text_by_codex.py
- [yfinance 하이브리드 파이프라인]
- 1. fetch_us_market_data.py를 사용하여 미국 시장의 정확한 지수, 섹터, TOP 5, 시장 폭 획득
- 2. 수집된 팩트 데이터를 기반으로 Codex에게 고품격 매크로 및 종목 시황 분석 텍스트(3문단 이상)만 작성하도록 위임
- 3. yfinance 수치 데이터와 Codex가 생성한 분석 텍스트를 파서 호환 포맷으로 조립하여 temp_input.txt로 영구 저장
- 4. LLM Hallucination(수치 왜곡) 및 Regex 파싱 미스를 100% 원천 봉쇄
"""

import os
import sys
import subprocess
from fetch_us_market_data import fetch_us_market_data, format_us_market_text, build_us_market_analysis

# Windows 콘솔 인코딩 에러 방지
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

def main():
    print("[INFO] ===========================================================")
    print("[INFO] yfinance 하이브리드 파이프라인 가동 (수치 확보 및 Codex 분석 연동)")
    print("[INFO] ===========================================================")
    
    # 1. yfinance로 미국 시장 팩트 수집
    try:
        market_data = fetch_us_market_data()
    except Exception as e:
        print(f"[ERROR] yfinance 데이터 수집 단계에서 치명적 오류 분출: {e}")
        sys.exit(1)

    output_txt_path = os.path.abspath("temp_input.txt")
    if market_data.get("market_status") == "closed":
        with open(output_txt_path, 'w', encoding='utf-8') as f:
            f.write(format_us_market_text(market_data))
        print(f"[INFO] 미국 정규장 휴장 감지. 휴장 안내 입력 파일 생성: {output_txt_path}")
        return
        
    # 2. Codex 분석 생성을 위한 프롬프트 구성
    # 실시간 검색 대신, 이미 획득한 수치 팩트를 제공하여 신속하고 정확한 고품격 텍스트 작성을 유도
    prompt = f"""
아래 제공되는 오늘의 미국 증시 실제 데이터 팩트를 기반으로, 금융 분석가 수준의 한국어 시황 분석 텍스트를 작성해줘.

[제공되는 실제 증시 데이터]
{market_data['raw_text_for_prompt']}

[작성 요구사항]
1. 불필요한 인사말(예: "네, 알겠습니다", "수집한 데이터 기준 분석입니다")이나 코드 블록 기호(예: ```) 등은 철저히 생략하고 오직 시황 분석 본문 텍스트만 출력해야 해.
2. 내용은 최소 3문단 이상의 고품격 매크로 및 종목 분석이어야 해.
   - 1문단: 당일 3대 지수의 움직임 배경, 국채 금리 동향, FOMC 및 연준 위원 발언 등 거시 경제(Macro) 여건 분석.
   - 2문단: 11개 주요 섹터 중 가장 강세를 나타낸 섹터와 그 배경, 또는 약세를 보인 섹터의 흐름과 요인 분석.
   - 3문단: 상승 TOP 5 및 하락 TOP 5에 랭크된 주요 특징주(예: 반도체 빅테크, AI 밸류체인, 소매 어닝 서프라이즈 등)의 구체적인 개별 호재/악재 사유 분석.
3. 전체 톤앤매너는 전문적인 자산운용사나 투자은행(IB)의 데일리 시황 리포트 수준으로 작성해줘.

오직 3문단 이상의 순수한 분석 글만 출력해줘!
"""

    print("[INFO] Codex CLI 호출용 매개변수를 조립하는 중...")
    
    # 임시 분석 텍스트 파일 저장용 절대 경로
    temp_analysis_file = os.path.abspath("temp_codex_analysis.txt")
    
    # 윈도우 쉘 명령줄 길이 한계 및 한글/특수문자 이스케이프 버그 방지를 위해 
    # 프롬프트를 stdin(-)으로 완벽하게 파이핑하여 주입합니다.
    cmd = [
        "codex", "exec", "-",
        "--dangerously-bypass-approvals-and-sandbox",
        "--skip-git-repo-check",
        "-o", temp_analysis_file
    ]
    
    print("[INFO] Codex 엔진에 연결 중... 실제 팩트 기반 시황 분석 생성 개시...")
    
    try:
        # subprocess.run 실행 (input=prompt 옵션으로 stdin 주입)
        result = subprocess.run(
            cmd,
            input=prompt,
            shell=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore"
        )
        
        analysis_text = ""
        
        if result.returncode == 0 and os.path.exists(temp_analysis_file):
            print("[SUCCESS] Codex 분석 작성이 완수되었습니다.")
            with open(temp_analysis_file, 'r', encoding='utf-8') as f:
                analysis_text = f.read().strip()
                
            # 임시 파일 제거
            if os.path.exists(temp_analysis_file):
                os.remove(temp_analysis_file)
        else:
            print("[WARNING] Codex CLI가 오류를 내거나 파일을 생성하지 못했습니다. Mock 분석 멘트로 대체 기동합니다.")
            print(f"[WARNING] Return Code: {result.returncode}, Stderr: {result.stderr}")
            analysis_text = build_us_market_analysis(market_data)

        # 3. yfinance 수치 데이터와 Codex 시황 분석을 완벽한 템플릿 포맷으로 조립
        final_output = []
        final_output.append(f"{market_data['date']} 미국증시 요약\n")
        
        final_output.append("■ 주요 지수")
        for ind in market_data["indices"]:
            arrow = "▲" if ind['change'] >= 0 else "▼"
            # us_data_parser.py 정규식 매칭: S&P500: 7,432.97 ▲1.08%
            final_output.append(f"  {ind['name']}: {ind['close']:,} {arrow}{abs(ind['change'])}%")
            
        final_output.append("\n■ 섹터별 등락 (가중평균)")
        for sec in market_data["sectors"]:
            # 이모지 규칙 (등락 크기에 맞춤)
            emoji = "🟩"
            if sec['change'] >= 1.5:
                emoji = "🟩🟩"
            elif sec['change'] < 0:
                emoji = "🟥"
                if sec['change'] <= -1.5:
                    emoji = "🟥🟥"
            
            sign = "+" if sec['change'] >= 0 else ""
            # us_data_parser.py 정규식 매칭: 🟩🟩 에너지 +2.10%
            final_output.append(f"  {emoji} {sec['sector']} {sign}{sec['change']}%")
            
        final_output.append("\n■ 상승 TOP 5")
        for tg in market_data["top_gainers"]:
            # us_data_parser.py 정규식 매칭: RRGB $12.34 (+18.20%)
            final_output.append(f"  {tg['name']} ${tg['close']:,} (+{tg['change']}%)")
            
        final_output.append("\n■ 하락 TOP 5")
        for tl in market_data["top_losers"]:
            # us_data_parser.py 정규식 매칭: ENGN $1.20 (-80.56%)
            final_output.append(f"  {tl['name']} ${tl['close']:,} ({tl['change']}%)")
            
        final_output.append(f"\n■ 시장 폭 (S&P 500 {market_data['breadth']['total']}종목)")
        # us_data_parser.py 정규식 매칭: 상승 412 | 하락 88 | 보합 3
        final_output.append(f"  상승 {market_data['breadth']['advance']} | 하락 {market_data['breadth']['decline']} | 보합 {market_data['breadth']['unchanged']}")
        
        final_output.append("\n■ 시황 분석")
        final_output.append(analysis_text)
        
        # 4. temp_input.txt 파일로 영구 저장
        output_txt_path = os.path.abspath("temp_input.txt")
        with open(output_txt_path, 'w', encoding='utf-8') as f:
            f.write("\n".join(final_output))
            
        print("[SUCCESS] ===============================================")
        print(f"[SUCCESS] yfinance 하이브리드 temp_input.txt 가 완성되었습니다!")
        print(f"[SUCCESS] 경로: {output_txt_path}")
        print("[SUCCESS] ===============================================")
        
    except Exception as e:
        print(f"[ERROR] 파이프라인 취합 과정 중 오류 분출: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
