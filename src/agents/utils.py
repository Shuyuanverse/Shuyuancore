from __future__ import annotations

import uuid
from typing import Any

from src.config import get_settings
from src.core.interfaces import Belief, IBeliefStore
from src.memory.decay import current_time_ms


async def compute_perturbation_strength(
    belief_store: IBeliefStore,
    user_message: str,
) -> float:
    cfg = get_settings().agents

    semantic_weight = cfg.perturbation_semantic_weight
    contradiction_weight = cfg.perturbation_contradiction_weight
    density_weight = cfg.perturbation_density_weight
    decision_weight = cfg.perturbation_decision_weight

    total_weight = (
        semantic_weight + contradiction_weight + density_weight + decision_weight
    )
    if total_weight <= 0:
        return 0.5

    score = 0.0

    similar = await belief_store.search_similar(
        user_message, top_k=5, min_confidence=0.1
    )
    if similar:
        max_sim = max(s for _, s in similar)
        semantic_distance = 1.0 - max_sim
        score += semantic_distance * semantic_weight

    recent = await belief_store.get("__global__", limit=30)
    contradict_pairs = 0
    for i in range(len(recent)):
        for j in range(i + 1, len(recent)):
            if recent[i].confidence > 0.6 and recent[j].confidence > 0.6:
                if _are_contradicting(recent[i], recent[j]):
                    contradict_pairs += 1
    contradiction_factor = min(contradict_pairs / max(len(recent), 1), 1.0)
    score += contradiction_factor * contradiction_weight

    if len(recent) >= 5:
        timestamps = [b.timestamp for b in recent if b.timestamp]
        if timestamps:
            span = max(timestamps) - min(timestamps)
            if span > 0:
                density = len(timestamps) / span * 3600000
                density_factor = min(density / 10.0, 1.0)
                score += density_factor * density_weight

    decision_keywords = [
        "要不要", "应不应该", "该不该", "是不是该", "是否应该",
        "应该", "推荐", "建议", "选哪个", "哪个好", "最好",
        "怎么办", "如何选择", "能不能", "可以吗",
    ]
    if any(kw in user_message for kw in decision_keywords):
        score += decision_weight

    return min(max(score, 0.0), 1.0)


def _are_contradicting(a: Belief, b: Belief) -> bool:
    if not a.entities or not b.entities:
        return False
    shared = set(a.entities) & set(b.entities)
    if not shared:
        return False
    content_diff = abs(len(a.content) - len(b.content)) / max(
        max(len(a.content), len(b.content)), 1
    )
    if a.emotion > 0.8 and b.emotion < 0.2:
        return True
    if a.emotion < 0.2 and b.emotion > 0.8:
        return True
    if content_diff > 0.7:
        return True
    return False


def build_updater_belief(result: Any, conversation_id: str) -> Belief:
    from src.agents.interfaces import UpdaterResult

    updater_result: UpdaterResult = result
    now = current_time_ms()
    meta = dict(updater_result.metadata)
    meta["reasoning"] = updater_result.reasoning
    return Belief(
        id=str(uuid.uuid4()),
        content=updater_result.content,
        source=f"updater:{updater_result.source}",
        confidence=updater_result.confidence,
        base_confidence=updater_result.confidence,
        last_accessed=now,
        timestamp=now,
        memory_type="fact",
        layer=3,
        metadata=meta,
    )


def determine_update_strategy(
    perturbation_strength: float,
    low_threshold: float = 0.3,
    high_threshold: float = 0.7,
    mode_override: str | None = None,
) -> list[str]:
    if mode_override:
        if mode_override == "quick":
            return ["evidence"]
        elif mode_override == "balanced":
            return ["evidence", "risk"]
        elif mode_override == "deep":
            return ["evidence", "risk", "innovation"]

    if perturbation_strength < low_threshold:
        return ["evidence"]
    elif perturbation_strength < high_threshold:
        return ["evidence", "risk"]
    else:
        return ["evidence", "risk", "innovation"]
