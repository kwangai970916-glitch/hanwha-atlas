from __future__ import annotations

from typing import Any, Literal, Optional
from pydantic import BaseModel, Field

DISCLAIMER = "본 자료는 내부 참고용으로, 투자 판단의 보조자료입니다. 최종 투자 의사결정은 담당 운용역의 판단에 따릅니다."


class CommandRequest(BaseModel):
    query: str
    context: dict[str, Any] = Field(default_factory=dict)


class MorningBriefRequest(BaseModel):
    market: str = "KR"


class StockDiagnosisRequest(BaseModel):
    symbol: str


class ReportGenerateRequest(BaseModel):
    report_type: str = "executive_summary"
    source_result: dict[str, Any]
    tone: str = "실장 보고"


class IdeaEvaluateRequest(BaseModel):
    symbol: str = "005930"
    portfolio_overrides: dict[str, Any] = Field(default_factory=dict)


class Source(BaseModel):
    id: str
    name: str
    type: str
    as_of: str


class StandardResponse(BaseModel):
    request_id: str
    job_id: str
    status: Literal["success"] = "success"
    intent: Optional[str] = None
    result: dict[str, Any]
    sources: list[Source] = Field(default_factory=list)
    as_of: str
    confidence: float = 0.8
    warnings: list[str] = Field(default_factory=list)
    latency_ms: int = 0


class SecurityAnalysisRequest(BaseModel):
    symbol: str


class CommitteeReviewRequest(BaseModel):
    symbol: str = "005930"
    idea: str = "보유종목 투자 thesis 재점검"
    event: str = "manual_review"
    portfolio_overrides: dict[str, Any] = Field(default_factory=dict)
