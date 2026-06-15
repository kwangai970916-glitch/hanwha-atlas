# -*- coding: utf-8 -*-
"""
장중(아침시황) Page 1 본문 생성기 — 08.아침시황 원본 generate_analysis_text의 포팅.

원본의 '섹터당 3줄' 결정론 서술을 재현하되, 섹터 구성과 종목 등락률을 '내재화'한다:
  - 섹터 구성: GICS 11 대분류(홈 히트맵과 동일, 시총가중 등락률)
  - 대표 종목:  KOSPI 전종목 universe에서 각 GICS 섹터의 시총 상위 종목을
               실제 등락률과 함께 직접 추출(하드코딩 매핑 없음 = 완전 내재화).

Page 1 본문에는 지수 기여도를 쓰지 않는다(원본 규칙). 기여도는 Page 2 표에만.
sector_reps는 run_intraday에서 to_major_sector로 버킷팅해 만들어 주입한다.
"""
from __future__ import annotations

from typing import Any


# GICS 11 대분류별 헤더 이슈(섹터 성격 요약)
HEADER_ISSUE: dict[str, str] = {
    "정보기술":     "반도체·AI 모멘텀과 차익실현 교차",
    "산업재":       "조선·방산·기계 수주 모멘텀",
    "금융":         "금리·환율 레벨과 밸류에이션 부담",
    "경기소비재":   "완성차 환율 효과와 수요 점검",
    "소재":         "중국 경기와 원자재 가격 변동",
    "커뮤니케이션": "플랫폼 실적과 AI 투자 사이클",
    "헬스케어":     "성장주 모멘텀과 파이프라인 기대",
    "에너지":       "국제 유가와 정제마진 흐름",
    "필수소비재":   "방어 수요와 가격 전가력",
    "유틸리티":     "전력 수요와 요금 정책",
    "부동산":       "금리 레벨과 임대 수익률",
}

# GICS 11 대분류별 당일 원인 fallback
CAUSE_FALLBACK: dict[str, str] = {
    "정보기술":     "HBM·메모리 업황 기대와 외국인 수급, 필라델피아 반도체 지수 흐름이 방향을 좌우.",
    "산업재":       "조선·방산 수주 모멘텀과 AI 데이터센터 전력 수요 기대가 수급을 견인.",
    "금융":         "환율과 금리 레벨 부담 속 밸류에이션 매력과 위험회피가 교차.",
    "경기소비재":   "원/달러 환율 효과와 미국·중국 수요 점검이 완성차·소비주 방향을 결정.",
    "소재":         "중국 부양 기대와 원자재 가격 변동이 철강·화학 수급을 좌우.",
    "커뮤니케이션": "플랫폼 실적 기대와 AI 투자 사이클, 광고 업황이 방향을 가름.",
    "헬스케어":     "성장주 전반의 리스크 선호 변화 속 개별 파이프라인 모멘텀 차별화.",
    "에너지":       "국제 유가와 정제마진, 배당 매력이 수급을 좌우.",
    "필수소비재":   "방어 수요와 원가·환율 전가력이 가격을 결정.",
    "유틸리티":     "전력 수요 증가 기대와 요금·연료비 정책이 교차.",
    "부동산":       "금리 레벨과 임대 수익률, 리츠 배당 매력이 방향을 결정.",
}


def _fmt_pct(v: Any) -> str:
    return f"{v:+.2f}%" if isinstance(v, (int, float)) else "0.00%"


