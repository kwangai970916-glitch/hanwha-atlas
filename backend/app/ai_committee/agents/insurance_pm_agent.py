from .base import CommitteeContext, source, CommitteeAgent


class InsurancePMAgent(CommitteeAgent):
    name = "Insurance PM"

    def analyze_final(self, c: CommitteeContext, final_view: dict) -> dict:
        return self.opinion(
            stance=final_view["stance"],
            score=final_view.get("score", 72),
            confidence=final_view.get("confidence", 0.78),
            summary=final_view["summary"],
            reasoning_steps=["각 agent signal을 긍정/중립/경고로 집계", "리스크 한도 위반 여부를 최종 action에 우선 반영", "보험사 일반계정의 drawdown 회피와 유동성 제약 반영", "후속 체크포인트와 PM override 필요성을 명시"],
            evidence=[final_view["action"], f"risk flags {len(final_view.get('risk_flags', []))}개"],
            risks=final_view.get("risk_flags", []),
            analysis={"mandate_fit": "insurance_general_account", "recommended_action": final_view["action"], "target_weight_delta": final_view.get("target_weight_delta", 0.0), "approval_gates": final_view.get("approval_gates", []), "next_review_trigger": final_view.get("next_review_trigger")},
            citations=[source("committee_synthesis", "ai_committee")],
            follow_up=final_view.get("checkpoints", []),
        )
