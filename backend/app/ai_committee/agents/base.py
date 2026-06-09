from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class CommitteeContext:
    symbol: str
    idea: str
    event: str
    stock: dict[str, Any]
    sector: dict[str, Any]
    news: list[dict[str, Any]]
    darts: list[dict[str, Any]]
    portfolio: dict[str, Any]
    security_report: dict[str, Any]


class CommitteeAgent:
    name = "Base"

    def analyze(self, context: CommitteeContext) -> dict[str, Any]:
        raise NotImplementedError

    def opinion(
        self,
        *,
        stance: str,
        score: int,
        confidence: float,
        summary: str,
        reasoning_steps: list[str],
        evidence: list[str],
        risks: list[str],
        analysis: dict[str, Any],
        citations: list[dict[str, Any]],
        follow_up: list[str] | None = None,
    ) -> dict[str, Any]:
        return {
            "agent": self.name,
            "stance": stance,
            "score": score,
            "confidence": round(confidence, 2),
            "summary": summary,
            "reasoning_steps": reasoning_steps,
            "evidence": evidence,
            "risks": risks,
            "analysis": analysis,
            "citations": citations,
            "follow_up": follow_up or [],
        }


def source(label: str, dataset: str, as_of: str | None = None, confidence: float | None = None) -> dict[str, Any]:
    return {"label": label, "dataset": dataset, "as_of": as_of, "confidence": confidence}
