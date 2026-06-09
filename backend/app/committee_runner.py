# backend/app/committee_runner.py
"""TradingAgents 위원회를 subprocess로 실행/추적한다."""
from __future__ import annotations
import json, subprocess, threading, datetime as dt
from pathlib import Path

# 격리 복사본을 사용한다. 원본 (20260115)CLAUDE AI INVESTMENT COMITIEE 프로젝트는 건드리지 않는다.
TA_DIR = Path(__file__).resolve().parents[2] / "committee_engine" / "TradingAgents"
TA_PY  = TA_DIR / ".venv" / "Scripts" / "python.exe"
OUT_ROOT = Path(__file__).resolve().parents[1] / "data" / "committee_runs"

_jobs: dict[str, dict] = {}   # job_id -> {ticker, status, out_dir}


def _job_id(ticker: str) -> str:
    return f"{ticker.replace('.', '_')}_{dt.datetime.now():%Y%m%d_%H%M%S}"


def start_run(ticker: str, date: str | None = None) -> dict:
    date = date or dt.date.today().isoformat()
    jid = _job_id(ticker)
    out_dir = OUT_ROOT / jid
    out_dir.mkdir(parents=True, exist_ok=True)
    _jobs[jid] = {"ticker": ticker, "status": "starting", "out_dir": str(out_dir)}

    def _run():
        _jobs[jid]["status"] = "running"
        sp = out_dir / "status.json"
        try:
            proc = subprocess.run(
                [str(TA_PY), "run_committee.py", ticker, date, str(out_dir)],
                cwd=str(TA_DIR), capture_output=True, text=True, timeout=900,
            )
            # 서브프로세스가 status.json(done/error)을 못 남기고 죽은 경우 방어
            wrote_terminal = False
            if sp.exists():
                try:
                    wrote_terminal = json.loads(sp.read_text(encoding="utf-8")).get("stage") in ("done", "error")
                except Exception:
                    wrote_terminal = False
            if not wrote_terminal and proc.returncode != 0:
                sp.write_text(json.dumps(
                    {"stage": "error", "error": f"exit {proc.returncode}",
                     "stderr": (proc.stderr or "")[-1500:]}, ensure_ascii=False), encoding="utf-8")
        except Exception as e:
            sp.write_text(json.dumps({"stage": "error", "error": str(e)},
                                     ensure_ascii=False), encoding="utf-8")
        _jobs[jid]["status"] = "finished"

    threading.Thread(target=_run, daemon=True).start()
    return {"job_id": jid, "ticker": ticker, "date": date}


def get_status(job_id: str) -> dict:
    job = _jobs.get(job_id)
    if not job:
        return {"stage": "unknown", "job_id": job_id}
    sp = Path(job["out_dir"]) / "status.json"
    if sp.exists():
        try:
            return {**json.loads(sp.read_text(encoding="utf-8")), "job_id": job_id}
        except Exception:
            pass
    return {"stage": job["status"], "job_id": job_id}


def get_messages(job_id: str, since: int = 0) -> dict:
    """실행 중 에이전트 멘트 스트림 (since 이상 idx만 반환)."""
    job = _jobs.get(job_id)
    if not job:
        return {"messages": [], "total": 0}
    mp = Path(job["out_dir"]) / "messages.jsonl"
    if not mp.exists():
        return {"messages": [], "total": 0}
    messages = []
    try:
        for line in mp.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                m = json.loads(line)
                if int(m.get("idx", 0)) >= since:
                    messages.append(m)
            except Exception:
                pass
    except Exception:
        pass
    return {"messages": messages, "total": len(messages) + since}


def get_result(job_id: str) -> dict:
    job = _jobs.get(job_id)
    if not job:
        return {"error": "unknown job"}
    dp = Path(job["out_dir"]) / "decision.json"
    if not dp.exists():
        return {"error": "not ready"}
    return json.loads(dp.read_text(encoding="utf-8"))


SEED_DIR = OUT_ROOT / "seed"


def _dir_is_done(d: Path) -> bool:
    """해당 잡 디렉터리가 완료(status.stage=done)+결과(decision.json) 모두 갖췄는지."""
    dp = d / "decision.json"
    sp = d / "status.json"
    if not dp.exists() or not sp.exists():
        return False
    try:
        return json.loads(sp.read_text(encoding="utf-8")).get("stage") == "done"
    except Exception:
        return False


def _shape_result(payload: dict, is_seed: bool) -> dict:
    """decision.json 페이로드를 latest API 반환형으로 정규화.

    반환: {ticker, input, decision, reports, is_seed}
      - reports 는 항상 dict (없으면 {}).
    """
    reports = payload.get("reports")
    if not isinstance(reports, dict):
        reports = {}
    # 신규 run_committee는 language=ko로 저장된다. 과거 seed가 영문이면
    # 홈/위젯에 영어 산출물이 노출되지 않도록 최소 한국어 안내로 대체한다.
    language = payload.get("language")
    if is_seed and language != "ko":
        raw_decision = str(payload.get("decision") or "").upper()
        ko_decision = {
            "BUY": "매수(BUY)",
            "SELL": "매도(SELL)",
            "HOLD": "보유(HOLD)",
        }.get(raw_decision, str(payload.get("decision") or "보류(HOLD)"))
        reports = {
            "final_trade_decision": (
                f"## 최종 결정\n\n{ko_decision}\n\n"
                "과거 seed 리포트는 영문으로 생성된 샘플이므로 표시하지 않습니다. "
                "상단의 [위원회 소집]을 실행하면 모든 세부 리포트가 한국어로 생성됩니다."
            )
        }
    else:
        ko_decision = payload.get("decision")
    return {
        "ticker": payload.get("ticker"),
        "input": payload.get("input"),
        "decision": ko_decision,
        "reports": reports,
        "is_seed": is_seed,
        "language": "ko" if is_seed and language != "ko" else language,
    }


def get_latest_result() -> dict:
    """가장 최근 done 잡의 decision.json 을 latest 반환형으로 돌려준다.

    탐색 순서:
      1) 라이브: 현재 서버 세션이 시작/추적한 잡(_jobs) 중 status.json(stage=done) +
         decision.json 을 모두 갖춘 잡 디렉터리 중 가장 최근(mtime) 것.
         (서버 프로세스 밖, 예: 독립 `python -c` 호출에서는 _jobs 가 비어 있으므로
          라이브 결과가 없는 것으로 간주되어 seed 로 폴백한다.)
      2) 폴백: 라이브 done 잡이 없으면 seed(samsung.json) 반환(is_seed=True).
      3) 둘 다 없으면 {"available": False}.

    반환: {ticker, input, decision, reports, is_seed} 또는 {"available": False}.
    """
    # 1) 라이브 done 잡 (이 세션이 추적 중인 _jobs 기준, mtime 내림차순)
    try:
        live_dirs = [
            Path(job["out_dir"]) for job in _jobs.values()
            if job.get("out_dir")
        ]
        done_dirs = [d for d in live_dirs if d.is_dir() and _dir_is_done(d)]
        done_dirs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        for d in done_dirs:
            try:
                payload = json.loads((d / "decision.json").read_text(encoding="utf-8"))
                return _shape_result(payload, is_seed=False)
            except Exception:
                continue
    except Exception:
        pass

    # 2) seed 폴백
    seed_path = SEED_DIR / "samsung.json"
    if seed_path.exists():
        try:
            payload = json.loads(seed_path.read_text(encoding="utf-8"))
            return _shape_result(payload, is_seed=True)
        except Exception:
            pass

    # 3) 아무것도 없음
    return {"available": False}
