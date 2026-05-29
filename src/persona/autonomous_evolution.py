from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

REJECT_THRESHOLD = 0.3
AUTO_THRESHOLD = 0.7
TRIGGER_DAYS = 7
MAX_PROPOSALS = 5

DIMENSIONS = [
    "formality",
    "warmth",
    "directness",
    "playfulness",
    "detail_orientation",
    "emotional_expression",
    "pace",
]


@dataclass
class EvolutionProposal:
    persona_id: str
    proposal_id: str
    dimension: str
    current_value: float
    proposed_value: float
    delta: float
    trigger_type: str
    reason: str = ""
    consistency_score: float = 0.0
    status: str = "pending"


class AutonomousEvolution:
    def __init__(self, persona_store: object = None):
        self._store = persona_store

    async def detect_evolution(
        self,
        persona_id: str,
        current_profile: object,
        drift_history: list[dict],
        recent_interactions: list[dict],
    ) -> list[EvolutionProposal]:
        if len(recent_interactions) < 10:
            return []

        proposals: list[EvolutionProposal] = []
        for dim in DIMENSIONS:
            drift_trend = self._analyze_dimension_trend(dim, drift_history, recent_interactions)
            if drift_trend is None:
                continue

            current_val = drift_trend["current"]
            trend_val = drift_trend["trend"]
            if abs(trend_val - current_val) < 0.05:
                continue

            proposal = EvolutionProposal(
                persona_id=persona_id,
                proposal_id=f"{persona_id}_{dim}_{len(proposals)}",
                dimension=dim,
                current_value=current_val,
                proposed_value=trend_val,
                delta=trend_val - current_val,
                trigger_type="drift_trend",
                reason=(
                    f"维度 {dim} 在最近对话中呈现 {trend_val:.2f} 的趋势"
                    f"（当前锚点: {current_val:.2f}）"
                ),
            )
            proposals.append(proposal)

            if len(proposals) >= MAX_PROPOSALS:
                break

        return proposals

    async def review_and_apply(
        self,
        proposal: EvolutionProposal,
    ) -> EvolutionProposal:
        proposal.consistency_score = self._calc_consistency(proposal)

        if proposal.consistency_score < REJECT_THRESHOLD:
            proposal.status = "rejected"
            logger.info(
                "[evolution] 拒绝演化提议: %s (consistency=%.2f)",
                proposal.dimension,
                proposal.consistency_score,
            )
        elif proposal.consistency_score <= AUTO_THRESHOLD:
            proposal.delta = proposal.delta * proposal.consistency_score
            proposal.proposed_value = proposal.current_value + proposal.delta
            proposal.status = "auto_adjusted"
            logger.info(
                "[evolution] 缩小幅度自动执行: %s (consistency=%.2f delta=%.4f)",
                proposal.dimension,
                proposal.consistency_score,
                proposal.delta,
            )
        else:
            proposal.status = "approved"
            logger.info(
                "[evolution] 演化提议通过: %s (consistency=%.2f)",
                proposal.dimension,
                proposal.consistency_score,
            )

        return proposal

    def _analyze_dimension_trend(
        self,
        dimension: str,
        drift_history: list[dict],
        recent_interactions: list[dict],
    ) -> Optional[dict]:
        dim_values = []
        for entry in drift_history[-20:]:
            dims = entry.get("dimensions", {})
            if isinstance(dims, str):
                continue
            if dimension in dims:
                dim_values.append(dims[dimension])

        if len(dim_values) < 3:
            return None

        trend = sum(dim_values) / len(dim_values)
        return {"current": 0.5, "trend": trend}

    @staticmethod
    def _calc_consistency(proposal: EvolutionProposal) -> float:
        base = 1.0 - abs(proposal.delta) * 2
        return max(min(base, 1.0), 0.0)
