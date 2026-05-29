from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from src.config import get_settings
from src.core.interfaces import IBeliefStore
from src.models.interfaces import IModelProvider
from src.skills.interfaces import ISkillStore
from src.skills.utils import generate_node_id

logger = logging.getLogger(__name__)

_extraction_lock = asyncio.Lock()

CORRECTION_KEYWORDS: list[str] = [
    "不对",
    "错了",
    "不是",
    "改一下",
    "重新",
    "错了错了",
    "我意思是",
    "你理解错了",
]

REFINEMENT_KEYWORDS: list[str] = [
    "再加",
    "补充",
    "注意",
    "别忘了",
    "也要",
    "同时",
    "顺便",
]

EXPLICIT_SAVE_KEYWORDS: list[str] = [
    "记住这个操作",
    "存成技能",
    "记下来",
    "保存这个",
    "学一下",
    "学会这个",
]

_LLM_SYSTEM_PROMPT = """你是一个技能提炼助手。根据提供的对话记录，提取一个可复用的技能。

请严格按照 JSON 格式输出，不要包含其他内容：

{
  "name": "技能名称（英文短横线命名，如 api-test-suite）",
  "description": "技能描述（中文，一句话概括）",
  "tags": ["标签1", "标签2"],
  "causality_level0": "一句话因果链，格式：当【条件】时→做【动作】→得到【结果】",
  "boundaries": ["不适用场景1"],
  "failure_modes": ["可能的失败模式1"],
  "dependencies": ["外部依赖1"]
}"""


def count_corrections(text: str) -> int:
    count = 0
    for kw in get_settings().skills.correction_keywords:
        count += text.count(kw)
    return count


def count_refinements(text: str) -> int:
    count = 0
    for kw in get_settings().skills.refinement_keywords:
        count += text.count(kw)
    return count


def has_explicit_save(text: str) -> bool:
    for kw in EXPLICIT_SAVE_KEYWORDS:
        if kw in text:
            return True
    return False


def calculate_value_score(
    turns_count: int,
    avg_interval_seconds: float = 30.0,
    correction_count: int = 0,
    refinement_count: int = 0,
    cross_session_count: int = 0,
    persona_weight: float = 0.5,
    recovered_from_error: bool = False,
    tool_call_failure_rate: float = 0.0,
    explicit_save: bool = False,
) -> float:
    time_spent_minutes = (turns_count * avg_interval_seconds) / 60.0

    time_score = min(time_spent_minutes / 5.0, 1.0) * 0.2
    correction_penalty = min(correction_count / 3.0, 1.0) * 0.15
    refinement_bonus = min(refinement_count / 2.0, 1.0) * 0.15
    cross_session_bonus = min(cross_session_count / 2.0, 1.0) * 0.3
    persona_bonus = persona_weight * 0.1
    recovery_bonus = 0.1 if recovered_from_error else 0.0
    failure_penalty = min(tool_call_failure_rate, 1.0) * 0.1
    save_bonus = 0.5 if explicit_save else 0.0

    score = (
        time_score
        - correction_penalty
        + refinement_bonus
        + cross_session_bonus
        + persona_bonus
        + recovery_bonus
        - failure_penalty
        + save_bonus
    )

    return max(0.0, min(score, 1.0))


def _parse_llm_output(text: str) -> dict[str, Any] | None:
    text = text.strip()
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        json_str = text[start : end + 1]
        try:
            return json.loads(json_str)
        except json.JSONDecodeError as exc:
            logger.warning("failed to parse LLM output: %s", exc)
            return None
    return None


async def extract_skill(
    conversation_id: str,
    message: str,
    response: str,
    belief_store: IBeliefStore,
    skill_store: ISkillStore,
    model_provider: IModelProvider,
) -> str | None:
    settings = get_settings()
    if not settings.skills.auto_extract:
        return None

    if _extraction_lock.locked():
        logger.info("extraction_skipped: another extraction task in progress")
        return None

    async with _extraction_lock:
        return await _do_extract(
            conversation_id,
            message,
            response,
            belief_store,
            skill_store,
            model_provider,
        )


async def _do_extract(
    conversation_id: str,
    message: str,
    response: str,
    belief_store: IBeliefStore,
    skill_store: ISkillStore,
    model_provider: IModelProvider,
) -> str | None:
    if has_explicit_save(message + response):
        explicit_save_flag = True
        threshold = 0.0
    else:
        explicit_save_flag = False
        threshold = get_settings().skills.value_score_threshold

    recent = await belief_store.get(conversation_id, limit=50)
    if not recent:
        return None

    turns_count = len(recent)
    correction_count = count_corrections(message) + count_corrections(response)
    refinement_count = count_refinements(message) + count_refinements(response)

    tool_calls = [b for b in recent if b.source == "tool"]
    total_tool_calls = len(tool_calls)
    failed_tool_calls = sum(
        1 for b in tool_calls if b.content.startswith("error:") or "error" in b.content.lower()
    )
    tool_call_failure_rate = failed_tool_calls / total_tool_calls if total_tool_calls > 0 else 0.0

    has_recovered = failed_tool_calls > 0 and total_tool_calls > failed_tool_calls

    score = calculate_value_score(
        turns_count=turns_count,
        correction_count=correction_count,
        refinement_count=refinement_count,
        cross_session_count=0,
        persona_weight=0.5,
        recovered_from_error=has_recovered,
        tool_call_failure_rate=tool_call_failure_rate,
        explicit_save=explicit_save_flag,
    )

    logger.info(
        "value_score conversation=%s score=%.3f threshold=%.2f",
        conversation_id,
        score,
        threshold,
    )

    if score < threshold and not explicit_save_flag:
        return None

    skill_data = await _generate_skill_from_llm(
        message=message,
        response=response,
        model_provider=model_provider,
    )
    if skill_data is None:
        logger.warning("LLM skill generation failed for %s", conversation_id)
        return None

    skill_data["explicit_save"] = explicit_save_flag
    skill_data["node_id"] = generate_node_id()

    node_id = await skill_store.create_skill(skill_data, conversation_id)

    logger.info(
        "skill_extracted conversation=%s skill_name=%s node_id=%s score=%.3f",
        conversation_id,
        skill_data.get("name", "unknown"),
        node_id,
        score,
    )
    return node_id


async def _generate_skill_from_llm(
    message: str,
    response: str,
    model_provider: IModelProvider,
) -> dict[str, Any] | None:
    transcript = f"用户消息: {message}\n\n助手回复: {response}\n\n"

    try:
        result = await model_provider.chat(
            history=[
                {"role": "system", "content": _LLM_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (f"根据以下对话，提炼一个技能。\n\n{transcript}"),
                },
            ],
            model="qwen-turbo",
            temperature=0.3,
            max_tokens=2000,
        )
    except Exception as exc:
        logger.error("LLM skill generation error: %s", exc)
        return None

    parsed = _parse_llm_output(result.content)
    if parsed is None:
        return None

    parsed["causality_level0"] = parsed.get("causality_level0", "")
    parsed["causality_level1"] = ""
    parsed["causality_level2"] = ""
    parsed["preconditions"] = []
    parsed["version_history"] = [{"version": "1.0", "change": "auto-extracted from conversation"}]

    return parsed
