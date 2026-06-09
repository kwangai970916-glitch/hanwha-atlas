# -*- coding: utf-8 -*-
"""
시황 브리핑 발송/생성 이력 저장·조회 + 다음 실행 스케줄 계산.

- append_history(...) : 브리핑 생성 1건을 jsonl 에 append
- list_history(...)   : 최근 이력 리스트(최신순) 반환
- next_scheduled_times(): 07:00 / 08:30 / 16:30 KST 기준 다음 실행시각(카운트다운 UI용)

저장 위치:
  backend/data/briefing_history.jsonl  (한 줄 = 한 JSON 레코드)

각 레코드 스키마:
  {
    "slot": "premarket" | "intraday" | "close",
    "ts": ISO8601 문자열(KST, +09:00),
    "ts_epoch": float(UNIX epoch, 정렬·중복방지용),
    "decision_summary": str | null,   # 선택(시황 title/stance 등)
    "png_path": str,                  # 생성 PNG 절대경로(없으면 "")
    "success": bool                   # 생성 성공 여부(있으면)
  }

순수 표준 라이브러리만 사용 (외부 패키지 의존 없음). Python 3.9 호환.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone, time as dtime
from pathlib import Path
from typing import Any, Dict, List, Optional

# ── 경로 / 상수 ─────────────────────────────────────────────────────────────
_BACKEND_DIR = Path(__file__).resolve().parents[1]
_DATA_DIR = _BACKEND_DIR / "data"
_HISTORY_PATH = _DATA_DIR / "briefing_history.jsonl"

# KST (UTC+9). 한국 증시는 DST 없음 → 고정 오프셋.
KST = timezone(timedelta(hours=9))

# 슬롯별 정규 실행 시각 (KST, 24h). 카운트다운 UI 가 참조.
SLOT_SCHEDULE = {
    "premarket": dtime(7, 0),    # 07:00 장전
    "intraday":  dtime(8, 30),   # 08:30 장중(개장 직전 점검)
    "close":     dtime(16, 30),  # 16:30 장마감 정리
}

_VALID_SLOTS = set(SLOT_SCHEDULE.keys())


# ── 내부 유틸 ────────────────────────────────────────────────────────────────
def _ensure_data_dir() -> None:
    try:
        _DATA_DIR.mkdir(parents=True, exist_ok=True)
    except Exception:
        # 디렉터리 생성 실패는 append 시점에서 다시 시도/무시
        pass


def _now_kst() -> datetime:
    return datetime.now(KST)


# ── 이력 append ──────────────────────────────────────────────────────────────
def append_history(
    slot: str,
    png_path: str = "",
    decision_summary: Optional[str] = None,
    success: Optional[bool] = None,
    ts: Optional[datetime] = None,
    **extra: Any,
) -> Dict[str, Any]:
    """
    브리핑 생성 1건을 history jsonl 에 append.

    Parameters
    ----------
    slot             : 'premarket' | 'intraday' | 'close' (검증은 느슨 — 그대로 기록)
    png_path         : 생성된 PNG 절대경로(없으면 "")
    decision_summary : 요약 텍스트(예: "RISK-ON · 반도체 주도"), 없으면 None
    success          : 생성 성공 여부(옵션)
    ts               : 기록 시각(없으면 현재 KST)
    extra            : 추가 메타데이터(그대로 레코드에 병합)

    Returns
    -------
    저장된 레코드 dict (실패해도 dict 는 반환).
    """
    _ensure_data_dir()
    now = ts or _now_kst()
    if now.tzinfo is None:
        now = now.replace(tzinfo=KST)

    record: Dict[str, Any] = {
        "slot": slot,
        "ts": now.isoformat(),
        "ts_epoch": now.timestamp(),
        "decision_summary": decision_summary,
        "png_path": png_path or "",
    }
    if success is not None:
        record["success"] = bool(success)
    if extra:
        # 예약 키를 덮어쓰지 않도록 보호
        for k, v in extra.items():
            if k not in record:
                record[k] = v

    try:
        with open(_HISTORY_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as e:
        # 기록 실패는 치명적이지 않음 — 진단 키만 추가하고 반환
        record["_write_error"] = str(e)
    return record


# ── 이력 조회 ────────────────────────────────────────────────────────────────
def list_history(limit: int = 50, slot: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    최근 브리핑 이력을 최신순으로 반환.

    Parameters
    ----------
    limit : 최대 반환 개수 (기본 50)
    slot  : 지정 시 해당 슬롯만 필터링

    Returns
    -------
    레코드 list (최신순). 파일이 없으면 빈 리스트.
    """
    if not _HISTORY_PATH.exists():
        return []

    records: List[Dict[str, Any]] = []
    try:
        with open(_HISTORY_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if slot and rec.get("slot") != slot:
                    continue
                records.append(rec)
    except Exception:
        return []

    # 최신순 정렬: ts_epoch 우선, 없으면 ts 문자열
    def _sort_key(r: Dict[str, Any]):
        ep = r.get("ts_epoch")
        if isinstance(ep, (int, float)):
            return (1, float(ep))
        return (0, str(r.get("ts", "")))

    records.sort(key=_sort_key, reverse=True)
    if limit and limit > 0:
        return records[:limit]
    return records


# ── 다음 실행 스케줄 ─────────────────────────────────────────────────────────
def next_scheduled_times(now: Optional[datetime] = None) -> List[Dict[str, Any]]:
    """
    07:00 / 08:30 / 16:30 KST 기준 슬롯별 '다음 실행시각'을 계산.
    카운트다운 UI 가 seconds_until 로 남은 시간을 표시.

    Returns
    -------
    슬롯별 dict 리스트 (next_ts 오름차순):
      {
        "slot": str,
        "label": "HH:MM",
        "next_ts": ISO8601(KST),
        "next_epoch": float,
        "seconds_until": int (>=0)
      }
    """
    base = now or _now_kst()
    if base.tzinfo is None:
        base = base.replace(tzinfo=KST)
    else:
        base = base.astimezone(KST)

    out: List[Dict[str, Any]] = []
    for slot, sched in SLOT_SCHEDULE.items():
        candidate = base.replace(
            hour=sched.hour, minute=sched.minute,
            second=0, microsecond=0,
        )
        if candidate <= base:
            candidate = candidate + timedelta(days=1)
        seconds_until = int((candidate - base).total_seconds())
        out.append({
            "slot": slot,
            "label": f"{sched.hour:02d}:{sched.minute:02d}",
            "next_ts": candidate.isoformat(),
            "next_epoch": candidate.timestamp(),
            "seconds_until": max(seconds_until, 0),
        })

    out.sort(key=lambda x: x["next_epoch"])
    return out


if __name__ == "__main__":
    # 간이 점검
    print("history path:", _HISTORY_PATH)
    print("next_scheduled_times:")
    for item in next_scheduled_times():
        print(" ", item)
    print("list_history(limit=5):")
    for r in list_history(limit=5):
        print(" ", r)
