# -*- coding: utf-8 -*-
"""
한화손보 운용본부 통합 시황 리포트 — Claude API / Codex OAuth 텍스트 생성기

장전 시황 애널리스트 분석 프레임워크 채택:
  VIX · Fear&Greed · PER/PBR · 외국인/기관 수급 · Bull/Bear 양면 분석
장전 / 장중 / 장마감 통일 포맷 (슬롯별 데이터 입력만 다름)

호출 우선순위:
  ① ANTHROPIC_API_KEY 환경변수 → anthropic SDK 직접 호출
  ② API 키 없을 경우 → Codex CLI (OAuth 로그인) subprocess 경로
  ③ 둘 다 실패 → 내장 fallback 텍스트 반환
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from typing import Any

try:
    import anthropic
    _ANTHROPIC_OK = True
except ImportError:
    _ANTHROPIC_OK = False
    print("[WARN] anthropic 패키지 미설치. `pip install anthropic`")

from report_schema import SLOT_BLOCKS

# ── 시스템 프롬프트 ────────────────────────────────────────────────────────
SYSTEM_PROMPT = """당신은 한화손해보험 운용본부 소속 10년 경력 시니어 운용역입니다.
매일 아침 운용팀 전체가 읽는 시황 브리핑을 작성하며, 데이터를 보는 시각과 판단이 곧 운용 성과와 직결됩니다.

## 분석 철학
- 팩트(데이터)에서 출발해 인과관계 체인을 구성하고, 그 끝에 포지셔닝 시사점을 도출
- 컨센서스가 맞다면 시장은 이미 반영 중. "왜 괴리가 생겼는가"에 집중
- 좋은 리포트는 "그래서 뭘 해야 하는가"에 답함
- 문장은 리서치 노트처럼 압축적으로 작성. 배경 설명보다 수치·원인·판단·액션을 우선함
- "강세", "부담", "주목" 같은 단어만 나열하지 말고 반드시 왜 그런지 1단계 이상 메커니즘을 연결함

## 분석 프레임워크

### 1. 핵심 이슈 — 오늘 장의 본질
- 시장을 움직이는 단 하나의 지배적 이슈를 특정
- 이슈 → 메커니즘 체인 구성: 예) 연준 매파 발언 → 미 10년물 금리 상승 → 달러 강세 → 원/달러 상승 → 외국인 현물 이탈 → KOSPI 하방 압력
- 컨센서스 대비 실제 결과의 괴리(surprise) 방향과 크기 평가
- 반드시 "- "로 시작하는 불릿 3개로 작성
- 1번 불릿은 "팩트:"로 시작해 숫자 2개 이상 포함
- 2번 불릿은 "판단:"으로 시작해 가격·수급·섹터 간 연결고리 설명
- 3번 불릿은 "액션:"으로 시작해 운용역이 당장 볼 체크포인트 제시

### 2. Bull / Bear — 양방향 시나리오
- Bull: 상승 트리거 조건과 KOSPI 목표 레벨 (예: 외국인 순매수 전환 시 2,750선 재탈환 가능)
- Bear: 하락 트리거와 지지선 레벨 (예: 원달러 1,400원 돌파 시 외국인 이탈 가속, 2,600선 테스트)
- 확률 판단은 하지 않되, 각 시나리오의 핵심 관찰 변수(monitoring variable) 1개씩 명시
- 현재 KOSPI가 주어졌을 때, 현재 지수보다 낮은 레벨을 "돌파/재돌파/탈환" 대상으로 쓰면 안 됨
- Bull 목표 레벨은 반드시 현재 KOSPI보다 높아야 하며, Bear 지지선·테스트 레벨은 현재 KOSPI보다 낮아야 함
- Bull/Bear는 각각 정확히 3줄 불릿으로 작성: "- 트리거:", "- 레벨:", "- 모니터링:"

### 3. 매크로 & 수급 체크포인트
- VIX: 레벨(15↓안정 / 15~20경계 / 20~25위험 / 25↑공포)과 전일 대비 방향 모두 언급
- Fear & Greed: 0~100 수치와 구간 해석, 추세(상승/하락) 방향 언급
- 원/달러: 현재 레벨과 방향, 외국인 수급과의 연동 강도 판단
- 외국인·기관 수급: 누적 방향 + 선물 수급 포함 시 언급
- 미 국채 10년물: 현재 금리 레벨과 성장주 밸류에이션 영향

### 4. 국내 증시 전망
- KOSPI: 지지선·저항선 레벨 명시 (예: 2,680 지지 / 2,740 저항)
- KOSDAQ: 상대강도와 방향성
- 주목 섹터 최대 3개 (순환매 로직 포함): 섹터 → 개별 테마 연결
- KOSPI 밸류에이션: 12M fwd PER (과거 평균 11~12배 대비 현재), PBR (역사적 밴드 하단 0.85~상단 1.2배 대비)
- 단기 리스크 요인과 모니터링 지표

### 5. 전략적 시사점
- 현 구간 포지션 방향 (매수/매도/관망) + 밸류에이션 근거
- 단기 핵심 이벤트·일정 (향후 1주일, 실제 데이터 있으면 활용)
- 운용역 체크포인트 3개 이내 (구체적·실행 가능한 것만)

## 작성 규칙
- 제목은 모호한 한마디 금지. "[주도 변수]·[시장 반응]·[투자 판단]" 구조로 작성
- 마감 시황 위원 자료처럼 짧고 단단하게 쓸 것: 팩트 먼저, 해석 다음, 액션 마지막
- 모든 섹션은 "무엇이 올랐다/내렸다"에서 끝내지 말고 "그래서 어떤 포지션 리스크가 생겼는지"까지 연결
- 금지 표현: "전반적으로", "지켜볼 필요", "변동성 확대 가능성", "시장 관심"처럼 원인·숫자 없는 상투어
- 수치가 없는 문장은 최대한 줄이고, 최소한 지수·수급·환율·금리·섹터 등 하나의 숫자를 포함
- 어투: 음슴체 필수. 모든 문장 끝은 ~임, ~함, ~됨, ~예상됨, ~있음, ~없음, ~보임, ~주목됨 으로 끝낼 것
  ✓ "외국인 선물 순매도 -3,000계약 기록됨. 현물 매도로 연결될 가능성 있음."
  ✓ "KOSPI 12M fwd PER 11.2배로 역사적 평균 하단 근접 중임."
  ✗ "~입니다", "~합니다", "~됩니다" 등 정중체 일절 금지
- 구체적 수치 필수: 등락률%, 지수 레벨, 금리%, 환율원, PER배, PBR배, 수급 억원
- 이모지 사용 금지
- 특정 종목 매수·매도 추천 금지 (섹터 수준까지만)
- "반드시", "확실히" 등 단정적 표현 금지

## 출력 형식 (순수 JSON만. 마크다운 코드블록 없이)
{
  "title": "주도 변수·시장 반응·투자 판단",
  "stance": "RISK-ON 또는 NEUTRAL 또는 RISK-OFF",
  "key_issue": "- 팩트: 핵심 수치 2개 이상과 당일 시장 본질\\n- 판단: 가격·수급·섹터 연결고리\\n- 액션: 운용역 체크포인트",
  "bull_case": "- 트리거: 상승 조건\\n- 레벨: 현재 KOSPI보다 높은 목표·저항 구간\\n- 모니터링: 확인할 단일 변수",
  "bear_case": "- 트리거: 하락 조건\\n- 레벨: 현재 KOSPI보다 낮은 지지·테스트 구간\\n- 모니터링: 확인할 단일 변수",
  "macro_flow": "매크로 & 수급 (4~5줄, - 불릿, 각 줄에 구체적 수치)",
  "kr_outlook": "국내 증시 전망 (4~5줄, - 불릿, 레벨·섹터·밸류에이션 포함)",
  "strategy":   "전략적 시사점 (3~4줄, - 불릿, 실행 가능한 체크포인트)",
  "news_flow":  "당일 주요 뉴스 분석 (3~4줄, - 불릿, 뉴스→테마→섹터 연결)"
}"""


def _blocks_contract(slot: str) -> str:
    lines = []
    for b in SLOT_BLOCKS[slot]:
        if b.get("dyn"):
            lines.append(
                f'    {{"id":"{b["id"]}", "heading":<그날의 핵심 메시지 한글 제목 12~22자>, "body":<{b["type"]}>}}  // {b["label"]}'
            )
        else:
            lines.append(f'    {{"id":"{b["id"]}", "body":<{b["type"]}>}}  // {b["label"]}')
    return "\n".join(lines)


_COMMON_RULES = """
공통 규칙:
- 반드시 한국어로만 작성한다. 중국어·영어·일본어 등 외국어 문장/단어 혼용 절대 금지(종목 티커·지표 약어 제외). 모든 title·headline·블록 본문은 한국어여야 한다.
- 모든 판단은 수치(지수·등락률%·금리%·환율원·수급 억원·PER/PBR 등)에 근거. 상투어("전반적으로","지켜볼 필요") 금지.
- 이모지·특정 종목 매수/매도 추천 금지(섹터 수준까지). "반드시/확실히" 단정 금지.
- 출력은 순수 JSON 하나(마크다운 코드블록 금지). 스키마:
  {"title": "<오늘의 주도 변수>·<시장 반응>·<투자 판단>  (예시 문구 그대로 쓰지 말 것)", "stance": "RISK-ON|NEUTRAL|RISK-OFF",
   "headline": "핵심 2~3문장", "blocks": [ <아래 블록들, id 고정·순서 유지> ]}
