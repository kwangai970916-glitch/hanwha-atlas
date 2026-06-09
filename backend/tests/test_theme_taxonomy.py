# -*- coding: utf-8 -*-
"""
테마 분류(theme_taxonomy) 단위 테스트
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "sitele"))

import theme_taxonomy as tt


def test_to_theme_maps_keywords():
    assert tt.to_theme("반도체") == "반도체·AI"
    assert tt.to_theme("조선") == "조선"
    assert tt.to_theme("은행") == "금융"
    assert tt.to_theme("듣보업종") == "기타"


def test_to_theme_it_maps_to_semiconductor():
    # IT 키워드 → 반도체·AI
    assert tt.to_theme("IT서비스") == "반도체·AI"
    assert tt.to_theme("전기전자") == "반도체·AI"


def test_to_theme_additional():
    assert tt.to_theme("2차전지 소재") == "2차전지"
    assert tt.to_theme("제약") == "바이오·제약"
    assert tt.to_theme("화학") == "소재·화학"
    assert tt.to_theme("인터넷") == "인터넷·게임"
    assert tt.to_theme("자동차") == "자동차"
    assert tt.to_theme("방산") == "방산"
    assert tt.to_theme("전력") == "전력·인프라"
    assert tt.to_theme("유통") == "소비·유통"


def test_aggregate_theme_returns():
    rows = [
        {"sector": "반도체",  "change": 2.0},
        {"sector": "IT서비스","change": 1.0},
        {"sector": "조선",    "change": -1.0},
    ]
    out = tt.aggregate_theme_returns(rows)
    by = {o["theme"]: o for o in out}
    # 반도체·AI: (2.0 + 1.0) / 2 = 1.5
    assert abs(by["반도체·AI"]["change"] - 1.5) < 1e-6
    assert by["반도체·AI"]["count"] == 2
    assert by["조선"]["change"] == -1.0
    assert by["조선"]["count"] == 1


def test_aggregate_empty():
    assert tt.aggregate_theme_returns([]) == []


def test_aggregate_graceful_name_alias():
    # "name" 키 사용 허용
    rows = [{"name": "은행", "change": 0.5}]
    out = tt.aggregate_theme_returns(rows)
    assert out[0]["theme"] == "금융"


def test_aggregate_graceful_change_alias():
    # "rs_1d" 키 사용 허용
    rows = [{"sector": "바이오", "rs_1d": 3.2}]
    out = tt.aggregate_theme_returns(rows)
    assert out[0]["theme"] == "바이오·제약"
    assert out[0]["change"] == 3.2


def test_aggregate_sorted_descending():
    rows = [
        {"sector": "화학", "change": -1.0},
        {"sector": "반도체", "change": 3.0},
        {"sector": "은행", "change": 1.5},
    ]
    out = tt.aggregate_theme_returns(rows)
    changes = [o["change"] for o in out if o["theme"] != "기타"]
    assert changes == sorted(changes, reverse=True)


def test_aggregate_기타_last():
    rows = [
        {"sector": "모르는업종", "change": 99.0},
        {"sector": "반도체", "change": 1.0},
    ]
    out = tt.aggregate_theme_returns(rows)
    themes = [o["theme"] for o in out]
    assert themes[-1] == "기타"


def test_aggregate_skips_non_numeric_change():
    rows = [
        {"sector": "반도체", "change": "N/A"},
        {"sector": "조선", "change": 2.0},
    ]
    out = tt.aggregate_theme_returns(rows)
    by = {o["theme"]: o for o in out}
    # 반도체는 숫자 변환 실패로 건너뜀
    assert "반도체·AI" not in by
    assert by["조선"]["change"] == 2.0
