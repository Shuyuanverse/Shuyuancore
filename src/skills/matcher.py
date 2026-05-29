from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

from src.config import get_settings
from src.core.interfaces import IBeliefStore
from src.memory.embedding import EmbeddingService
from src.skills.manager import PersistentSkillStore
from src.skills.utils import preconditions_satisfied

logger = logging.getLogger(__name__)

_EXACT_PATTERN = re.compile(r"(?:/skill\s+|用|使用|调用|执行)\s*([\w\-]+)\s*(?:技能|方法|步骤)?")
_USE_SKILL_PATTERN = re.compile(r"(?:用|使用|调用|执行)\s*(.+?)\s*(?:技能|方法|步骤)")


async def match_skill(
    user_message: str,
    belief_store: IBeliefStore,
    skill_store: PersistentSkillStore,
    embedding_service: EmbeddingService,
) -> dict[str, Any] | None:
    settings = get_settings()
    timeout_ms = settings.skills.matching_timeout_ms

    try:
        result = await asyncio.wait_for(
            _match_skill_impl(
                user_message=user_message,
                belief_store=belief_store,
                skill_store=skill_store,
                embedding_service=embedding_service,
            ),
            timeout=timeout_ms / 1000.0,
        )
        return result
    except asyncio.TimeoutError:
        logger.warning(
            "skill_matching_timeout msg_preview=%s",
            user_message[:50],
        )
        return None


async def _match_skill_impl(
    user_message: str,
    belief_store: IBeliefStore,
    skill_store: PersistentSkillStore,
    embedding_service: EmbeddingService,
) -> dict[str, Any] | None:
    exact = await _try_exact_match(user_message, skill_store)
    if exact is not None:
        return exact

    similar = await _try_vector_match(
        user_message=user_message,
        belief_store=belief_store,
        skill_store=skill_store,
        embedding_service=embedding_service,
    )
    return similar


async def _try_exact_match(
    user_message: str,
    skill_store: PersistentSkillStore,
) -> dict[str, Any] | None:
    match = _EXACT_PATTERN.search(user_message)
    if not match:
        match = _USE_SKILL_PATTERN.search(user_message)
    if not match:
        return None

    skill_name = match.group(1).strip().lower()

    all_skills = await skill_store.list_skills(status="active")
    for skill in all_skills:
        if skill.get("name", "").lower() == skill_name:
            return skill
        tags = skill.get("tags", [])
        if isinstance(tags, str):
            try:
                tags = json.loads(tags)
            except (json.JSONDecodeError, TypeError):
                tags = []
        if any(t.lower() == skill_name for t in tags):
            return skill
    return None


async def _try_vector_match(
    user_message: str,
    belief_store: IBeliefStore,
    skill_store: PersistentSkillStore,
    embedding_service: EmbeddingService,
) -> dict[str, Any] | None:
    similar_beliefs = await belief_store.search_similar(user_message, top_k=10, min_confidence=0.1)
    if not similar_beliefs:
        return None

    skill_candidates: list[tuple[dict[str, Any], float]] = []

    for belief, sim_score in similar_beliefs:
        if belief.memory_type != "skill" or belief.layer != 4:
            continue
        if belief.status != "active":
            continue

        skill = await skill_store.get_skill_by_belief_id(belief.id)
        if skill is None:
            continue
        if skill.get("status") != "active":
            continue

        combined_score = sim_score * belief.confidence
        skill_candidates.append((skill, combined_score))

    if not skill_candidates:
        return None

    skill_candidates.sort(key=lambda x: x[1], reverse=True)

    all_skills_list = await skill_store.list_skills(status="active")
    skill_name_to_confidence: dict[str, float] = {}
    belief_id_to_confidence: dict[str, float] = {}
    for sk in all_skills_list:
        name = sk.get("name", "")
        conf = sk.get("confidence", 0.0)
        skill_name_to_confidence[name] = conf
        bid = sk.get("belief_id", "")
        if bid:
            belief_id_to_confidence[bid] = conf

    for skill, _score in skill_candidates:
        preconditions_raw = skill.get("preconditions", [])
        if isinstance(preconditions_raw, str):
            try:
                preconditions_raw = json.loads(preconditions_raw)
            except (json.JSONDecodeError, TypeError):
                preconditions_raw = []

        if preconditions_satisfied(
            preconditions=preconditions_raw,
            skill_confidence_map=skill_name_to_confidence,
            belief_confidence_map=belief_id_to_confidence,
        ):
            return skill

    best = skill_candidates[0][0]
    return best


def format_skill_for_prompt(skill: dict[str, Any]) -> str:
    name = skill.get("name", "unknown")
    description = skill.get("description", "")
    causality = skill.get("causality_level0", "")

    lines = [
        f"[技能匹配] 名称: {name}",
    ]
    if description:
        lines.append(f"描述: {description}")
    if causality:
        lines.append(f"因果链: {causality}")

    tags = skill.get("tags", [])
    if isinstance(tags, str):
        try:
            tags = json.loads(tags)
        except (json.JSONDecodeError, TypeError):
            tags = []
    if tags:
        lines.append(f"标签: {', '.join(tags)}")

    boundaries = skill.get("boundaries", [])
    if isinstance(boundaries, str):
        try:
            boundaries = json.loads(boundaries)
        except (json.JSONDecodeError, TypeError):
            boundaries = []
    if boundaries:
        lines.append(f"注意: 不适用于 {'、'.join(boundaries)}")

    return "\n".join(lines)