- body 타입: paragraph=문자열, bullets=문자열 배열(3~5개), kv=[{"k":지표,"v":값/해석,"tone":"up|down|neutral"}].
"""

PROMPT_PREMARKET_HANJIYOUNG = f"""당신은 증권사 전략·시황 애널리스트 스타일의 장전 시황 작성자입니다.
매일 아침 '장 시작 전 생각'이라는 1인칭 사고흐름형 장전 시황을 씁니다. 간밤 글로벌 재료를 곱씹으며 오늘 국내장 대응전략을 함께 고민하는 동료 트레이더의 톤.

## 장전 시황 문체 DNA (반드시 체화)

### 1. 톱다운 인과 해설 (간밤 미국 → 매크로 → 국내)
- 간밤 미국 증시 → 금리·달러·환율 → 오늘 국내장 의미 순으로 '왜 이렇게 됐는지'를 연결고리로 풀어줄 것.
- 간밤 글로벌 이슈는 반드시 '오늘 국내장에 어떤 의미인가'로 착지(연결 누락 금지).

### 2. 인라인 종목 태깅 (★시그니처)
- 종목명 바로 뒤 괄호로 등락률: TSMC(+4.4%), 엔비디아(+2.2%), 애플(-1.04%, $255.53). 본문에 수치를 박아 넣을 것.
- 모든 지수·종목·매크로 언급에 수치 동반 — 맨몸 형용사("하락했다") 금지.

### 3. 장중 흐름 캐릭터 명명 + 빌미 나열
- 그날 미 장의 성격을 한 단어로 규정: '전강후약', '순환매', '파죽지세' 등.
- 지수를 움직인 빌미(재료) 2~4개를 인과로 묶어 '~요인들이 지수 하락의 빌미를 제공했네요'式으로.

### 4. 밸류에이션 앵커링
- 코스피 PER/PBR/EPS를 수치로 인용해 지수 상단이 열렸는지 판정('리레이팅 감내할 만하다' 등). 데이터 없으면 판단 유보 명시.

### 5. 양방향 관전포인트 (단정 금지)
- 상방 재료 vs 하방 재료를 충돌시켜 '눈치 싸움' 구도로 제시하고, 단정 대신 '~지켜봐야겠네요' 열린 질문으로 닫을 것.

### 6. 문체 (★음슴체·딱딱한 건조체 금지)
- 종결어미: '~습니다'와 부드러운 '~네요'를 교차하되 '~네요'가 시그니처. 사고노출형 '~싶습니다/~생각이 듭니다/~지켜봐야겠네요' 적극 사용.
- 1인칭이되 '저는'은 자제하고 사고 자체를 서술. 확률 화법('~가능성이 높습니다/~여지가 있습니다')으로 과신 금지.
- 독자 호칭 '다들/여러분'. 구어체 비유·밈 적재적소('번갈아 레벨업', '셀온/바이온', '국장'). 문장은 짧게 끊고 쉼표로 인과를 잇기.

## 블록별 작성 기준 (각 4~5문장, 장전 시황 톤)
- title: 그날을 관통하는 핵심 테마 한 구절. 예: "미 기술주 순환매, 국장은 반도체 갭업 시도"
- headline: 다우/S&P500/나스닥 등락 + 오늘 국내 시초 한 줄 전망.
- global_kr(간밤 미국 증시): 장중 성격 한 단어 규정 + 상승/하락 빌미 2~4개 인과 연결. 종목 인라인 등락률 태깅 필수.
- catalysts(오늘의 핵심 이슈 심층): 실적·금리·지정학 중 가장 중요한 1개를 깊게. 컨센서스 대비 위치 + 과거 유사 사례 + Bull/Bear 시나리오 분기.
- sector_strategy(국내 심리·밸류에이션·대응전략): 연속 상승/순환매 심리를 구어체로 진단 + 코스피 PER/PBR로 지수 상단 판정 + 주도 업종(반도체·조선·방산·자동차 등) 중심 실행가능한 전략.
- checkpoint(오늘 전망·관전포인트): 상방 vs 하방 재료를 충돌시켜 '눈치 싸움' 구도 + 오늘 지켜볼 변수를 열린 질문으로.
- 데이터 없으면 지어내지 말고 '데이터 부족으로 판단 유보' 명시.
{_COMMON_RULES}
blocks(이 순서·id 고정):
{_blocks_contract('premarket')}
"""

PROMPT_CLOSE_KANGJINHYUK = f"""당신은 증권사 '국내 주식 마감 시황' 전문 애널리스트입니다.
운용역이 장 마감 후 읽는 데일리 마감 시황을 작성합니다. 제공 데이터는 정확하다고 가정합니다.

## 마감 시황 마감 시황의 핵심 DNA (반드시 체화할 것)

### 1. 섹션 제목(heading)은 그날의 메시지다
- 추상적 라벨 금지. 그날 장을 한 줄로 요약한 한글 메시지를 제목으로.
- 좋은 예: "중국 지준율 인하에 강세 확대" / "헬스케어 숨고르고 민감주 달리고" / "외국인 매도에 지수 급락"
- 나쁜 예: "Market Summary" / "지수 동향" / "섹터 리뷰" (추상적·영어)

### 2. 인과 연결 서술 (간밤 글로벌 → 국내 반응)
- "인민은행이 지준율 50bp 인하 및 1조 위안 유동성 공급을 발표하면서 Shanghai(+3.6%)·HSCEI(+4.5%) 등 중화권 증시가 강세를 보였고, 이는 국내에도 우호적으로 작용하며 보합권의 KOSPI가 상승 탄력을 받았습니다."
- 숫자 나열이 아니라 '무엇이 왜 움직였고 그게 국내에 어떻게 전이됐는지'를 문장으로.

### 3. 종목은 반드시 "종목명(±등락%, 괄호 안 사유)" 형식 (★시그니처)
- "유한양행(+5.9%, 렉라자 FDA 허가)·바이넥스(+2.9%, 174억원 CMO 계약 체결)"
- "삼성전자(-2.5%, 외국인 순매도)·SK하이닉스(-2.6%, HBM 경쟁 우려)"
- 제공된 상승/하락 TOP 종목과 뉴스 헤드라인을 연결해 '사유'를 괄호 안에 추정·명시. 사유 없으면 수급·섹터 맥락으로.

### 4. #특징업종 태그 (feature_tags, bullets — 마감 시황 시그니처)
- 각 항목: "테마명: 배경 한 줄(대표종목+등락%)" 형식
- 예: "교육: AI 디지털교과서 도입 기대(웅진씽크빅 +8.7%, 아이스크림미디어 +1.5%)"
- 예: "경영권 분쟁: 고려아연(-3.3%)·영풍(-11.7%) 분쟁 격화"
- 3~4개. 제공된 무버·뉴스에서 테마를 묶어낼 것.

### 5. 담백한 존댓말 종결
- "~했습니다 / ~보였습니다 / ~연출했습니다 / ~나타났습니다"
- 과장 금지: 폭락/패닉/반등 확실/명확히 바닥 금지.

### 6. 깊이 규칙 (★레퍼런스 격차 해소 — 반드시)
- (순환매) sector_flow에서 강세 1섹터·약세 1섹터를 반드시 대비시켜 "돈이 어디서 어디로 갔는가"(순환매 방향)를 한 문장으로 규정. 강세·약세 각 최소 2종목.
- (사유 4범주) 종목 괄호 사유는 [수급 / 뉴스 / 실적 / 정책] 중 하나로 명시. 사유 불명이면 섹터·수급 맥락으로 추정하되 범주를 드러낼 것.
- (교차일치) 본문에 인용하는 KOSPI/KOSDAQ 종가·외국인/기관 수급(억원)·원달러는 제공 데이터와 정확히 일치(임의 수치 생성 금지).
- (선제 인과) event_outlook은 ①오늘 핵심 이벤트의 시장 반응 → ②내일 관전포인트(일정+관찰레벨)를 연결하되, ①이 ②에 주는 선제 함의를 1단계 이상 연결(예: 외국인 5거래일 연속 순매도 → 내일 옵션만기 수급 부담).
- (테마성) #특징업종은 단발 종목이 아니라 '테마로 묶인 2종목 이상'.
- (어미 다양성) 존댓말 종결어미 4종 이상 로테이션, 동일 어미 연속 2회 금지. 숫자 없는 상투 문장 금지.

