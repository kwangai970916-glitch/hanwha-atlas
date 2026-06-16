from __future__ import annotations
import sys, os, glob, importlib, json, time
from pathlib import Path

SITELE_DIR = Path(__file__).resolve().parents[1] / "sitele"
REPO_ROOT = Path(__file__).resolve().parents[2]
# 슬롯별 전체 결과를 디스크에 영속화 → 재배포/재시작 후에도 24h 복원(영구 볼륨과 결합).
_SLOT_CACHE_DIR = Path(__file__).resolve().parents[1] / "data" / "briefing_cache"
_SLOT_MAX_AGE = 86400


def save_slot_cache(slot: str, out: dict) -> None:
    """성공한 슬롯 결과 전체(report/sections/png/interactive)를 디스크에 저장."""
    try:
        if not (isinstance(out, dict) and out.get("success")):
            return
        _SLOT_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        rec = dict(out)
        rec.setdefault("_cached_at", time.time())
        (_SLOT_CACHE_DIR / f"{slot}.json").write_text(
            json.dumps(rec, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def load_slot_cache(slot: str, max_age: float = _SLOT_MAX_AGE) -> "dict | None":
    """24h 이내 디스크 저장 슬롯 결과를 복원(없으면 None)."""
    try:
        p = _SLOT_CACHE_DIR / f"{slot}.json"
        if not p.exists():
            return None
        rec = json.loads(p.read_text(encoding="utf-8"))
        ts = float(rec.get("_cached_at") or 0)
        if rec.get("success") and ts and (time.time() - ts) < max_age:
            return rec
    except Exception:
        pass
    return None
# 위원회 엔진 쪽에 실제 키가 들어있는 .env (MIMO/ANTHROPIC/OPENAI/ALPHA_VANTAGE 등)
COMMITTEE_ENV = REPO_ROOT / "committee_engine" / "TradingAgents" / ".env"

# slot -> 신형 실행 모듈명
_SLOT_MODULES = {
    "premarket": "run_premarket",
    "intraday":  "run_intraday",
    "close":     "run_close",
}

# 가장 최근 성공한 시황 결과(전체 dict) — 홈 '최신 시황' 팝업/위젯용 인메모리 캐시.
_LATEST_RESULT: "dict | None" = None


def _set_latest(out: dict) -> None:
    global _LATEST_RESULT
    _LATEST_RESULT = out


def get_latest_briefing() -> dict:
    """최신 시황 결과 반환. 이번 세션에 생성된 전체 결과가 있으면 그대로,
    없으면 발송 이력(png/요약)으로 최소 폴백. 둘 다 없으면 available=False."""
    if _LATEST_RESULT:
        return _LATEST_RESULT
    # 디스크 슬롯 캐시(재배포 후에도 24h 복원) — 가장 최근 것
    newest = None
    for s in ("premarket", "intraday", "close"):
        rec = load_slot_cache(s)
        if rec and (newest is None or
                    float(rec.get("_cached_at", 0)) > float(newest.get("_cached_at", 0))):
            newest = rec
    if newest:
        return newest
    try:
        from app.briefing_history import list_history
    except Exception:
        try:
            from .briefing_history import list_history  # type: ignore
        except Exception:
            list_history = None  # type: ignore
    if list_history is not None:
        try:
            recs = list_history(limit=1)
            if recs:
                r = recs[0]
                return {
                    "available": True, "from_history": True,
                    "slot": r.get("slot"), "png_path": r.get("png_path"),
                    "decision_summary": r.get("decision_summary"), "ts": r.get("ts"),
                    "sections": None,
                }
        except Exception:
            pass
    return {"available": False}


def _ensure_path():
    p = str(SITELE_DIR)
    if p not in sys.path:
        sys.path.insert(0, p)


def _inject_committee_keys() -> dict:
    """
    committee_engine/TradingAgents/.env 의 KEY=VALUE 를 os.environ 에 주입.
    - 시황 LLM 텍스트(generate_report_sections)가 fallback 껍데기가 아니라
      실제 생성되도록 ANTHROPIC/OPENAI/MIMO 등 키를 미리 환경에 올린다.
    - 값이 비어있는 키는 건너뛴다(공란으로 기존 환경을 덮어쓰지 않음).
    - 파일이 없거나 읽기 실패해도 graceful (조용히 무시).
    반환: 주입된(또는 이미 존재하는) 키 이름 목록을 담은 진단용 dict.
    """
    injected = []
    present = []
    try:
        if not COMMITTEE_ENV.exists():
            return {"env_file": str(COMMITTEE_ENV), "found": False, "injected": [], "present": []}
        for raw_line in COMMITTEE_ENV.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if not key:
                continue
            if not value:
                # 공란 키는 주입하지 않음 (graceful)
                continue
            # 이미 환경에 (비어있지 않게) 있으면 존중, 아니면 주입
            if os.environ.get(key, "").strip():
                present.append(key)
            else:
                os.environ[key] = value
                injected.append(key)
    except Exception:
        # 키 주입 단계 실패는 치명적이지 않음 — 모듈이 자체 fallback 처리
        pass
    return {
        "env_file": str(COMMITTEE_ENV),
        "found": True,
        "injected": injected,
        "present": present,
    }


def _load_adr_history(limit: int = 60) -> list:
    """
    sitele/adr_history.json (없으면 backend/adr_history.json) 에서 최근 ADR 시계열 로드.
    프론트 ADR 차트용. 최신 limit 개만 반환. 없거나 실패 시 [].
    """
    candidates = [
        SITELE_DIR / "adr_history.json",
        REPO_ROOT / "backend" / "adr_history.json",
    ]
    for path in candidates:
        try:
            if not path.exists():
                continue
            import json as _json
            data = _json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, list) and data:
                # kospi/kosdaq ADR 값을 가진 항목만 추려 차트 친화적으로 정리
                series = []
                for row in data:
                    if not isinstance(row, dict):
                        continue
                    entry = {"date": row.get("date")}
                    if "kospi" in row:
                        entry["kospi"] = row.get("kospi")
                    if "kosdaq" in row:
                        entry["kosdaq"] = row.get("kosdaq")
                    # breadth(등락 종목수) 항목도 함께 보존
                    for k in ("kospi_adv", "kospi_dec", "kosdaq_adv", "kosdaq_dec"):
                        if k in row:
                            entry[k] = row.get(k)
                    series.append(entry)
                if limit and limit > 0:
                    return series[-limit:]
                return series
        except Exception:
            continue
    return []


def _build_interactive_data() -> dict:
    """
    프론트 인터랙티브 차트용 데이터 묶음.
    auto_data_fetcher.get_complete_report_data() 를 호출해
    RS 4분면(kospi/kosdaq), 섹터 등락률, ADR, 등락 종목수, 상·하위 종목, 뉴스를 추출.

    실패하거나 휴장이면 가능한 부분만 채우고 나머지는 graceful 하게 비움.
    네트워크 호출이 포함되어 수 초~수십 초 소요될 수 있음.
    """
    interactive: dict = {
        "rs_kospi": [],       # RS 4분면 (KOSPI 섹터)
        "rs_kosdaq": [],      # RS 4분면 (KOSDAQ 섹터)
        "sector_returns": [], # KOSPI 섹터 등락률
        "kosdaq_sectors": [], # KOSDAQ 섹터 등락률
        "theme_returns": [],        # KOSPI 주도 테마 집계
        "kosdaq_theme_returns": [], # KOSDAQ 주도 테마 집계
        "adr_history": [],    # ADR 시계열 (차트)
        "adr_latest": {},     # 최신 ADR 1건
        "breadth": {},        # 등락 종목수 (KOSPI/KOSDAQ)
        "top_gainers": [],
        "top_losers": [],
        "news_headlines": [],
        "market_indices": {},
    }
    # 주도 테마 분류 함수 — sitele/theme_taxonomy.py (실패 시 graceful)
    def _agg_theme(sector_list: list) -> list:
        try:
            _sitele = str(SITELE_DIR)
            if _sitele not in sys.path:
                sys.path.insert(0, _sitele)
            from theme_taxonomy import aggregate_theme_returns
            return aggregate_theme_returns(sector_list)
        except Exception:
            return []

    try:
        import auto_data_fetcher as adf
        report = adf.get_complete_report_data()
        if isinstance(report, dict):
            interactive["rs_kospi"] = report.get("rsData", []) or []
            interactive["rs_kosdaq"] = report.get("kosdaqRsData", []) or []
            interactive["sector_returns"] = report.get("sectorReturns", []) or []
            interactive["kosdaq_sectors"] = report.get("kosdaqSectors", []) or []
            interactive["top_gainers"] = report.get("topGainers", []) or []
            interactive["top_losers"] = report.get("topLosers", []) or []
            interactive["news_headlines"] = report.get("newsHeadlines", []) or []
            interactive["market_indices"] = report.get("marketIndices", {}) or {}
            adr = report.get("adrData", []) or []
            if adr:
                interactive["adr_latest"] = adr[-1] if isinstance(adr[-1], dict) else {}
            interactive["breadth"] = {
                "kospi": {
                    "advance": report.get("kospiAdvance"),
                    "decline": report.get("kospiDecline"),
                    "unchanged": report.get("kospiUnchanged"),
                    "total": report.get("kospiTotal"),
                },
                "kosdaq": {
                    "advance": report.get("kosdaqAdvance"),
                    "decline": report.get("kosdaqDecline"),
                    "unchanged": report.get("kosdaqUnchanged"),
                    "total": report.get("kosdaqTotal"),
                },
            }
            # 주도 테마 집계 (theme_taxonomy)
            interactive["theme_returns"] = _agg_theme(interactive["sector_returns"])
            interactive["kosdaq_theme_returns"] = _agg_theme(interactive["kosdaq_sectors"])
    except Exception as e:
        interactive["error"] = f"interactive build 실패: {e}"

    # ADR 시계열은 파일에서 직접 로드(휴장/네트워크 실패와 무관하게 표시 가능)
    interactive["adr_history"] = _load_adr_history()
    if not interactive.get("adr_latest") and interactive["adr_history"]:
        last = interactive["adr_history"][-1]
        if isinstance(last, dict):
            interactive["adr_latest"] = last
    return interactive


def _summarize_decision(sections) -> str:
    """sections 에서 카운트다운/이력용 한 줄 요약 생성."""
    if not isinstance(sections, dict):
        return ""
    title = str(sections.get("title", "") or "").strip()
    stance = str(sections.get("stance", "") or "").strip()
    if title and stance:
        return f"{stance} · {title}"
    return title or stance or ""


def _latest_png(slot: str) -> str:
    """
    sitele/output/{yyyymmdd}/hanwha_{slot}_*.png 중 최신 PNG 경로를 반환.
    날짜 폴더가 여러 개일 수 있으니 전체 output 트리에서 슬롯 매칭 최신본을 찾는다.
    """
    candidates = []
    out_root = SITELE_DIR / "output"
    if out_root.exists():
        # slot 매칭 우선
        patterns = [
            str(out_root / "*" / f"hanwha_{slot}_*.png"),
            str(out_root / f"hanwha_{slot}_*.png"),
        ]
        for pat in patterns:
            candidates.extend(glob.glob(pat))
        if not candidates:
            # 슬롯 못 찾으면 아무 PNG라도 최신본
            candidates.extend(glob.glob(str(out_root / "*" / "*.png")))
            candidates.extend(glob.glob(str(out_root / "*.png")))
    if not candidates:
        return ""
    try:
        return max(candidates, key=os.path.getmtime)
    except Exception:
        return candidates[-1]


def _latest_png_set(slot: str) -> list:
    out_root = SITELE_DIR / "output"
    pats = [str(out_root / "*" / f"*{slot}*_page*.png"),
            str(out_root / "*" / f"hanwha_{slot}_*.png")]
    files = []
    for p in pats:
        files.extend(glob.glob(p))
    files = sorted(set(files), key=os.path.getmtime, reverse=True)
    # 최신 배치의 page 파일들을 고른 뒤, 표시 순서는 page1→page3 오름차순으로 정렬
    import re as _re
    pages = [f for f in files if "_page" in f][:3]

    def _pageno(f: str) -> int:
        m = _re.search(r"_page(\d+)", f)
        return int(m.group(1)) if m else 0

    pages.sort(key=_pageno)
    chosen = pages or files[:1]
    return [os.path.abspath(f) for f in chosen]


def run_briefing(slot: str) -> dict:
    """
    시황 브리핑 실행기.

    slot in {'premarket','intraday','close'} → 각각 신형 모듈
    run_premarket / run_intraday / run_close 의 main(send=False, test_only=True) 호출.

    반환 dict:
      success     : bool
      slot        : 입력 슬롯
      png_path    : 생성된 리포트 PNG 절대경로 (없으면 "")
      sections    : generate_report_sections() 산출(LLM 시황 9섹션 텍스트) — 캡처 성공 시 포함
                    (title/stance/key_issue/bull_case/bear_case/macro_flow/kr_outlook/strategy/news_flow)
      market_data : generate_report_sections() 에 전달된 슬롯별 시장 데이터 — 캡처 성공 시 포함
      interactive : 프론트 인터랙티브 차트용 데이터 묶음
                    (rs_kospi/rs_kosdaq RS 4분면, sector_returns/kosdaq_sectors 섹터,
                     adr_history/adr_latest ADR, breadth 등락종목수, top_gainers/top_losers, news_headlines)
      keys        : 주입된 키 진단 정보
      error       : 실패 시 사유
    """
    if slot not in _SLOT_MODULES:
        return {
            "success": False,
            "slot": slot,
            "error": f"알 수 없는 슬롯: {slot!r} (premarket/intraday/close 중 선택)",
            "png_path": "",
        }

    _ensure_path()
    # 키 주입은 모듈 import / 실행 전에 수행 (LLM 경로가 키를 읽도록)
    keys_info = _inject_committee_keys()

    prev_cwd = os.getcwd()
    captured = {"sections": None, "market_data": None, "report": None}
    try:
        # 신형 모듈은 import 시 module-level 에서 자체적으로 os.chdir(HERE) 를 수행하므로
        # 여기서 굳이 먼저 chdir 하지 않아도 되지만, 일관성을 위해 sitele 로 이동.
        os.chdir(str(SITELE_DIR))

        mod_name = _SLOT_MODULES[slot]
        mod = importlib.import_module(mod_name)

        # main() 은 png_path 만 반환하고 sections 는 돌려주지 않으므로,
        # 모듈 네임스페이스의 generate_report_sections 를 래핑해 실제 산출물을 캡처한다.
        # (재실행/재네트워크 호출 없이 main() 내부 결과를 그대로 가로챔)
        orig_gen = getattr(mod, "generate_report_sections", None)
        if callable(orig_gen):
            def _capturing_gen(*args, **kwargs):
                res = orig_gen(*args, **kwargs)
                try:
                    if isinstance(res, dict):
                        captured["report"] = res
                        # backward compat: keep sections pointing at the same envelope
                        captured["sections"] = res
                    # generate_report_sections(slot, market_data) → 2번째 인자가 market_data
                    md = kwargs.get("market_data")
                    if md is None and len(args) >= 2:
                        md = args[1]
                    if isinstance(md, dict):
                        captured["market_data"] = md
                except Exception:
                    pass
                return res
            try:
                mod.generate_report_sections = _capturing_gen  # type: ignore[attr-defined]
            except Exception:
                orig_gen = None  # 래핑 실패 시 원복 불필요 표시

        try:
            result = mod.main(send=False, test_only=True)
        finally:
            # 래핑한 경우 원복
            if callable(orig_gen):
                try:
                    mod.generate_report_sections = orig_gen  # type: ignore[attr-defined]
                except Exception:
                    pass

        # main() 이 png_path 를 반환할 수도, None 일 수도 있음 → 양쪽 모두 대비
        png_path = ""
        if result and isinstance(result, str) and os.path.exists(result):
            png_path = os.path.abspath(result)
        else:
            found = _latest_png(slot)
            if found:
                png_path = os.path.abspath(found)

        # 프론트 인터랙티브 차트용 데이터(RS 4분면·섹터·ADR·등락 종목수·뉴스)
        try:
            interactive = _build_interactive_data()
        except Exception as e:
            interactive = {"error": f"interactive build 실패: {e}"}

        out = {
            "success": True,
            "slot": slot,
            "png_path": png_path,
            "png_paths": _latest_png_set(slot),
            "keys": keys_info,
            "interactive": interactive,
        }
        if captured["report"] is not None:
            out["report"] = captured["report"]
            out["sections"] = captured["report"].get("legacy")
        elif captured["sections"] is not None:
            out["sections"] = captured["sections"]
        if captured["market_data"] is not None:
            out["market_data"] = captured["market_data"]

        # 생성 이력 append (실패해도 본 응답에는 영향 없음)
        try:
            from app.briefing_history import append_history
        except Exception:
            try:
                from .briefing_history import append_history  # type: ignore
            except Exception:
                append_history = None  # type: ignore
        if append_history is not None:
            try:
                append_history(
                    slot=slot,
                    png_path=png_path,
                    decision_summary=_summarize_decision(captured.get("report") or captured.get("sections")),
                    success=True,
                )
            except Exception:
                pass

        _set_latest(out)
        save_slot_cache(slot, out)
        return out

    except Exception as e:
        import traceback
        return {
            "success": False,
            "slot": slot,
            "error": str(e),
            "trace": traceback.format_exc()[-1500:],
            "png_path": "",
            "keys": keys_info,
        }
    finally:
        # 모듈이 바꾼 cwd 복원
        try:
            os.chdir(prev_cwd)
        except Exception:
            os.chdir(str(REPO_ROOT))
