# -*- coding: utf-8 -*-
"""시황 envelope 스키마 · 슬롯별 블록 정의 · 검증 · 레거시(9키) 매핑."""
from __future__ import annotations
from typing import Any

PERSONA = {"premarket": "장전 시황", "intraday": "아침시황", "close": "마감 시황"}
VALID_STANCES = {"RISK-ON", "NEUTRAL", "RISK-OFF"}

# 슬롯별 블록 순서·라벨·타입(bullets|paragraph|kv). 프론트/PNG/검증 공통 단일 소스.
SLOT_BLOCKS: dict[str, list[dict[str, str]]] = {
    # 장전: 미국 마감 톱다운. 좌측 4문단 내러티브(매크로/금리/환율 수치는 우측 레일).
    "premarket": [
        {"id": "global_kr",       "label": "글로벌 마감 정리",     "type": "paragraph"},
        {"id": "catalysts",       "label": "간밤 핵심 이슈 · 촉매", "type": "paragraph"},
        {"id": "sector_strategy", "label": "국내 시초 영향 · 주목 섹터", "type": "paragraph"},
        {"id": "checkpoint",      "label": "오늘 체크포인트",      "type": "paragraph"},
    ],
    "intraday": [
        {"id": "kospi_theme",  "label": "KOSPI 흐름 · 주도 테마",  "type": "paragraph"},
        {"id": "kosdaq_theme", "label": "KOSDAQ 흐름 · 주도 테마", "type": "paragraph"},
        {"id": "sector_rs",    "label": "섹터 · RS 동향",          "type": "bullets"},
        {"id": "breadth_flow", "label": "등락 · 수급",             "type": "kv"},
        {"id": "headlines",    "label": "주요 헤드라인",            "type": "bullets"},
    ],
    # 마감 시황(신한투자증권) 마감 시황 재현: 동적 한글 제목(heading) + 종목(±%, 사유) + #특징업종 태그
    # dyn=True → 섹션 제목을 LLM이 그날 메시지로 생성(예: "반도체 무너지고 방어주만 버텨")
    "close": [
        {"id": "index_wrap",   "label": "지수 총평",        "type": "paragraph", "dyn": True},
        {"id": "sector_flow",  "label": "섹터 · 특징주",    "type": "paragraph", "dyn": True},
        {"id": "feature_tags", "label": "특징 업종",        "type": "bullets"},
        {"id": "event_outlook","label": "핵심 이벤트 · 내일", "type": "paragraph", "dyn": True},
        {"id": "takeaway",     "label": "운용 시사점",      "type": "paragraph"},
    ],
}

# legacy 9키 ← envelope 블록 매핑(블록 id 우선순위로 채움)
_LEGACY_FROM = {
    "key_issue":  ["catalysts", "index_wrap", "kospi_theme"],
    "bull_case":  ["sector_strategy", "sector_flow", "sector_rs"],
    "bear_case":  ["checkpoint", "event_outlook", "breadth_flow"],
    "macro_flow": ["global_kr", "index_wrap", "breadth_flow"],
    "kr_outlook": ["global_kr", "takeaway", "kosdaq_theme"],
    "strategy":   ["sector_strategy", "takeaway", "sector_rs"],
    "news_flow":  ["headlines", "feature_tags", "sector_flow"],
}


def _empty_body(btype: str) -> Any:
    return {"bullets": ["—"], "paragraph": "—", "kv": [{"k": "—", "v": "—"}]}[btype]


def _coerce_body(btype: str, body: Any) -> Any:
    if body in (None, "", [], {}):
        return _empty_body(btype)
    if btype == "bullets":
        if isinstance(body, str):
            return [ln.strip(" -•·") for ln in body.splitlines() if ln.strip()] or ["—"]
        return [str(x).strip(" -•·") for x in body if str(x).strip()] or ["—"]
    if btype == "paragraph":
        if isinstance(body, list):
            return " ".join(str(x) for x in body) or "—"
        return str(body)
    # kv
    out = []
    if isinstance(body, dict):
        body = [{"k": k, "v": v} for k, v in body.items()]
    for item in body if isinstance(body, list) else []:
        if isinstance(item, dict) and ("k" in item or "v" in item):
            out.append({"k": str(item.get("k", "")), "v": str(item.get("v", "")),
                        "tone": item.get("tone", "neutral")})
    return out or _empty_body("kv")


def normalize_envelope(slot: str, raw: dict[str, Any]) -> dict[str, Any]:
    """LLM 산출 raw dict를 슬롯 규격 envelope로 정규화(누락 보정·순서 고정)."""
    spec = SLOT_BLOCKS.get(slot)
    if spec is None:
        raise ValueError(f"unknown slot: {slot!r}")
    raw = raw or {}
    given = {str(b.get("id")): b for b in (raw.get("blocks") or []) if isinstance(b, dict)}

    blocks = []
    for s in spec:
        src = given.get(s["id"], {})
        block = {
            "id": s["id"], "label": s["label"], "type": s["type"],
            "body": _coerce_body(s["type"], src.get("body")),
        }
        # dyn 블록: LLM이 생성한 그날 한글 제목(heading). 없으면 고정 label 사용.
        if s.get("dyn"):
            heading = str(src.get("heading", "")).strip()
            block["heading"] = heading or s["label"]
        blocks.append(block)

    stance = str(raw.get("stance", "")).upper().strip()
    if stance not in VALID_STANCES:
        stance = "NEUTRAL"
    title = str(raw.get("title", "")).strip() or f"{PERSONA[slot]} 시황 브리핑"
    headline = str(raw.get("headline", "")).strip() or "—"

    return {
        "slot": slot, "persona": PERSONA[slot], "title": title,
        "stance": stance, "headline": headline, "blocks": blocks,
    }


def _block_text(block: dict[str, Any]) -> str:
    body = block.get("body")
    if isinstance(body, list):
        if body and isinstance(body[0], dict):  # kv
            return "\n".join(f"- {i.get('k')}: {i.get('v')}" for i in body)
        return "\n".join(f"- {x}" for x in body)
    return str(body or "—")


def to_legacy(env: dict[str, Any]) -> dict[str, Any]:
    """기존 PNG/렌더러 호환용 9키 매핑."""
    by_id = {b["id"]: b for b in env.get("blocks", [])}
    legacy = {"title": env.get("title", "—"), "stance": env.get("stance", "NEUTRAL")}
    for key, candidates in _LEGACY_FROM.items():
        text = "—"
        for cid in candidates:
            if cid in by_id:
                text = _block_text(by_id[cid]); break
        legacy[key] = text
    return legacy


def fallback_envelope(slot: str, reason: str = "") -> dict[str, Any]:
    """LLM 미가용 시 슬롯별 완결 폴백(공백 금지)."""
    spec = SLOT_BLOCKS[slot]
    raw_blocks = [{"id": s["id"], "body": _empty_body(s["type"])} for s in spec]
    env = normalize_envelope(slot, {
        "title": f"{PERSONA[slot]} 시황 — 데이터 준비 중",
        "stance": "NEUTRAL",
        "headline": f"분석 텍스트 생성 보류 중{f' ({reason})' if reason else ''}. 데이터 패널을 참고하세요.",
        "blocks": raw_blocks,
    })
    return env