## 블록별 작성 기준
- title: 20~26자, '주어+동사' 메시지. 명사 나열·영어 금지. 예: "외국인 매도에 지수 급락, 방어주만 선방"
- headline: 1문장. 지수 등락 + 주도 수급/섹터.
- index_wrap: heading(지수 메시지) + 간밤 글로벌→국내 인과로 지수 총평 3~4문장. 종가·수급 수치는 레일과 교차일치.
- sector_flow: heading(섹터 메시지) + 강세 섹터(2종목±%,사유)·약세 섹터(2종목±%,사유) 대비 + 순환매 방향 1문장 명시. 스타일(방어/성장/경기민감/금리민감) 관점 1회.
- feature_tags(bullets 3~4): "테마: 배경(대표종목+%, 2종목 이상)" 형식. 테마로 묶일 것.
- event_outlook: heading + ①오늘 핵심 이벤트 반응 ②내일 관전(일정·레벨), ①→② 선제 인과 1단계.
- takeaway: 운용 시사점 1문장(존댓말 아닌 단정 운용판단). 본문에서 도출된 변수만으로 귀결 — 일반론·면피성 금지. 예: "현 구간에서는 낙폭과대 매수보다 변동성 관리가 우선이며, 외국인 매도 축소가 확인되기 전까지 현금성 여력 유지가 합리적이다."
{_COMMON_RULES}
blocks(이 순서·id 고정):
{_blocks_contract('close')}
"""

PROMPT_INTRADAY_MORNING = f"""당신은 한화손보 운용본부의 '아침시황' 작성자입니다. KOSPI·KOSDAQ 각 시장의 장중 흐름과 그날의 주도 섹터/테마를 실무 브리핑 톤으로 깊이 있게 설명합니다.

## 아침시황 DNA (반드시 체화)

### 1. 주도주 스토리 — '왜 그 테마가 움직이는가'
- 단순 등락 나열 금지. 제공된 '주도 테마 등락률'·'RS 동향'·'상승/하락 TOP 종목' 데이터를 연결해 그날을 끌어가는 테마를 거명하고 촉매·수급으로 설명.
- 대표 종목을 등락률과 함께 인용: "조선(+3.8%, HD현대중공업 카타르 수주 기대), 방산(+2.1%)이 강세를 주도했다."

### 2. 섹터 로테이션·RS로 순환매 방향 규정
- sector_rs: RS 4분면(리더/단기반등/숨고르기/약세지속)을 활용해 '돈이 어디서 어디로 가는가'를 강세·약세 대비로 명시.

### 3. KOSPI·KOSDAQ 분리 서술
- kospi_theme / kosdaq_theme를 각각 그 시장 고유의 주도 테마로. KOSDAQ은 중소형·기술주 색채를 반영.

### 4. 수급·시장폭 해석
- breadth_flow: 등락 종목수 + 외국인/기관 수급(억원)을 해석. 상승종목 vs 하락종목 분포로 시장 내부 강도 진단.

### 5. 실무 브리핑 톤
- 운용역이 장중 빠르게 읽는 톤. 담백하고 정보 밀도 높게. 종목·수치 근거 필수, 상투어 금지.
{_COMMON_RULES}
blocks(이 순서·id 고정):
{_blocks_contract('intraday')}
"""

_SLOT_SYSTEM = {
    "premarket": PROMPT_PREMARKET_HANJIYOUNG,
    "close":     PROMPT_CLOSE_KANGJINHYUK,
    "intraday":  PROMPT_INTRADAY_MORNING,
}


# ── 슬롯별 사용자 프롬프트 ─────────────────────────────────────────────────
def _build_premarket_prompt(data: dict) -> str:
    """장전(07:00): 미국 마감 데이터 기반 국내 장 시작 전 분석."""
    us = data.get("us_indices", {})
    rates = data.get("rates", {})
    sent = data.get("sentiment", {})
    events = data.get("events", [])
    kr = data.get("kr_indices", {}) or {}
    kospi = kr.get("kospi", {}) or {}
    kosdaq = kr.get("kosdaq", {}) or {}

    us_lines = "\n".join(
        f"- {k}: {v.get('close', 'N/A'):,} ({v.get('change_str', 'N/A')})"
        for k, v in us.items()
    ) if us else "- 데이터 없음"

    def _mv(m):
        nm = m.get("name", "")
        ch = m.get("change_str")
        if not ch and m.get("change") is not None:
            try:
                ch = f"{float(m.get('change')):+.2f}%"
            except Exception:
                ch = ""
        rs = m.get("reason") or m.get("note") or m.get("theme") or ""
        return f"- {nm}: {ch}" + (f" — {rs}" if rs else "")
    mover_lines = "\n".join(_mv(m) for m in (data.get("us_movers") or [])[:8]) or "- 데이터 없음"
    us_narr = (data.get("us_narrative") or "").strip()
    narr_section = (f"## 간밤 시장 내러티브(참고 — 핵심 스토리 단서)\n{us_narr}\n\n" if us_narr else "")

    rot = data.get("sector_rotation", {}) or {}

    def _rot_line(lst, n=6):
        top = " · ".join(f"{x['sector']} {x['return']:+.1f}%" for x in lst[:n])
        bot = " · ".join(f"{x['sector']} {x['return']:+.1f}%" for x in lst[-3:])
        return f"- 주도: {top}\n- 부진: {bot}"
    rot_section = ""
    if rot.get("20d") or rot.get("5d"):
        rot_section = "## 업종 로테이션 (KOSPI 상세업종 시총가중 수익률)\n"
        if rot.get("20d"):
            rot_section += "### 최근 20거래일\n" + _rot_line(rot["20d"]) + "\n"
        if rot.get("5d"):
            rot_section += "### 최근 5거래일\n" + _rot_line(rot["5d"]) + "\n"
        rot_section += "\n"

    evt_lines = "\n".join(f"- {e}" for e in events[:5]) if events else "- 없음"

    # 국내 지수 직전 종가 — grounding 의 핵심. 이게 없으면 LLM 이 학습된 통념(예: 3,100선)으로
    # 코스피 레벨을 지어낸다. 제공되면 지수 섹션 + 앵커링 경고를 함께 주입한다.
    def _kr_val(d):
        v = d.get("index", d.get("close", d.get("value")))
        try:
            return float(v) if v is not None else None
        except Exception:
            return None
    kp, kq = _kr_val(kospi), _kr_val(kosdaq)
    kr_section, ground_rule = "", ""
    if kp:
        kchg = kospi.get("change", kospi.get("chg_pct"))
        qchg = kosdaq.get("change", kosdaq.get("chg_pct"))
        kr_section = "## 국내 증시 (직전 거래일 종가)\n" + \
            f"- KOSPI: {kp:,.2f}" + (f" ({float(kchg):+.2f}%)" if kchg is not None else "") + "\n"
        if kq:
            kr_section += f"- KOSDAQ: {kq:,.2f}" + (f" ({float(qchg):+.2f}%)" if qchg is not None else "") + "\n"
        ground_rule = (f"\n⚠️ 지수 레벨 grounding(엄수): 현재 KOSPI 수준은 약 {kp:,.0f}pt다. 본문의 모든 "
                       f"지지·저항·목표·'탈환/돌파/재돌파' 레벨은 반드시 이 수치 부근(±수%)에서만 사용할 것. "
                       f"학습된 과거 통념(3,100선·2,700선 등 현재와 동떨어진 라운드넘버)을 절대 인용 금지.")

    return f"""[장전 시황 분석 요청 — 미국 마감 기준]
분석 날짜: {data.get('date', '—')}

## 미국 증시 (전일 마감)
{us_lines}

## 미국 개별주 무버 (오늘 스토리의 핵심 재료 — 인라인 등락률로 본문에 박을 것)
{mover_lines}

## 금리 & 환율
- 미 10년물 국채 금리: {rates.get('us10y', 'N/A')}%
- 달러인덱스 (DXY): {rates.get('dxy', 'N/A')}
- 원/달러: {rates.get('usdkrw', 'N/A')}원

## 심리 지표
- VIX: {sent.get('vix', 'N/A')}
- Fear & Greed Index: {sent.get('fear_greed', 'N/A')} / 100 ({sent.get('fear_greed_label', 'N/A')})

{kr_section}{narr_section}{rot_section}## 오늘 주요 이벤트
{evt_lines}
{ground_rule}
---
[작성 지시 — 가장 중요]
1. 숫자 나열 금지. 먼저 **오늘 장을 관통하는 메인 내러티브(핵심 스토리) 1~3개**를 규정하라. 위 데이터에서
   가장 큰 움직임·재료를 골라(예: 특정 개별주 급등, 특정 섹터 랠리, 지정학/정책 이벤트) "무엇이 왜
   움직였고 그게 오늘 국내장에 어떤 의미인가"를 인과로 풀 것.
2. 미국 개별주 무버는 단순 등락이 아니라 그 **배경/테마**(IPO 흥행, 메모리/AI 수요, 휴전 등)와 연결해
   국내 연관 업종(반도체·메모리·방산·에너지 등)으로 착지시킬 것.