def generate_intraday_analysis_text(
    *,
    indices: dict,
    breadth: dict,
    kosdaq_breadth: dict,
    sectors: list[dict],          # GICS 11 [{sector, change}] (시총가중)
    sector_reps: dict,            # {gics_sector: [{name, change}, ...]} (시총 상위)
    usdkrw: float | None = None,
    macro_text: str | None = None,
) -> str:
    """원본 '섹터당 3줄' 본문을 GICS 섹터 + 전종목 universe 대표종목으로 생성."""
    kospi = (indices or {}).get("kospi", {})
    kosdaq = (indices or {}).get("kosdaq", {})
    kospi_index = float(kospi.get("index", 0) or 0)
    kospi_chg = float(kospi.get("change", 0) or 0)
    kosdaq_index = float(kosdaq.get("index", 0) or 0)
    kosdaq_chg = float(kosdaq.get("change", 0) or 0)

    kospi_adv = int((breadth or {}).get("up", 0) or 0)
    kospi_dec = int((breadth or {}).get("down", 0) or 0)
    kosdaq_adv = int((kosdaq_breadth or {}).get("up", 0) or 0)
    kosdaq_dec = int((kosdaq_breadth or {}).get("down", 0) or 0)

    # '기타'(ETF 등) 제외, 시총가중 등락률순 정렬
    ranked = sorted(
        [s for s in (sectors or []) if s.get("sector") and s.get("sector") != "기타"],
        key=lambda x: float(x.get("change", 0) or 0),
        reverse=True,
    )
    sector_change = {s["sector"]: float(s.get("change", 0) or 0) for s in ranked}

    # 선택: 강세 3 + 약세 2 (주도주/소외주 대비) — 원본의 상·하위 대비 정신 유지
    selected: list[str] = []
    for s in ranked[:3]:
        selected.append(s["sector"])
    for s in reversed(ranked):
        if s["sector"] not in selected:
            selected.append(s["sector"])
        if len(selected) >= 5:
            break
    selected = selected[:5]

    def reps_line(sector: str) -> tuple[str, str]:
        reps = (sector_reps or {}).get(sector, [])[:4]
        picks = [f"{r.get('name','')}({_fmt_pct(float(r.get('change', 0) or 0))})" for r in reps if r.get("name")]
        if not picks:
            return "", "혼조"
        vals = [float(r.get("change", 0) or 0) for r in reps]
        tone = "동반 강세" if all(v >= 0 for v in vals) else "동반 약세" if all(v < 0 for v in vals) else "혼조"
        return ", ".join(picks), tone

    if macro_text:
        macro = macro_text[:110] + ("..." if len(macro_text) > 110 else "")
    else:
        macro = "전일 미국 증시 흐름과 환율·금리 레벨을 반영해 위험선호를 점검."

    lines: list[str] = []
    lines.append("■ KOSPI 장중 시황")
    lines.append(
        f"- KOSPI {kospi_index:,.2f}pt, {_fmt_pct(kospi_chg)}. "
        f"KOSDAQ {kosdaq_index:,.2f}pt, {_fmt_pct(kosdaq_chg)}. "
        + ("지수와 종목 온도가 함께 개선된 장세." if kospi_chg >= 0 else "지수보다 종목 체감이 더 약한 장세.")
    )
    lines.append(
        f"- 코스피 상승 {kospi_adv}개·하락 {kospi_dec}개, "
        f"코스닥 상승 {kosdaq_adv}개·하락 {kosdaq_dec}개. "
        + ("시장 폭 양호." if kospi_adv >= kospi_dec else "시장 폭 급랭.")
    )
    lines.append(f"- {macro}")
    lines.append("- 본문은 GICS 대분류 섹터의 시총가중 등락률·대표 종목 흐름 중심으로 해석.")
    lines.append("")

    for sector in selected:
        change = sector_change.get(sector)
        stocks, tone = reps_line(sector)
        issue = HEADER_ISSUE.get(sector, "당일 수급 재배치")

        lines.append(f"■ {sector}({_fmt_pct(change)}), {issue}")
        if stocks:
            lines.append(f"- {stocks} {tone}. 섹터 시총가중 수익률 {_fmt_pct(change)}.")
        else:
            lines.append(f"- 섹터 시총가중 수익률 {_fmt_pct(change)}. 대표 종목 수급 편차 확대.")

        cause = CAUSE_FALLBACK.get(sector, "수급 공백과 이벤트 부재로 방향성 제한.")
        if usdkrw and sector in ("금융", "경기소비재", "소재"):
            cause = cause.rstrip(".") + f". 원/달러 {usdkrw:,.1f}원 레벨 병존."
        lines.append(f"- 당일 원인: {cause}")

        if (change or 0) < 0:
            lines.append("- 의미: 낙폭 자체보다 약세가 하루 이벤트인지 수급 이탈인지 확인 필요.")
        else:
            lines.append("- 의미: 강세 지속 여부는 후속 수급·거래대금으로 확인 필요.")
        lines.append("")

    return "\n".join(lines).strip()
