"""세부 업종명 → GICS 스타일 11 대분류 매핑.

price_service 의 종목 sector(네이버 업종 상세명, 약 70여 종)를 11개 대분류 +
'기타'로 접는다. 정확 매칭(_EXACT) 우선, 미등록 명칭은 키워드 폴백(_RULES)으로 흡수.
새 업종명이 등장해도 키워드로 합리적으로 분류되도록 이중 안전망을 둔다.
"""
from __future__ import annotations

from typing import Optional

# 11 대분류 (+기타) — 한국어 라벨
IT = '정보기술'
INDUSTRIALS = '산업재'
MATERIALS = '소재'
DISCRETIONARY = '경기소비재'
FINANCIALS = '금융'
HEALTHCARE = '헬스케어'
COMMUNICATION = '커뮤니케이션'
STAPLES = '필수소비재'
ENERGY = '에너지'
UTILITIES = '유틸리티'
REAL_ESTATE = '부동산'
OTHER = '기타'

MAJORS = [IT, INDUSTRIALS, MATERIALS, DISCRETIONARY, FINANCIALS, HEALTHCARE,
          COMMUNICATION, STAPLES, ENERGY, UTILITIES, REAL_ESTATE, OTHER]

# 실제 등장하는 네이버 상세 업종명 → 대분류 (정확 매칭)
_EXACT = {
    # 정보기술
    '반도체와반도체장비': IT, '전자장비와기기': IT, 'IT서비스': IT, '전기제품': IT,
    '전자제품': IT, '디스플레이장비및부품': IT, '디스플레이패널': IT, '통신장비': IT,
    '핸드셋': IT, '소프트웨어': IT, '컴퓨터와주변기기': IT, '사무용전자제품': IT,
    # 산업재
    '건설': INDUSTRIALS, '기계': INDUSTRIALS, '조선': INDUSTRIALS, '전기장비': INDUSTRIALS,
    '항공화물운송과물류': INDUSTRIALS, '항공사': INDUSTRIALS, '해운사': INDUSTRIALS,
    '우주항공과국방': INDUSTRIALS, '상업서비스와공급품': INDUSTRIALS,
    '무역회사와판매업체': INDUSTRIALS, '도로와철도운송': INDUSTRIALS, '운송인프라': INDUSTRIALS,
    '복합기업': INDUSTRIALS, '건축제품': INDUSTRIALS,
    # 소재
    '화학': MATERIALS, '철강': MATERIALS, '비철금속': MATERIALS, '포장재': MATERIALS,
    '종이와목재': MATERIALS, '건축자재': MATERIALS,
    # 경기소비재
    '자동차': DISCRETIONARY, '자동차부품': DISCRETIONARY, '섬유,의류,신발,호화품': DISCRETIONARY,
    '백화점과일반상점': DISCRETIONARY, '호텔,레스토랑,레저': DISCRETIONARY, '가구': DISCRETIONARY,
    '가정용기기와용품': DISCRETIONARY, '레저용장비와제품': DISCRETIONARY, '전문소매': DISCRETIONARY,
    '인터넷과카탈로그소매': DISCRETIONARY, '교육서비스': DISCRETIONARY, '판매업체': DISCRETIONARY,
    '문구류': DISCRETIONARY,
    # 금융
    '증권': FINANCIALS, '은행': FINANCIALS, '손해보험': FINANCIALS, '생명보험': FINANCIALS,
    '카드': FINANCIALS, '창업투자': FINANCIALS,
    # 헬스케어
    '제약': HEALTHCARE, '생물공학': HEALTHCARE, '건강관리장비와용품': HEALTHCARE,
    '건강관리업체및서비스': HEALTHCARE,
    # 커뮤니케이션
    '방송과엔터테인먼트': COMMUNICATION, '무선통신서비스': COMMUNICATION,
    '다각화된통신서비스': COMMUNICATION, '양방향미디어와서비스': COMMUNICATION,
    '광고': COMMUNICATION, '출판': COMMUNICATION, '게임엔터테인먼트': COMMUNICATION,
    # 필수소비재
    '식품': STAPLES, '음료': STAPLES, '담배': STAPLES, '식품과기본식료품소매': STAPLES,
    '화장품': STAPLES, '가정용품': STAPLES,
    # 에너지
    '석유와가스': ENERGY, '에너지장비및서비스': ENERGY,
    # 유틸리티
    '가스유틸리티': UTILITIES, '전기유틸리티': UTILITIES, '복합유틸리티': UTILITIES,
    # 부동산
    '부동산': REAL_ESTATE,
}

# 키워드 폴백 — 위에서부터 우선. 미등록/변형 명칭 흡수용(순서가 곧 우선순위).
_RULES = [
    ('유틸리티', UTILITIES), ('가스', UTILITIES),
    ('반도체', IT), ('디스플레이', IT), ('소프트웨어', IT), ('컴퓨터', IT),
    ('IT', IT), ('통신장비', IT), ('핸드셋', IT), ('전자', IT),
    ('우주항공', INDUSTRIALS), ('국방', INDUSTRIALS), ('조선', INDUSTRIALS),
    ('건설', INDUSTRIALS), ('기계', INDUSTRIALS), ('전기장비', INDUSTRIALS),
    ('운송', INDUSTRIALS), ('항공', INDUSTRIALS), ('해운', INDUSTRIALS),
    ('물류', INDUSTRIALS), ('복합기업', INDUSTRIALS),
    ('화학', MATERIALS), ('철강', MATERIALS), ('금속', MATERIALS),
    ('포장재', MATERIALS), ('종이', MATERIALS), ('건축자재', MATERIALS),
    ('제약', HEALTHCARE), ('바이오', HEALTHCARE), ('생물', HEALTHCARE),
    ('건강관리', HEALTHCARE), ('의료', HEALTHCARE),
    ('증권', FINANCIALS), ('은행', FINANCIALS), ('보험', FINANCIALS),
    ('카드', FINANCIALS), ('금융', FINANCIALS), ('창업투자', FINANCIALS),
    ('방송', COMMUNICATION), ('엔터', COMMUNICATION), ('미디어', COMMUNICATION),
    ('통신서비스', COMMUNICATION), ('광고', COMMUNICATION), ('출판', COMMUNICATION),
    ('게임', COMMUNICATION),
    ('식품', STAPLES), ('음료', STAPLES), ('담배', STAPLES), ('화장품', STAPLES),
    ('가정용품', STAPLES),
    ('자동차', DISCRETIONARY), ('의류', DISCRETIONARY), ('섬유', DISCRETIONARY),
    ('백화점', DISCRETIONARY), ('호텔', DISCRETIONARY), ('레저', DISCRETIONARY),
    ('소매', DISCRETIONARY), ('가구', DISCRETIONARY), ('교육', DISCRETIONARY),
    ('석유', ENERGY), ('에너지', ENERGY), ('가스유틸', UTILITIES),
    ('부동산', REAL_ESTATE), ('리츠', REAL_ESTATE),
]


def to_major_sector(detailed: Optional[str]) -> str:
    """세부 업종명을 11 대분류 중 하나로 매핑. 미상/미분류는 '기타'."""
    s = str(detailed or '').strip()
    if not s or s in ('기타', 'KOSPI', 'KOSDAQ'):
        return OTHER
    if s in _EXACT:
        return _EXACT[s]
    for kw, major in _RULES:
        if kw in s:
            return major
    return OTHER