3. **업종 로테이션** 데이터가 있으면 sector_strategy 에서 "최근 어느 업종이 이끌고 어디로 순환매가
   도는가(키맞추기)"를 실제 수치(20일/5일 상위·하위 업종 %)로 규정하고, 대응 전략을 제시할 것.
4. 지수·종목·매크로·업종수익률은 위 제공 수치만 사용(임의 생성·학습통념 금지).
JSON 형식으로만 출력해 주세요."""


def _investor_lines(inv: dict) -> str:
    """투자자 수급 블록. 장중 집계 전(전부 0)이면 0을 주입하지 않고 '미제공' 명시 —
    LLM이 '수급 0억원'을 어색하게 해석·변명하는 문장을 차단한다."""
    vals = {k: int(inv.get(k, 0) or 0) for k in ("individual", "foreign", "institution")}
    if not any(vals.values()):
        return "- 미제공(장중 집계 전) — 수급 수치를 지어내지 말고, 수급 언급이 필요하면 '미확인'으로 서술할 것"
    return (f"- 개인:   {vals['individual']:+,}\n"
            f"- 외국인: {vals['foreign']:+,}\n"
            f"- 기관:   {vals['institution']:+,}")


def _build_intraday_prompt(data: dict) -> str:
    """장중(08:30): 장 개장 직후 흐름 분석."""
    kr = data.get("kr_indices", {})
    kospi = kr.get("kospi", {})
    kosdaq = kr.get("kosdaq", {})
    inv = data.get("investor", {})
    sectors = data.get("sectors", [])
    news = data.get("news", [])
    us = data.get("us_indices", {})
    sent = data.get("sentiment", {})

    def _idx_line(name: str, d: dict) -> str:
        idx = d.get("index", d.get("close", 0))
        chg = d.get("change", d.get("chg_pct", 0))
        return f"- {name}: {idx:,.2f} ({float(chg):+.2f}%)"

    kosdaq_sectors = data.get("kosdaq_sectors", [])
    themes = data.get("theme_returns", [])
    kq_themes = data.get("kosdaq_theme_returns", [])
    rs_kospi = data.get("rs_kospi", [])
    gainers = data.get("top_gainers", [])
    losers = data.get("top_losers", [])
    top_contrib = data.get("top_contributors", [])
    bottom_contrib = data.get("bottom_contributors", [])
    breadth = data.get("breadth", {})

    def _sec_lines(lst, n=8):
        return "\n".join(f"- {s.get('sector','')}: {float(s.get('change',0)):+.2f}%" for s in lst[:n]) if lst else "- 데이터 없음"
    def _theme_lines(lst, n=6):
        out = []
        for t in (lst or [])[:n]:
            nm = t.get('theme', t.get('name', ''))
            ch = float(t.get('change', t.get('return', 0)) or 0)
            out.append(f"- {nm}: {ch:+.2f}%")
        return "\n".join(out) if out else "- 데이터 없음"
    def _mover_lines(lst, n=6):
        out = []
        for m in (lst or [])[:n]:
            out.append(f"- {m.get('name','')}: {float(m.get('change',0)):+.2f}%")
        return "\n".join(out) if out else "- 데이터 없음"
    def _rs_lines(lst, n=8):
        out = []
        for r in (lst or [])[:n]:
            out.append(f"- {r.get('sector','')}: RS {float(r.get('rs_1d',0)):.0f} / {r.get('quadrant','')}")
        return "\n".join(out) if out else "- 데이터 없음"
    def _contrib_lines(lst, n=6):
        out = []
        for c in (lst or [])[:n]:
            cp = float(c.get('contribution', 0) or 0)
            ch = float(c.get('change', 0) or 0)
            out.append(f"- {c.get('name','')}: {cp:+.2f}pt (등락 {ch:+.2f}%)")
        return "\n".join(out) if out else "- 데이터 없음"

    sec_lines = _sec_lines(sectors)
    news_lines = "\n".join(f"- {n.get('title',n) if isinstance(n,dict) else n}" for n in news[:5]) if news else "- 없음"
    us_lines = "\n".join(f"- {k}: ({v.get('change_str','N/A')})" for k,v in us.items()) if us else "- 데이터 없음"

    return f"""[장중 시황 분석 요청 — 장 개장 직후]
분석 날짜: {data.get('date','—')}  /  분석 시각: {data.get('time','08:30')}

## 국내 지수 (장중 현재)
{_idx_line('KOSPI', kospi)}
{_idx_line('KOSDAQ', kosdaq)}

## 투자자 수급 (KOSPI 누적, 억원)
{_investor_lines(inv)}

## 시장 폭 (등락 종목수)
- 상승: {breadth.get('up','N/A')} / 하락: {breadth.get('down','N/A')}

## KOSPI 섹터별 등락
{sec_lines}

## KOSDAQ 섹터별 등락
{_sec_lines(kosdaq_sectors)}

## 주도 테마 등락률 (KOSPI)
{_theme_lines(themes)}

## 주도 테마 등락률 (KOSDAQ)
{_theme_lines(kq_themes)}

## 섹터 상대강도(RS) 동향
{_rs_lines(rs_kospi)}

## 상승률 TOP 종목
{_mover_lines(gainers)}

## 하락률 TOP 종목
{_mover_lines(losers)}

## 지수 기여도 상위 (KOSPI 견인, 시총가중 내재화 산출)
{_contrib_lines(top_contrib)}

## 지수 기여도 하위 (KOSPI 압박)
{_contrib_lines(bottom_contrib)}

## 심리 지표
- VIX: {sent.get('vix','N/A')}
- Fear & Greed: {sent.get('fear_greed','N/A')} ({sent.get('fear_greed_label','N/A')})

## 전일 미국 마감
{us_lines}

## 주요 뉴스
{news_lines}

---
장중 분석 포인트(아침시황 톤 — 주도주 스토리 중심):
- kospi_theme / kosdaq_theme: 각 시장의 주도 테마를 거명하고 '왜 그 테마가 움직이는가'(촉매·수급)를 위 테마/RS/무버 데이터로 연결. 대표 종목을 등락률과 함께 인용. 특히 지수 기여도 상위 종목(예: 'SK하이닉스가 지수를 +N포인트 견인')을 포인트 단위로 명시해 지수 변동의 주범을 설명.
- sector_rs: 섹터·RS 동향을 강세/약세 대비로(순환매 방향) 불릿. RS 원점수("RS 6")를 그대로 인용하지 말고 반드시 4분면 라벨(리더/단기반등/숨고르기/약세지속)로 서술할 것. 예: "반도체 장비: 리더 그룹 유지, 자금 유입 지속".
- breadth_flow: 등락 종목수·외국인/기관 수급을 해석. 수급이 '미제공'이면 그 항목은 만들지 말 것.
- headlines: 위 '주요 뉴스' 목록에서만 선별해 시장 영향(테마·섹터 연결)을 한 줄씩 덧붙일 것. 본문(지수·테마 서술)의 요약 재나열 금지. 뉴스가 '없음'이면 "특이 뉴스 부재" 한 줄만.
- 데이터로 확인되지 않는 수치 지어내기 금지.
JSON 형식으로만 출력해 주세요."""


def _build_close_prompt(data: dict) -> str:
    """장마감(16:30): 최종 종가 기준 총평 및 내일 선제 분석."""
    kr = data.get("kr_indices", {})
    kospi = kr.get("kospi", {})
    kosdaq = kr.get("kosdaq", {})
    inv = data.get("investor", {})
    sectors = data.get("sectors", data.get("sector_returns", []))
    breadth = data.get("breadth", {})
    events_tmr = data.get("events_tomorrow", [])
    us_fut = data.get("us_futures", {})
    sent = data.get("sentiment", {})

    sec_lines = "\n".join(
        f"- {s.get('sector','')}: {float(s.get('change',0)):+.2f}%"
        for s in sectors[:8]
    ) if sectors else "- 데이터 없음"

    tmr_lines = "\n".join(f"- {e}" for e in events_tmr[:4]) if events_tmr else "- 없음"
    fut_lines = "\n".join(f"- {k}: {v}" for k,v in us_fut.items()) if us_fut else "- 데이터 없음"

    kospi_close = kospi.get("close", 0)
    kospi_chg = kospi.get("chg_pct", kospi.get("change", 0))
    kosdaq_close = kosdaq.get("close", 0)
    kosdaq_chg = kosdaq.get("chg_pct", kosdaq.get("change", 0))

    # 주요 종목 TOP 무버
    movers_raw = data.get("top_movers", {})
    gainers = movers_raw.get("gainers", [])
    losers  = movers_raw.get("losers", [])
    gainer_lines = "\n".join(f"- {m['name']}: {m['change']:+.2f}% ({m['close']:,}원)" for m in gainers[:5]) or "- 데이터 없음"
    loser_lines  = "\n".join(f"- {m['name']}: {m['change']:+.2f}% ({m['close']:,}원)" for m in losers[:5]) or "- 데이터 없음"

    # 뉴스 헤드라인
    news_list = data.get("news", [])
    news_lines = "\n".join(f"- {n}" for n in news_list[:6]) if news_list else "- 없음"

    return f"""[장마감 시황 분석 요청 — 15:30 종가 기준]
