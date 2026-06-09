import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "sitele"))

import report_schema as rs


def test_slot_blocks_well_formed():
    for slot in ("premarket", "intraday", "close"):
        spec = rs.SLOT_BLOCKS[slot]
        assert 3 <= len(spec) <= 6  # 슬롯별 블록 수는 다를 수 있음
        assert all({"id", "label", "type"} <= set(b) for b in spec)
        assert all(b["type"] in ("paragraph", "bullets", "kv") for b in spec)


def test_normalize_envelope_fills_missing_blocks_and_stance():
    raw = {"title": "테스트 제목·시장·판단", "stance": "BOGUS",
           "headline": "요약", "blocks": [
               {"id": "global_kr", "type": "paragraph", "body": "문단"}]}
    env = rs.normalize_envelope("premarket", raw)
    assert env["slot"] == "premarket"
    assert env["persona"] == "한지영"
    assert env["stance"] == "NEUTRAL"
    assert len(env["blocks"]) == len(rs.SLOT_BLOCKS["premarket"])
    ids = [b["id"] for b in env["blocks"]]
    assert ids == [b["id"] for b in rs.SLOT_BLOCKS["premarket"]]
    assert env["blocks"][0]["body"] == "문단"


def test_legacy_mapping_has_nine_keys():
    env = rs.normalize_envelope("close", {"title": "마감·수급·판단",
                                          "stance": "RISK-OFF", "headline": "h",
                                          "blocks": []})
    legacy = rs.to_legacy(env)
    assert {"title", "stance", "key_issue", "bull_case", "bear_case",
            "macro_flow", "kr_outlook", "strategy", "news_flow"} <= set(legacy)
    assert legacy["title"] == "마감·수급·판단"
    assert legacy["stance"] == "RISK-OFF"


def test_fallback_envelope_is_complete():
    env = rs.fallback_envelope("intraday", reason="no_llm")
    assert env["slot"] == "intraday"
    assert len(env["blocks"]) == len(rs.SLOT_BLOCKS["intraday"])
    assert all(b.get("body") not in (None, "", []) for b in env["blocks"])
