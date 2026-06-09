"""오프라인 1회 실행으로 known-good decision.json을 seed로 저장.

실데이터/LLM이 있으면 그 결과를, 없으면 룰 폴백 결과를 저장한다(어느 쪽이든 유효).
get_latest_result()가 라이브 done 잡이 없을 때 이 seed로 폴백 → 데모 빈화면 방지.

실행: cd backend && python scripts/make_ideation_seed.py
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.ideation.stream import RunStream  # noqa: E402
from app.ideation.orchestrator import run_committee  # noqa: E402
from app.ideation.runner import SEED_DIR  # noqa: E402


def main() -> None:
    tmp = SEED_DIR.parent / '_seed_build'
    stream = RunStream(tmp)
    decision = run_committee('AI 반도체 전력망 방산', 3, stream)
    SEED_DIR.mkdir(parents=True, exist_ok=True)
    out = SEED_DIR / 'ideation_seed.json'
    out.write_text(json.dumps(decision, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'seed written: {out} | picks: {len(decision.get("top_picks", []))} '
          f'| minutes: {len(decision.get("committee_minutes", []))} '
          f'| source: {decision.get("data_quality", {}).get("mode")}')


if __name__ == '__main__':
    main()