분석 날짜: {data.get('date','—')}

## 국내 지수 (최종 종가)
- KOSPI:  {float(kospi_close):,.2f} ({float(kospi_chg):+.2f}%)
- KOSDAQ: {float(kosdaq_close):,.2f} ({float(kosdaq_chg):+.2f}%)

## 투자자 수급 (KOSPI 최종, 억원)
- 개인:   {int(inv.get('individual',0)):+,}
- 외국인: {int(inv.get('foreign',0)):+,}
- 기관:   {int(inv.get('institution',0)):+,}

## 시장 폭 (KOSPI)
- 상승: {breadth.get('up','N/A')}종목 / 하락: {breadth.get('down','N/A')}종목

## 섹터 등락
{sec_lines}

## 심리 지표
- VKOSPI(종가): {sent.get('vkospi','N/A')}
- VIX: {sent.get('vix','N/A')}
- Fear & Greed: {sent.get('fear_greed','N/A')} ({sent.get('fear_greed_label','N/A')})
- 원/달러: {sent.get('usdkrw','N/A')}원

## 미국 선물 (장후)
{fut_lines}

## 내일 주요 일정
{tmr_lines}

## 상승 TOP 5 (KOSPI 시가총액 상위 기준)
{gainer_lines}

## 하락 TOP 5
{loser_lines}

## 당일 주요 뉴스
{news_lines}

---
장마감 분석 포인트: 오늘 장 총평, 수급·섹터 해석, 오늘 결과가 내일 시장에 미치는 선제적 함의.
JSON 형식으로만 출력해 주세요."""


# ── JSON 파싱 ─────────────────────────────────────────────────────────────
_REQUIRED = {"title", "stance", "key_issue", "bull_case", "bear_case",
             "macro_flow", "kr_outlook", "strategy", "news_flow"}
_VALID_STANCES = {"RISK-ON", "NEUTRAL", "RISK-OFF"}


def _to_float(value: Any) -> float | None:
    """콤마·문자열이 섞인 숫자를 float로 변환."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    cleaned = re.sub(r"[^0-9.+-]", "", str(value))
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _get_kospi_level(market_data: dict[str, Any]) -> float | None:
    """market_data에서 현재 또는 기준 KOSPI 레벨 추출."""
    kospi = (market_data.get("kr_indices") or {}).get("kospi") or {}
    for key in ("close", "index", "value", "level"):
        level = _to_float(kospi.get(key))
        if level and level > 0:
            return level
    return None


def _fmt_index_level(value: float) -> str:
    """지수 목표 레벨은 10pt 단위로 둥글려 표기."""
    rounded = int(round(value / 10.0) * 10)
    return f"{rounded:,}"


def _upside_range(kospi_level: float) -> str:
    """Bull 시나리오용 현재 지수 상단 돌파 구간."""
    return f"{_fmt_index_level(kospi_level * 1.01)}~{_fmt_index_level(kospi_level * 1.02)}"


def _downside_range(kospi_level: float) -> str:
    """Bear 시나리오용 현재 지수 하단 테스트 구간."""
    return f"{_fmt_index_level(kospi_level * 0.98)}~{_fmt_index_level(kospi_level * 0.97)}"


def _sanitize_breakout_levels(text: str, kospi_level: float | None) -> str:
    """
    현재 KOSPI보다 낮은 레벨을 '돌파/재돌파/탈환'으로 쓰는 오류를 보정.

    예: 현재 8,800대인데 '7,950~8,000선 재돌파' → '8,890~8,980선 재돌파'
    """
    if not text or not kospi_level:
        return text

    level_token = r"\d{1,2},?\d{3}(?:\.\d+)?"
    trigger_token = r"(?:재돌파|돌파|탈환|상향\s*돌파)"
    range_re = re.compile(
        rf"(?P<a>{level_token})\s*(?:~|-|–|—)\s*(?P<b>{level_token})(?P<suffix>\s*선)?(?P<tail>[^.\n]{{0,16}}?{trigger_token})"
    )
    single_re = re.compile(
        rf"(?P<a>{level_token})(?P<suffix>\s*선)?(?P<tail>[^.\n]{{0,16}}?{trigger_token})"
    )

    def parse_num(s: str) -> float:
        return float(s.replace(",", ""))

    def repl_range(match: re.Match[str]) -> str:
        a = parse_num(match.group("a"))
        b = parse_num(match.group("b"))
        if max(a, b) < kospi_level * 0.99:
            return f"{_upside_range(kospi_level)}{match.group('suffix') or '선'}{match.group('tail')}"
        return match.group(0)

    def repl_single(match: re.Match[str]) -> str:
        a = parse_num(match.group("a"))
        if a < kospi_level * 0.99:
            return f"{_fmt_index_level(kospi_level * 1.01)}{match.group('suffix') or '선'}{match.group('tail')}"
        return match.group(0)

    return single_re.sub(repl_single, range_re.sub(repl_range, text))


def _ensure_bullets(text: str, max_items: int = 3) -> str:
    """문단형 텍스트를 렌더러가 불릿으로 표시할 수 있게 정규화."""
    if not text:
        return "—"
    lines = [ln.strip() for ln in str(text).splitlines() if ln.strip()]
    if len(lines) <= 1:
        # 마침표 기준으로 3개까지 쪼갬. 숫자 소수점은 보존하기 위해 문장 끝 공백 기준만 사용.
        parts = re.split(r"(?<=[가-힣A-Za-z0-9%원임함됨음])\.\s+", str(text).strip())
        lines = [p.strip().rstrip(".") + ("." if not p.strip().endswith(".") else "") for p in parts if p.strip()]
    normalized = []
    for line in lines[:max_items]:
        line = re.sub(r"^[•·-]\s*", "", line).strip()
        normalized.append(f"- {line}")
    return "\n".join(normalized) if normalized else "—"


def _ensure_labeled_bullets(text: str, labels: list[str]) -> str:
    """지정 라벨 순서의 불릿으로 보정."""
    base = _ensure_bullets(text, len(labels))
    lines = [re.sub(r"^[•·-]\s*", "", ln).strip() for ln in base.splitlines() if ln.strip()]
    if not lines:
        lines = ["—"] * len(labels)
    while len(lines) < len(labels):
        lines.append(lines[-1])

    fixed: list[str] = []
    for label, line in zip(labels, lines[: len(labels)]):
        line = re.sub(r"^(팩트|판단|액션|트리거|레벨|모니터링)\s*[:：]\s*", "", line).strip()
        fixed.append(f"- {label}: {line}")
    return "\n".join(fixed)


def _split_sentences(text: str) -> list[str]:
    """한국어 리포트 문장을 문장 단위로 완만하게 분리."""
    lines: list[str] = []
    for raw in str(text or "").splitlines():
        raw = re.sub(r"^[•·-]\s*", "", raw).strip()
        if not raw:
            continue
        lines.extend([p.strip() for p in re.split(r"(?<=[임함됨음봄임])\.\s+", raw) if p.strip()])
    return [ln if ln.endswith(".") else f"{ln}." for ln in lines]


def _scenario_monitoring(text: str, kind: str) -> str:
    if "외국인" in text:
        side = "순매수" if kind == "bull" else "순매도"
        return f"외국인 KOSPI 현물 {side} 금액과 선물 포지션 변화가 핵심 변수임."
    if "환율" in text or "원/달러" in text:
        return "원/달러 환율과 외국인 현물 수급 동조 여부가 핵심 변수임."
    return "KOSPI 현물 수급과 주도업종 상대강도 변화가 핵심 변수임."


