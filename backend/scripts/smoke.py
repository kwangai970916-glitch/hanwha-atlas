# backend/scripts/smoke.py
"""5탭 스모크 테스트.

FastAPI TestClient 로 app 을 import 한 뒤 핵심 엔드포인트를 빠르게 점검한다.
각 항목은 PASS/FAIL 한 줄 + 핵심값을 출력한다. 위원회 라이브 완주(수 분)는
기다리지 않고 POST /api/committee/run 이 즉시 job_id 를 반환하는지만 확인한다.

실행:
    cd C:/.../ai-investment-desk-os/backend
    python scripts/smoke.py

종료코드: 모든 항목 PASS 면 0, 하나라도 FAIL 이면 1.
"""
from __future__ import annotations

import sys
from pathlib import Path

# scripts/ 의 부모(=backend 루트)를 sys.path 에 추가해 'app' 패키지를 import 가능하게.
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

# Windows 콘솔에서 한글/이모지 출력 깨짐 방지.
try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

from fastapi.testclient import TestClient  # noqa: E402

# app import 시 .env 로더(_load_env_file)가 동작하여 키들이 os.environ 에 주입된다.
from app.main import app  # noqa: E402

client = TestClient(app)

_results: list[tuple[str, bool, str]] = []


def _record(name: str, passed: bool, detail: str) -> None:
    _results.append((name, passed, detail))
    status = "PASS" if passed else "FAIL"
    print(f"[{status}] {name} - {detail}")


def check_kpi() -> None:
    """(a) GET /api/market/kpi 200 + kospi 키 존재."""
    name = "a) GET /api/market/kpi"
    try:
        r = client.get("/api/market/kpi")
        if r.status_code != 200:
            _record(name, False, f"status={r.status_code}")
            return
        body = r.json()
        has_kospi = isinstance(body, dict) and "kospi" in body
        kospi = body.get("kospi") if isinstance(body, dict) else None
        kval = kospi.get("value") if isinstance(kospi, dict) else None
        _record(name, has_kospi, f"status=200 kospi.value={kval}")
    except Exception as e:
        _record(name, False, f"exception={e!r}")


def check_pnl() -> None:
    """(b) GET /api/pnl 200 + holdings 비어있지 않음 + total_value>0."""
    name = "b) GET /api/pnl"
    try:
        r = client.get("/api/pnl")
        if r.status_code != 200:
            _record(name, False, f"status={r.status_code}")
            return
        body = r.json()
        holdings = body.get("holdings") if isinstance(body, dict) else None
        total_value = body.get("total_value") if isinstance(body, dict) else None
        n = len(holdings) if isinstance(holdings, list) else 0
        tv = total_value if isinstance(total_value, (int, float)) else 0
        passed = n > 0 and tv > 0
        _record(name, passed, f"status=200 holdings={n} total_value={tv}")
    except Exception as e:
        _record(name, False, f"exception={e!r}")


def check_snapshot() -> None:
    """(c) GET /api/market/snapshot 200 + ticks 비어있지 않음."""
    name = "c) GET /api/market/snapshot"
    try:
        r = client.get("/api/market/snapshot")
        if r.status_code != 200:
            _record(name, False, f"status={r.status_code}")
            return
        body = r.json()
        ticks = body.get("ticks") if isinstance(body, dict) else None
        n = len(ticks) if isinstance(ticks, list) else 0
        transport = body.get("transport") if isinstance(body, dict) else None
        _record(name, n > 0, f"status=200 ticks={n} transport={transport}")
    except Exception as e:
        _record(name, False, f"exception={e!r}")


def check_committee_latest() -> None:
    """(d) GET /api/committee/latest 200 + decision/reports 존재.

    중요: 토큰 절약을 위해 실제 위원회를 기동하지 않는다(POST /run 금지 —
    매 스모크마다 MiMo 멀티에이전트가 수 분간 돌아 토큰을 소모하던 문제).
    대신 최근 결과 또는 seed 폴백을 반환하는 latest 엔드포인트만 점검한다.
    """
    name = "d) GET /api/committee/latest"
    try:
        r = client.get("/api/committee/latest")
        if r.status_code != 200:
            _record(name, False, f"status={r.status_code} body={r.text[:200]}")
            return
        body = r.json() if r.content else {}
        decision = body.get("decision") if isinstance(body, dict) else None
        reports = body.get("reports") if isinstance(body, dict) else None
        n = len(reports) if isinstance(reports, dict) else 0
        is_seed = body.get("is_seed") if isinstance(body, dict) else None
        passed = bool(decision) and n >= 7
        _record(name, passed, f"status=200 decision={decision} reports={n} is_seed={is_seed}")
    except Exception as e:
        _record(name, False, f"exception={e!r}")


def check_market_table() -> None:
    """(e) GET /api/market/table 200."""
    name = "e) GET /api/market/table"
    try:
        r = client.get("/api/market/table")
        if r.status_code != 200:
            _record(name, False, f"status={r.status_code}")
            return
        body = r.json()
        # bonds/equities/fx 섹션 합산 행 개수(있으면) 출력.
        sections = {k: len(v) for k, v in body.items() if isinstance(v, list)} if isinstance(body, dict) else {}
        _record(name, True, f"status=200 sections={sections}")
    except Exception as e:
        _record(name, False, f"exception={e!r}")


def check_seed_file() -> None:
    """추가: seed 폴백 파일(samsung.json) 존재 + reports 9개 확인."""
    name = "seed) committee_runs/seed/samsung.json"
    try:
        import json
        seed = BACKEND_ROOT / "data" / "committee_runs" / "seed" / "samsung.json"
        if not seed.exists():
            _record(name, False, "파일 없음")
            return
        data = json.loads(seed.read_text(encoding="utf-8"))
        reports = data.get("reports", {}) if isinstance(data, dict) else {}
        decision = data.get("decision") if isinstance(data, dict) else None
        passed = len(reports) >= 7 and bool(decision)
        _record(name, passed, f"decision={decision} reports={len(reports)}")
    except Exception as e:
        _record(name, False, f"exception={e!r}")


def main() -> int:
    print("=" * 60)
    print("AI Investment Desk OS - 5탭 스모크 테스트")
    print("=" * 60)

    check_kpi()
    check_pnl()
    check_snapshot()
    check_committee_latest()
    check_market_table()
    check_seed_file()

    print("-" * 60)
    passed = sum(1 for _, ok, _ in _results if ok)
    total = len(_results)
    print(f"결과: {passed}/{total} PASS")
    failed = [n for n, ok, _ in _results if not ok]
    if failed:
        print("FAIL 항목: " + ", ".join(failed))
    print("=" * 60)
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
