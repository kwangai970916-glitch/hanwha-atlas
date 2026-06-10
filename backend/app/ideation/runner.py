from __future__ import annotations
import datetime as dt
import json
import threading
import traceback
from pathlib import Path
from typing import Any, Dict

from .orchestrator import run_committee
from .stream import RunStream

OUT_ROOT = Path(__file__).resolve().parents[2] / 'data' / 'idea_committee_runs'
SEED_DIR = OUT_ROOT / 'seed'
WATCHDOG_SEC = 600
MAX_DONE_JOBS = 50

_jobs: Dict[str, Dict[str, Any]] = {}
_jobs_lock = threading.Lock()


def _job_id(keywords: str) -> str:
    slug = ''.join(ch for ch in (keywords or 'all') if ch.isalnum())[:12] or 'all'
    return f"{slug}_{dt.datetime.now():%Y%m%d_%H%M%S}"


def _evict_old_jobs() -> None:
    """완료된 잡이 MAX_DONE_JOBS를 넘으면 오래된 것부터 dict에서 제거 (디스크 파일은 남김)."""
    with _jobs_lock:
        done_ids = []
        for jid, job in list(_jobs.items()):
            sp = Path(job['out_dir']) / 'status.json'
            try:
                if sp.exists():
                    stage = json.loads(sp.read_text(encoding='utf-8')).get('stage')
                    if stage in ('done', 'error'):
                        done_ids.append(jid)
            except Exception:
                pass
        if len(done_ids) > MAX_DONE_JOBS:
            # mtime 기준 오래된 순 정렬
            done_ids.sort(key=lambda jid: Path(_jobs[jid]['out_dir']).stat().st_mtime
                          if Path(_jobs[jid]['out_dir']).exists() else 0)
            to_remove = done_ids[:len(done_ids) - MAX_DONE_JOBS]
            for jid in to_remove:
                _jobs.pop(jid, None)


def start_run(keywords: str, horizon_months: int = 3) -> Dict[str, Any]:
    jid = _job_id(keywords)
    out_dir = OUT_ROOT / jid
    stream = RunStream(out_dir)
    stream.set_stage('starting', keywords=keywords)
    with _jobs_lock:
        _jobs[jid] = {'keywords': keywords, 'out_dir': str(out_dir)}

    def _run():
        try:
            run_committee(keywords, horizon_months, stream)
        except Exception as e:
            stream.set_stage('error', keywords=keywords, error=str(e),
                             trace=traceback.format_exc()[-2000:])
        finally:
            _evict_old_jobs()

    t = threading.Thread(target=_run, daemon=True)
    t.start()

    def _watchdog():
        t.join(WATCHDOG_SEC)
        if t.is_alive():
            stream.set_stage('error', keywords=keywords,
                             error=f'watchdog timeout {WATCHDOG_SEC}s')
    threading.Thread(target=_watchdog, daemon=True).start()
    return {'job_id': jid, 'keywords': keywords}


def get_status(job_id: str) -> Dict[str, Any]:
    with _jobs_lock:
        job = _jobs.get(job_id)
    if not job:
        return {'stage': 'unknown', 'job_id': job_id}
    sp = Path(job['out_dir']) / 'status.json'
    if sp.exists():
        try:
            return {**json.loads(sp.read_text(encoding='utf-8')), 'job_id': job_id}
        except Exception:
            pass
    return {'stage': 'starting', 'job_id': job_id}


def get_messages(job_id: str, since: int = 0) -> Dict[str, Any]:
    with _jobs_lock:
        job = _jobs.get(job_id)
    if not job:
        return {'messages': [], 'total': 0}
    mp = Path(job['out_dir']) / 'messages.jsonl'
    if not mp.exists():
        return {'messages': [], 'total': 0}
    out = []
    try:
        for line in mp.read_text(encoding='utf-8').splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                m = json.loads(line)
                if int(m.get('idx', 0)) >= since:
                    out.append(m)
            except Exception:
                pass
    except Exception:
        pass
    return {'messages': out, 'total': len(out) + since}


def get_result(job_id: str) -> Dict[str, Any]:
    with _jobs_lock:
        job = _jobs.get(job_id)
    if not job:
        return {'error': 'unknown job'}
    dp = Path(job['out_dir']) / 'decision.json'
    if not dp.exists():
        return {'error': 'not ready'}
    return json.loads(dp.read_text(encoding='utf-8'))


def get_latest_result() -> Dict[str, Any]:
    """최근 done job → 없으면 seed 폴백(데모 빈화면 방지)."""
    try:
        done = []
        with _jobs_lock:
            jobs_snapshot = list(_jobs.values())
        for job in jobs_snapshot:
            d = Path(job['out_dir'])
            sp, dp = d / 'status.json', d / 'decision.json'
            if sp.exists() and dp.exists():
                try:
                    stg = json.loads(sp.read_text(encoding='utf-8')).get('stage')
                    if stg == 'done':
                        done.append(d)
                except Exception:
                    pass
        done.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        for d in done:
            try:
                return json.loads((d / 'decision.json').read_text(encoding='utf-8'))
            except Exception:
                continue
    except Exception:
        pass
    seeds = sorted(SEED_DIR.glob('*.json')) if SEED_DIR.exists() else []
    for sp in seeds:
        try:
            return json.loads(sp.read_text(encoding='utf-8'))
        except Exception:
            continue
    return {'available': False}