def _structure_scenario(text: str, kind: str, kospi_level: float | None) -> str:
    """Bull/Bear 시나리오를 트리거·레벨·모니터링 3줄로 전문화."""
    labels = ["트리거", "레벨", "모니터링"]
    text = str(text or "").strip()
    if all(re.search(rf"(^|\n)\s*[-•·]?\s*{label}\s*[:：]", text) for label in labels):
        return _ensure_labeled_bullets(text, labels)

    sentences = _split_sentences(text)
    trigger = sentences[0] if sentences else (
        "주도업종 확산과 외국인 현물 수급 개선이 확인될 경우임."
        if kind == "bull"
        else "외국인 현물 매도와 환율 상승이 동시에 진행될 경우임."
    )
    level = next((s for s in sentences if re.search(r"KOSPI|\d{1,2},?\d{3}", s)), "")
    fallback_level = "KOSPI 단기 지지·저항 레벨 확인 필요함."
    if kospi_level:
        if kind == "bull":
            fallback_level = f"KOSPI {_upside_range(kospi_level)}선 재돌파·안착 여부가 1차 저항 확인 구간임."
        else:
            fallback_level = f"KOSPI {_downside_range(kospi_level)}선 지지 여부가 1차 방어선 확인 구간임."
        if not level:
            level = fallback_level
        else:
            level = _sanitize_breakout_levels(level, kospi_level)
    elif not level:
        level = fallback_level

    # 트리거 문장 자체가 레벨 문장까지 겸하면 레벨 줄은 별도 판단 문장으로 분리.
    if level == trigger:
        level = fallback_level
    trigger = re.sub(r"\s*KOSPI\s*\d{1,2},?\d{3}(?:\.\d+)?\s*(?:~|-|–|—)\s*\d{1,2},?\d{3}(?:\.\d+)?선?\s*(?:재돌파|돌파|탈환|안착)?\s*가능함\.?", "", trigger).strip()
    if not trigger.endswith("."):
        trigger += "."

    monitoring = next((s for s in sentences if "모니터" in s or "변수" in s), "")
    if not monitoring:
        monitoring = _scenario_monitoring(text, kind)

    trigger = re.sub(r"^(트리거)\s*[:：]\s*", "", trigger).strip()
    level = re.sub(r"^(레벨)\s*[:：]\s*", "", level).strip()
    monitoring = re.sub(r"^(모니터링|변수)\s*[:：]\s*", "", monitoring).strip()

    return "\n".join([
        f"- 트리거: {trigger}",
        f"- 레벨: {level}",
        f"- 모니터링: {monitoring}",
    ])


def _market_change_text(market_data: dict[str, Any]) -> str:
    kospi = (market_data.get("kr_indices") or {}).get("kospi") or {}
    chg = _to_float(kospi.get("chg_pct", kospi.get("change")))
    if chg is None:
        return "KOSPI 방향성 확인"
    return f"KOSPI {chg:+.2f}%"


def _leading_sector(market_data: dict[str, Any]) -> str:
    sectors = market_data.get("sectors") or market_data.get("sector_returns") or []
    if not sectors:
        return "수급"
    best = max(sectors, key=lambda x: _to_float(x.get("change")) or -999)
    name = str(best.get("sector") or "주도업종").strip()
    chg = _to_float(best.get("change"))
    return f"{name} {chg:+.2f}%" if chg is not None else name


def _fallback_title(market_data: dict[str, Any]) -> str:
    inv = market_data.get("investor") or {}
    foreign = _to_float(inv.get("foreign"))
    flow = f"외국인 {foreign:+,.0f}억" if foreign is not None else "수급 확인"
    return f"{_leading_sector(market_data)}·{_market_change_text(market_data)}·{flow}"


def _postprocess_sections(result: dict[str, Any], market_data: dict[str, Any]) -> dict[str, Any]:
    """LLM 산출물의 브랜드·형식·지수 레벨 오류를 렌더 전 보정."""
    result = dict(result)
    kospi_level = _get_kospi_level(market_data)

    for key, value in list(result.items()):
        if isinstance(value, str):
            value = value.replace("한화생명보험", "한화손해보험").replace("한화생명", "한화손해보험")
            result[key] = _sanitize_breakout_levels(value, kospi_level)

    title = str(result.get("title") or "").strip()
    if len(title) < 8 or title in {"오늘 장 본질", "시장 방향성", "분석 준비 중", "시황 점검"} or "·" not in title:
        result["title"] = _fallback_title(market_data)

    result["key_issue"] = _ensure_labeled_bullets(
        str(result.get("key_issue", "")),
        ["팩트", "판단", "액션"],
    )

    if kospi_level:
        bull = str(result.get("bull_case", "") or "")
        if not re.search(r"\d{1,2},?\d{3}", bull):
            result["bull_case"] = (
                f"{bull.rstrip()} KOSPI 상단은 {_upside_range(kospi_level)}선 재돌파 여부가 관건임. "
                "모니터링 변수는 외국인 KOSPI 현물 순매수 금액임."
            ).strip()
        result["bull_case"] = _structure_scenario(str(result.get("bull_case", "")), "bull", kospi_level)
        bear = str(result.get("bear_case", "") or "")
        if not re.search(r"\d{1,2},?\d{3}", bear):
            result["bear_case"] = (
                f"{bear.rstrip()} KOSPI 하단은 {_downside_range(kospi_level)}선 지지 여부가 관건임. "
                "모니터링 변수는 외국인 KOSPI 현물 순매도 금액임."
            ).strip()
        result["bear_case"] = _structure_scenario(str(result.get("bear_case", "")), "bear", kospi_level)

    return result


def _parse_sections(raw: str) -> dict[str, Any]:
    """Claude 응답에서 JSON 섹션 딕셔너리 추출 및 검증."""
    # JSON 블록만 추출
    m = re.search(r'\{[\s\S]*\}', raw)
    if m:
        raw = m.group(0)
    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        print(f"[WARN] JSON 파싱 실패. 원본 앞 200자: {raw[:200]}")
        return _fallback_sections()

    # 필수 키 보완
    for k in _REQUIRED:
        if k not in result:
            result[k] = "—"
    # stance 검증
    if result.get("stance") not in _VALID_STANCES:
        result["stance"] = "NEUTRAL"
    return result


def _fallback_sections(reason: str = "") -> dict[str, Any]:
    msg = f"시황 분석 데이터를 처리하는 중 오류가 발생했습니다.{' (' + reason + ')' if reason else ''}"
    return {
        "title": "분석 준비 중",
        "stance": "NEUTRAL",
        "key_issue": msg,
        "bull_case": "—",
        "bear_case": "—",
        "macro_flow": "—",
        "kr_outlook": "—",
        "strategy": "—",
        "news_flow": "—",
    }


# ── Codex CLI (OAuth) 호출 경로 ───────────────────────────────────────────
def _call_via_codex(user_prompt: str, system: str = SYSTEM_PROMPT) -> str:
    """
    Codex CLI OAuth 경로로 텍스트 생성.
    ANTHROPIC_API_KEY 없이 `codex exec -` subprocess로 동일한 결과 생성.

    Returns
    -------
    str  Codex 출력 텍스트 (성공) 또는 빈 문자열 (실패)
    """
    # system prompt + user prompt 합성 (Codex는 single-turn)
    full_prompt = f"{system}\n\n---\n\n{user_prompt}"

    tmp = tempfile.NamedTemporaryFile(
        suffix=".txt", delete=False, mode="w", encoding="utf-8"
    )
    tmp.close()
    tmp_path = tmp.name

    cmd = [
        "codex", "exec", "-",
        "--dangerously-bypass-approvals-and-sandbox",
        "--skip-git-repo-check",
        "-o", tmp_path,
    ]

    try:
        result = subprocess.run(
            cmd,
            input=full_prompt,
            shell=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            timeout=120,
        )
        if result.returncode == 0 and os.path.exists(tmp_path):
            with open(tmp_path, "r", encoding="utf-8") as f:
                return f.read().strip()
        else:
            print(f"[WARN] Codex CLI 오류: rc={result.returncode} / {result.stderr[:120]}")
            return ""
    except FileNotFoundError:
        print("[WARN] Codex CLI를 찾을 수 없습니다. `npm i -g @openai/codex` 또는 OAuth 로그인 확인")
        return ""
    except subprocess.TimeoutExpired:
        print("[WARN] Codex CLI 타임아웃 (120s)")
        return ""
    except Exception as exc:
        print(f"[WARN] Codex 호출 오류: {exc}")
        return ""
    finally:
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except OSError:
            pass


import report_schema as _schema


def _extract_json(raw: str) -> dict | None:
    """LLM(특히 MiMo) 응답에서 JSON 객체 추출. 마크다운 펜스/문자열 내 raw 제어문자 등
    비표준 출력을 관대하게 보정해 재시도(비결정적 LLM 안정화)."""
    import json, re
    if not raw:
        return None
    text = raw.strip()
    # ```json … ``` 펜스 제거
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text).strip()
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        return None
    block = m.group(0)
    # 1차: 그대로
    try:
        return json.loads(block)
    except Exception:
        pass
    # 2차: strict=False 로 문자열 내 제어문자 허용
    try:
        return json.loads(block, strict=False)
    except Exception:
        pass
    # 3차: 흔한 오류 보정(트레일링 콤마 제거)
    try:
        repaired = re.sub(r",\s*([}\]])", r"\1", block)
        return json.loads(repaired, strict=False)
    except Exception:
        return None


def _is_korean_envelope(parsed: dict) -> bool:
    """title+headline 에 한글이 있고 한자(중국어) 비중이 과하지 않으면 한국어로 간주.
    MiMo(샤오미)가 가끔 중국어로 답하는 것을 차단."""
    import re
    text = f"{parsed.get('title','')} {parsed.get('headline','')}"
    if not text.strip():
        return True  # 빈 응답은 다른 검증/폴백에 위임
    hangul = len(re.findall(r"[가-힣]", text))
    hanzi = len(re.findall(r"[一-鿿]", text))
    # 한글이 전혀 없으면(=중국어/영어 위주) 거부. 한자가 한글보다 많아도 거부.
    if hangul == 0:
        return False
    return hanzi <= hangul


