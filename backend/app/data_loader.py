from __future__ import annotations

from pathlib import Path
import csv
import json
from functools import lru_cache


def _resolve_sample_dir() -> Path:
    """레거시 샘플 픽스처 경로. 배포 이미지에 포함되도록 backend/app/data/samples 를
    우선하고, 없으면 로컬 개발용 루트 /data/samples 를 쓴다."""
    bundled = Path(__file__).resolve().parent / "data" / "samples"   # backend/app/data/samples (Docker 포함)
    if bundled.exists():
        return bundled
    legacy = Path(__file__).resolve().parents[2] / "data" / "samples"  # 루트/data/samples (로컬 전용)
    return legacy if legacy.exists() else bundled


SAMPLE_DIR = _resolve_sample_dir()


def _read_json(name: str, default):
    """샘플 JSON 로더 — 파일이 없거나 깨져도 절대 예외를 던지지 않는다(배포 안전)."""
    try:
        return json.loads((SAMPLE_DIR / name).read_text(encoding="utf-8-sig"))
    except Exception:
        return default


@lru_cache(maxsize=1)
def load_market_summary() -> dict:
    return _read_json("market_summary.json", {})


@lru_cache(maxsize=1)
def load_sectors() -> list[dict]:
    return _read_csv("sector_snapshot.csv")


@lru_cache(maxsize=1)
def load_stocks() -> list[dict]:
    return _read_csv("stock_universe.csv")


@lru_cache(maxsize=1)
def load_news() -> list[dict]:
    return _read_json("news_headlines.json", [])


@lru_cache(maxsize=1)
def load_dart_events() -> list[dict]:
    return _read_json("dart_events.json", [])


def _read_csv(name: str) -> list[dict]:
    try:
        with (SAMPLE_DIR / name).open("r", encoding="utf-8-sig", newline="") as handle:
            return list(csv.DictReader(handle))
    except Exception:
        return []
