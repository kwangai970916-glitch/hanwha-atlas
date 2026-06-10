from __future__ import annotations
import datetime as dt
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict

KST = dt.timezone(dt.timedelta(hours=9))

# stage -> (step 0-5, 한국어 label). 프론트 4단계 진행카드/STAGE_TO_PHASE와 매핑.
STAGE_META: Dict[str, tuple] = {
    'starting':      (0, '시작 중'),
    'discovery':     (1, '사전조사·발굴 중'),
    'sector_debate': (2, '섹터 라운드테이블 토론 중'),
    'nomination':    (3, '종목 상정 중'),
    'risk_review':   (4, '리스크 사전심의 중'),
    'decision':      (5, 'PM 의장 최종선정 중'),
    'done':          (5, '회의 완료'),
    'error':         (0, '오류 발생'),
}


def iso_now() -> str:
    return dt.datetime.now(KST).isoformat(timespec='seconds')


class RunStream:
    """단일 job의 messages.jsonl / status.json / decision.json 기록기.

    orchestrator 스레드가 단독 소유한다(동시 쓰기 없음). idx는 emit마다 단조 증가.
    """

    def __init__(self, out_dir: Path | str):
        self.out_dir = Path(out_dir)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self._idx = 0
        self._msg_path = self.out_dir / 'messages.jsonl'
        self._status_path = self.out_dir / 'status.json'
        self._decision_path = self.out_dir / 'decision.json'

    @property
    def idx(self) -> int:
        return self._idx

    def emit(self, agent: str, stage: str, text: str, icon: str = 'message',
             source: str = 'rules') -> None:
        msg = {
            'idx': self._idx, 'ts': iso_now(), 'agent': agent, 'stage': stage,
            'text': (text or '').strip()[:240], 'icon': icon, 'source': source,
        }
        with self._msg_path.open('a', encoding='utf-8') as f:
            f.write(json.dumps(msg, ensure_ascii=False) + '\n')
        self._idx += 1

    def _atomic_write(self, path: Path, content: str) -> None:
        """temp 파일로 쓴 뒤 os.replace로 원자적 교체.
        Windows에서 대상 파일이 잠긴 경우 직접 write_text로 폴백."""
        try:
            fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), suffix='.tmp')
            try:
                os.write(fd, content.encode('utf-8'))
            finally:
                os.close(fd)
            os.replace(tmp_path, str(path))
        except OSError:
            # Windows 잠금 등으로 replace 실패 시 직접 쓰기로 폴백
            try:
                os.unlink(tmp_path)
            except Exception:
                pass
            path.write_text(content, encoding='utf-8')

    def set_stage(self, stage: str, **extra: Any) -> None:
        step, label = STAGE_META.get(stage, (0, stage))
        payload = {'stage': stage, 'stage_label': label, 'step': step, 'ts': iso_now()}
        payload.update(extra)
        self._atomic_write(self._status_path, json.dumps(payload, ensure_ascii=False))

    def write_decision(self, decision: Dict[str, Any]) -> None:
        self._atomic_write(
            self._decision_path,
            json.dumps(decision, ensure_ascii=False, indent=2)
        )