_PLACEHOLDER_TITLES = {"주도변수·시장반응·판단", "주도 변수·시장 반응·투자 판단", "주도·반응·판단"}


_HANZI_RE = __import__('re').compile(r'[一-鿿㐀-䶿豈-﫿]+')
# 슬롯별 블록 글자 수 상한 — close는 종목 분석을 위해 더 넉넉하게
_PARA_MAX_CHARS: dict[str, int] = {
    "premarket": 340,   # 장전 시황 톱다운 서술 + 페이지 채움
    "intraday":  260,   # 아침시황 주도주 스토리 서술 위해 상향
    "close":     460,   # 마감 시황 재현 — 종목(±%,사유)+순환매 + 페이지 채움
}

def _strip_hanzi(text: str) -> str:
    """한자(중국어) 문자열 제거 — MiMo 중국어 혼입 방어."""
    return _HANZI_RE.sub('', text).strip()

def _cap_paragraph(text: str, max_chars: int) -> str:
    """문장 단위로 max_chars 이내로 잘라낸다.
    소수점(4.19%)을 문장 끝으로 오인하지 않도록 종결부호 뒤 '공백 필수(\\s+)'로 분리."""
    if len(text) <= max_chars:
        return text
    out, total = [], 0
    # 종결부호(.!?。) 뒤에 공백이 실제로 있을 때만 문장 경계로 본다 → 소수점 보호
    for sent in __import__('re').split(r'(?<=[.!?。])\s+', text):
        if not sent.strip():
            continue
        if total + len(sent) > max_chars and out:
            break
        out.append(sent)
        total += len(sent)
    return ' '.join(out) if out else text[:max_chars]

def _postprocess_envelope(env: dict, market_data: dict, slot: str = "premarket") -> dict:
    max_chars = _PARA_MAX_CHARS.get(slot, 220)
    kospi_level = _get_kospi_level(market_data)
    title = str(env.get("title", "")).strip()
    if title in _PLACEHOLDER_TITLES or title.startswith("<") or "예시" in title:
        env["title"] = _fallback_title(market_data)
    for b in env.get("blocks", []):
        # 동적 한글 제목(heading)도 한자 제거
        if b.get("heading"):
            b["heading"] = _strip_hanzi(str(b["heading"])).replace("한화생명", "한화손해보험")
        if b["type"] == "paragraph" and isinstance(b["body"], str):
            body = _strip_hanzi(b["body"])
            body = body.replace("한화생명보험", "한화손해보험").replace("한화생명", "한화손해보험")
            body = _sanitize_breakout_levels(body, kospi_level)
            b["body"] = _cap_paragraph(body, max_chars)
        elif b["type"] == "bullets":
            b["body"] = [_sanitize_breakout_levels(_strip_hanzi(str(x)), kospi_level) for x in b["body"]]
    return env


# ── MiMo (OpenAI 호환) 호출 — 시황 LLM 1순위 ──────────────────────────────
MIMO_BASE_URL = "https://api.xiaomimimo.com/v1"
MIMO_MODEL = "mimo-v2.5"
# 시황 리포트는 스케줄 생성(비대화형)이라 지연 부담이 적어 고성능 모델(pro)을 기본 사용.
MIMO_MODEL_PRO = "mimo-v2.5-pro"


