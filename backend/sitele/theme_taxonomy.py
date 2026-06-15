# -*- coding: utf-8 -*-
"""
주도 테마(Leading Theme) 분류 모듈
- KOSPI/KOSDAQ 업종(sector) 이름을 12개 대주제 테마로 그루핑
- aggregate_theme_returns()로 테마별 평균 등락률 산출
"""
from __future__ import annotations

from typing import Any

# ── 12대 테마 정의 ─────────────────────────────────────────────────────────
THEMES: list[str] = [
    "반도체·AI",
    "전력·인프라",
    "방산",
    "2차전지",
    "조선",
    "바이오·제약",
    "자동차",
    "인터넷·게임",
    "금융",
    "소재·화학",
    "소비·유통",
    "기타",
]

# 테마별 매칭 키워드 (순서 중요 — 앞에서부터 첫 매칭 사용)
THEME_KEYWORDS: dict[str, list[str]] = {
    "반도체·AI":   ["반도체", "IT", "전기전자", "온디바이스", "HBM", "AI반도체", "시스템반도체"],
    "전력·인프라": ["전력", "전기", "유틸", "에너지", "인프라", "가스", "발전"],
    "방산":        ["방산", "우주", "국방", "항공"],
    "2차전지":     ["2차전지", "전지", "배터리", "리튬", "이차전지", "양극재", "음극재"],
    "조선":        ["조선", "선박", "해운"],
    "바이오·제약": ["제약", "바이오", "의료", "의약품", "헬스케어", "의료기기", "바이오텍"],
    "자동차":      ["자동차", "운송장비", "운수장비", "차량", "부품", "완성차"],
    "인터넷·게임": ["인터넷", "게임", "소프트", "미디어", "엔터", "플랫폼", "콘텐츠"],
    "금융":        ["은행", "증권", "보험", "금융", "카드", "캐피탈"],
    "소재·화학":   ["화학", "철강", "금속", "소재", "비철", "기계", "건설"],
    "소비·유통":   ["유통", "음식료", "섬유", "화장품", "소비", "의류", "식품", "백화점", "마트"],
}

# ── 단일 업종명 → 테마 매핑 ───────────────────────────────────────────────
def to_theme(sector_name: str) -> str:
    """
    sector_name에 포함된 키워드로 테마를 결정한다.
    THEME_KEYWORDS를 순서대로 검사하며 첫 매칭 테마를 반환.
    매칭 없으면 '기타'.
    """
    name = str(sector_name or "")
    for theme, keywords in THEME_KEYWORDS.items():
        for kw in keywords:
            if kw in name:
                return theme
    return "기타"


# ── 테마별 평균 등락률 집계 ───────────────────────────────────────────────
def aggregate_theme_returns(sector_returns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    입력: [{"sector": str, "change": float}, ...] 형태의 리스트
          "name"/"return"/"rs_1d" 키도 허용 (graceful).
    출력: [{"theme": str, "change": float(평균, 반올림2), "count": int}, ...]
          change 내림차순 정렬. 빈 테마는 제외.
    """
    accum: dict[str, list[float]] = {}

    for item in (sector_returns or []):
        if not isinstance(item, dict):
            continue

        # 업종명: "sector" > "name" 순으로 탐색
        sector_name = item.get("sector") or item.get("name") or ""

        # 등락률: "change" > "return" > "rs_1d" 순으로 탐색
        raw_change = item.get("change")
        if raw_change is None:
            raw_change = item.get("return")
        if raw_change is None:
            raw_change = item.get("rs_1d")

        try:
            change_val = float(raw_change)
        except (TypeError, ValueError):
            continue  # 숫자 변환 불가 → 건너뜀

        theme = to_theme(sector_name)
        accum.setdefault(theme, []).append(change_val)

    result: list[dict[str, Any]] = []
    for theme, values in accum.items():
        if not values:
            continue
        mean_change = round(sum(values) / len(values), 2)
        result.append({
            "theme":  theme,
            "change": mean_change,
            "count":  len(values),
        })

    # change 내림차순 정렬 (기타는 맨 뒤로)
    result.sort(key=lambda x: (x["theme"] == "기타", -x["change"]))
    return result
