# -*- coding: utf-8 -*-
"""Shared configuration helpers for report automation."""

from __future__ import annotations

import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
# 위원회 엔진 .env (MIMO_API_KEY/DART_API_KEY/ECOS_API_KEY 등 실제 키 보관처).
# 단독 실행(run_*.py: 텔레그램 cron)에서도 시황 LLM(MiMo)이 동작하도록 폴백 로드한다.
COMMITTEE_ENV = BASE_DIR.parent.parent / "committee_engine" / "TradingAgents" / ".env"


def _load_one_env(env_path: Path, *, override: bool) -> None:
    """단일 .env 파일을 os.environ 에 주입. BOM·'export KEY=' 형식 허용."""
    if not env_path.exists():
        return
    # 위원회 .env 는 BOM(utf-8-sig)일 수 있어 sig 로 읽어 첫 키 깨짐 방지
    for raw_line in env_path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key.startswith("export "):
            key = key[len("export "):].strip()
        value = value.strip().strip('"').strip("'")
        if key and (override or key not in os.environ):
            os.environ[key] = value


def load_env_file(path: str | os.PathLike | None = None, *, override: bool = False) -> None:
    """Load simple KEY=VALUE pairs from a .env file into os.environ.

    명시 경로가 없으면 sitele/.env(우선) + 위원회 .env(폴백)를 함께 로드한다.
    이미 존재하는 키는 보존(override=False)하므로 sitele/.env 값이 우선한다.
    """
    if path is not None:
        _load_one_env(Path(path), override=override)
        return
    _load_one_env(BASE_DIR / ".env", override=override)        # 1차: sitele 로컬
    _load_one_env(COMMITTEE_ENV, override=override)            # 2차: 위원회 키(MiMo 등) 폴백


def get_env(name: str, default: str | None = None) -> str | None:
    """Return an environment value after loading the project .env file."""
    load_env_file()
    return os.environ.get(name, default)


def require_env(name: str) -> str:
    """Return an environment value or raise a clear runtime error."""
    value = get_env(name)
    if not value:
        raise RuntimeError(
            f"Required environment variable {name} is missing. "
            "Set it in Windows environment variables or in this folder's .env file."
        )
    return value