def _call_via_mimo(system: str, user: str, temperature: float = 0.4) -> str:
    """MiMo (OpenAI 호환) chat.completions 호출. 키 없거나 실패 시 빈 문자열."""
    api_key = os.environ.get("MIMO_API_KEY", "").strip()
    if not api_key:
        return ""
    try:
        from openai import OpenAI

        base_url = os.environ.get("MIMO_BASE_URL", "").strip() or MIMO_BASE_URL
        _use_pro = os.environ.get("ATLAS_USE_PRO", "1").strip().lower() not in ("0", "false", "off", "no")
        model = os.environ.get("MIMO_MODEL", "").strip() or (MIMO_MODEL_PRO if _use_pro else MIMO_MODEL)
        client = OpenAI(api_key=api_key, base_url=base_url, timeout=120.0, max_retries=1)
        resp = client.chat.completions.create(
            model=model,
            max_tokens=4000,
            temperature=temperature,
            # MiMo reasoning 끄기 — 추론토큰이 4000 예산을 잡아먹어 섹션 JSON 이 잘리는 것을
            # 막는다(실측 reasoning_tokens=0). 기존 JSON 복구 로직은 그대로 유지.
            extra_body={"chat_template_kwargs": {"enable_thinking": False}},
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return resp.choices[0].message.content or ""
    except Exception as exc:
        print(f"[WARN] MiMo 호출 실패: {exc}")
        return ""


# ── 메인 생성 함수 ─────────────────────────────────────────────────────────
def generate_report_sections(slot: str, market_data: dict) -> dict[str, Any]:
    import datetime as _dt
    builders = {"premarket": _build_premarket_prompt,
                "intraday": _build_intraday_prompt, "close": _build_close_prompt}
    builder = builders.get(slot)
    if builder is None:
        raise ValueError(f"알 수 없는 슬롯: {slot!r}")
    user_prompt = builder(market_data)
    system = _SLOT_SYSTEM[slot]

    def _finish(raw_text, reason: str = "") -> dict:
        parsed = _extract_json(raw_text or "")
        if parsed is None:
            env = _schema.fallback_envelope(slot, reason or "json_parse_failed")
        else:
            env = _postprocess_envelope(_schema.normalize_envelope(slot, parsed), market_data, slot=slot)
        env["as_of"] = _dt.datetime.now().isoformat(timespec="seconds")
        env["legacy"] = _schema.to_legacy(env)
        return env

    # ① MiMo (1순위 — 앱 전역 시황/위원회 LLM). 비한국어(중국어) 출력 시 재시도.
    mimo_key = os.environ.get("MIMO_API_KEY", "").strip()
    if mimo_key:
        for attempt in range(3):
            try:
                raw = _call_via_mimo(system, user_prompt)
                parsed = _extract_json(raw) if raw else None
                if parsed is not None:
                    if not _is_korean_envelope(parsed):
                        print(f"[WARN] MiMo 비한국어 출력 (slot={slot}, attempt={attempt+1}) → 재시도")
                        continue
                    print(f"[INFO] MiMo 경로 완료 (slot={slot})")
                    return _finish(raw)
                if raw:
                    print(f"[WARN] MiMo JSON 파싱 실패 (slot={slot}, attempt={attempt+1})")
            except Exception as exc:
                print(f"[WARN] MiMo 실패: {exc} → 다음 경로")
                break

    # ② Anthropic (키 있을 때만)
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if _ANTHROPIC_OK and api_key:
        try:
            client = anthropic.Anthropic(api_key=api_key)
            msg = client.messages.create(model="claude-sonnet-4-6", max_tokens=2600,
                system=system, messages=[{"role": "user", "content": user_prompt}])
            return _finish(msg.content[0].text)
        except Exception as exc:
            print(f"[WARN] Claude API 실패: {exc} → Codex")

    # ③ Codex CLI (OAuth)
    try:
        raw = _call_via_codex(user_prompt, system=system)
        if raw:
            return _finish(raw)
    except Exception as exc:
        print(f"[WARN] Codex 실패: {exc}")

    # ④ 결정론 폴백
    reason = "MIMO/ANTHROPIC 키 없음 + Codex 실패" if not (mimo_key or api_key) else "LLM 호출 실패"
    return _finish(None, reason)


# ── 장중 Page 1 본문: 전문 애널리스트 문체(■/- 평문) ────────────────────────
_PAGE1_SYSTEM = (
    "당신은 한국 증권사 리서치센터의 시황 담당 애널리스트입니다. "
    "국내 주식 운용역(기관투자가)이 장중에 빠르게 읽는 '아침시황/장중 시황 노트'를 작성합니다. "
    "근거 없는 전망·상투어를 배제하고, 제공된 수치와 종목·뉴스로 인과를 단정적으로 설명합니다."
)


def _fmt_signed(v) -> str:
    try:
        return f"{float(v):+.2f}%"
    except (TypeError, ValueError):
        return "0.00%"


def _build_page1_prompt(p: dict) -> str:
    idx = p.get("indices", {})
    kospi = idx.get("kospi", {}); kosdaq = idx.get("kosdaq", {})
    br = p.get("breadth", {}); kbr = p.get("kosdaq_breadth", {})
    sectors = [s for s in (p.get("sectors") or []) if s.get("sector") and s.get("sector") != "기타"]
    sectors = sorted(sectors, key=lambda x: float(x.get("change", 0) or 0), reverse=True)
    reps = p.get("sector_reps", {})
    tops = p.get("top_contributors", []) or []
    bots = p.get("bottom_contributors", []) or []
    news = p.get("news", []) or []

    def _sec_block(s):
        nm = s["sector"]; ch = _fmt_signed(s.get("change"))
        rl = reps.get(nm, [])[:5]
        reps_str = ", ".join(f"{r.get('name','')}({_fmt_signed(r.get('change'))})" for r in rl if r.get("name")) or "—"
        return f"  · {nm} (시총가중 {ch}): 대표 {reps_str}"

    sec_lines = "\n".join(_sec_block(s) for s in sectors)
    # 작성할 섹터 사전 선정(강세 3 + 약세 1) → 누락 방지용 명시
    picked = [s["sector"] for s in sectors[:3]]
    if sectors and sectors[-1]["sector"] not in picked:
        picked.append(sectors[-1]["sector"])
    picked_str = " / ".join(f"■{nm}" for nm in picked) + " / ■KOSDAQ"
    contrib_up = ", ".join(f"{c.get('name','')}(+{float(c.get('contribution',0)):.2f}pt)" for c in tops[:6]) or "—"
    contrib_dn = ", ".join(f"{c.get('name','')}({float(c.get('contribution',0)):+.2f}pt)" for c in bots[:6]) or "—"
    news_str = "\n".join(f"  · {n.get('title', n) if isinstance(n, dict) else n}" for n in news[:8]) or "  · 없음"

    # 미국 증시(전일)
    us = p.get("us_indices", {}) or {}
    us_str = ", ".join(
        f"{k} ({v.get('change_str') or _fmt_signed(v.get('change'))})" for k, v in list(us.items())[:5]
    ) if us else ""
    us_line = f"- 전일 미국: {us_str}\n" if us_str else ""

    # 대외 지표(있는 것만)
    macro_bits = []
    if p.get("usdkrw"):
        macro_bits.append(f"원/달러 {p.get('usdkrw')}")
    if p.get("vix"):
        macro_bits.append(f"VIX {p.get('vix')}")
    macro_line = ("- 대외: " + " · ".join(macro_bits) + "\n") if macro_bits else ""

    # KOSDAQ 섹터(네이버 업종) + 등락 종목
    kq_secs = sorted([s for s in (p.get("kosdaq_sectors") or []) if s.get("sector")],
                     key=lambda x: float(x.get("change", 0) or 0), reverse=True)
    kq_top = ", ".join(f"{s.get('sector')}({_fmt_signed(s.get('change'))})" for s in kq_secs[:5]) or "—"
    kq_bot = ", ".join(f"{s.get('sector')}({_fmt_signed(s.get('change'))})" for s in kq_secs[-4:]) or "—"
    kq_g = ", ".join(f"{m.get('name','')}({_fmt_signed(m.get('change'))})" for m in (p.get("kosdaq_gainers") or [])[:6]) or "—"
    kq_l = ", ".join(f"{m.get('name','')}({_fmt_signed(m.get('change'))})" for m in (p.get("kosdaq_losers") or [])[:6]) or "—"

    return f"""[장중 시황 노트 작성 — 실데이터 기반]

## 지수
- KOSPI {float(kospi.get('index',0)):,.2f}pt ({_fmt_signed(kospi.get('change'))}) / KOSDAQ {float(kosdaq.get('index',0)):,.2f}pt ({_fmt_signed(kosdaq.get('change'))})
- 시장폭: 코스피 상승 {br.get('up',0)}·하락 {br.get('down',0)} / 코스닥 상승 {kbr.get('up',0)}·하락 {kbr.get('down',0)}
{us_line}{macro_line}
## KOSPI GICS 대분류 섹터(시총가중 등락률) + 섹터별 대표 종목(실제 등락률)
{sec_lines}

## 지수 기여도(시총×등락, 포인트)
- 견인(상위): {contrib_up}
- 압박(하위): {contrib_dn}

## KOSDAQ 동향
- 강세 업종: {kq_top}
- 약세 업종: {kq_bot}
- 상승 종목: {kq_g}
- 하락 종목: {kq_l}

## 당일 헤드라인(시장 촉매)
{news_str}

---
작성 규칙(엄수):
1) 출력은 순수 텍스트만. JSON·코드블록 금지. 헤더는 '■', 항목은 '- '로 시작.
2) 첫 블록 '■ KOSPI 장중 시황' — 불릿 4개: ① KOSPI/KOSDAQ 레벨·등락과 장 성격 ② 전일 미국 증시·대외 여건이 국내에 준 영향 ③ 시장폭(상승/하락 종목수)으로 본 강도 ④ 오늘의 관전 포인트.
3) 그 다음 아래 블록을 '반드시 모두, 이 순서대로' 작성(하나도 생략 금지):
   {picked_str}
   - 각 KOSPI 섹터 블록: '■ {{섹터}}({{시총가중 등락%}}), {{한 줄 규정}}' 헤더 + 불릿 4개:
     ① 대표 종목을 실제 등락률과 함께 인용(무엇이 끌고/눌렀는지) ② 당일 촉매 — '헤드라인'에서 그 섹터·종목과 관련된 뉴스를 찾아 구체적으로 연결. 관련 뉴스 없으면 기여도·수급으로 설명 ③ 매크로/밸류에이션 연결(미국 증시·환율·순환매 등) ④ 운용 함의(추격/분할/관망/차익실현 등 액션, 단정·간결).
4) 마지막 '■ KOSDAQ({{등락%}}), {{한 줄 규정}}' 블록 — 불릿 3개: ① 강세/약세 업종 대비 ② 상승·하락 대표 종목 인용 ③ 코스피 대비 중소형주 온도차·시장폭 해석.
5) 핵심: '당일 뉴스'를 반드시 섹터 서술에 녹일 것. 헤드라인을 섹터/종목 촉매로 적극 인용하되, 제공된 헤드라인 내용만 사용(없는 사실·수치 창작 금지).
6) 금지 표현: "주목됩니다", "관심이 필요합니다", "전망됩니다", "예상됩니다", "~할 것으로 보입니다", "신중한 접근". 상투어·중복 패턴 배제.
7) 문체: 간결한 리포트체(명사형/단정 종결 혼용, 예 '외국인 순매수 우위', '낙폭 과대'). 한 불릿 1~2문장. 섹터마다 표현을 달리할 것.
8) 한국어로만. 한자·중국어·영문 문장 금지(종목명/지수명 고유표기는 예외). 어색한 외래어 조각 금지.
9) 제공되지 않은 지표는 언급하지 말 것. '미제공/데이터 없음/N/A' 표현 절대 금지.
10) 맞춤법·띄어쓰기를 정확히. 오타·깨진 단어·합성 오류(예: '메드라인', '긴급제발' 같은 비단어) 절대 금지. 표준 한국어 금융 용어만 사용하고, 각 문장을 자연스럽게 완결할 것."""


def generate_intraday_page1_text(payload: dict) -> str:
    """장중 Page 1 본문을 전문 애널리스트 문체의 ■/- 평문으로 생성.

    내재화 데이터(payload)를 LLM(MiMo→Anthropic→Codex)에 주입한다.
    실패하거나 형식 불충족 시 빈 문자열을 반환(호출측이 결정론 생성기로 폴백).
    """
    user = _build_page1_prompt(payload)

    def _valid(t: str) -> bool:
        if not t or "■" not in t:
            return False
        # 한국어 비율 점검(중국어/영문 폭주 방지)
        ko = sum(1 for c in t if "가" <= c <= "힣")
        return ko >= 80

    def _clean(t: str) -> str:
        import unicodedata
        t = (t or "").strip()
        if t.startswith("```"):
            t = t.split("```", 2)[1] if t.count("```") >= 2 else t.replace("```", "")
            t = t.strip()
        # 분해형(NFD) 한글 자모 → 조합형(NFC)로 정규화(깨진 '멘' 등 복구)
        t = unicodedata.normalize("NFC", t)
        return _strip_hanzi(t) if "_strip_hanzi" in globals() else t

    # ① MiMo
    if os.environ.get("MIMO_API_KEY", "").strip():
        for _ in range(2):
            try:
                raw = _clean(_call_via_mimo(_PAGE1_SYSTEM, user, temperature=0.2))
                if _valid(raw):
                    print("[장중] Page1 본문: MiMo 전문문체 생성 완료")
                    return raw
            except Exception as exc:
                print(f"[WARN] Page1 MiMo 실패: {exc}")
                break

    # ② Anthropic
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if _ANTHROPIC_OK and api_key:
        try:
            client = anthropic.Anthropic(api_key=api_key)
            msg = client.messages.create(
                model="claude-sonnet-4-6", max_tokens=2200,
                system=_PAGE1_SYSTEM, messages=[{"role": "user", "content": user}])
            raw = _clean(msg.content[0].text)
            if _valid(raw):
                print("[장중] Page1 본문: Anthropic 전문문체 생성 완료")
                return raw
        except Exception as exc:
            print(f"[WARN] Page1 Anthropic 실패: {exc}")

    # ③ Codex
    try:
        raw = _clean(_call_via_codex(user, system=_PAGE1_SYSTEM))
        if _valid(raw):
            print("[장중] Page1 본문: Codex 전문문체 생성 완료")
            return raw
    except Exception as exc:
        print(f"[WARN] Page1 Codex 실패: {exc}")

    return ""
