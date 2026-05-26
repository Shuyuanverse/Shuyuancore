from __future__ import annotations

import logging

from src.agents.interfaces import IUpdater, UpdateContext, UpdaterResult
from src.config import get_settings
from src.models.interfaces import IModelProvider

logger = logging.getLogger(__name__)

_EVIDENCE_SYSTEM_PROMPT = """你是一个基于事实的决策者（证据更新器）。
你的职责：根据已有信念和用户消息，提供最可靠的结论。
强调数据和已有证据，不要凭空猜测。
如果证据不足，请明确说明不确定性。

请按以下格式输出（严格 JSON）：
{"content": "你的结论文本", "confidence": 0.0-1.0之间的小数, "reasoning": "简要推理依据（≤100字）"}
仅输出 JSON，不要包含任何其他内容。"""


class EvidenceUpdater(IUpdater):

    def __init__(self, model_provider: IModelProvider) -> None:
        self._model_provider = model_provider

    async def update(self, ctx: UpdateContext) -> UpdaterResult:
        cfg = get_settings()
        model = cfg.models.routing.review

        messages: list[dict[str, str]] = [
            {"role": "system", "content": _EVIDENCE_SYSTEM_PROMPT},
        ]

        if ctx.belief_store:
            recent = await ctx.belief_store.get(ctx.conversation_id, limit=20)
            belief_context = "\n".join(
                f"[置信度 {b.confidence:.2f}] {b.content}" for b in recent
            )
            if belief_context:
                messages.append(
                    {
                        "role": "system",
                        "content": f"当前已知信念：\n{belief_context}",
                    }
                )

        messages.append(
            {
                "role": "user",
                "content": f"用户的当前消息：{ctx.message}\n\n请基于事实和已有证据提供你的结论。",
            }
        )

        try:
            result = await self._model_provider.chat(
                history=messages,
                model=model,
                temperature=0.3,
                max_tokens=500,
            )
            parsed = _parse_updater_json(result.content, "evidence")
            return parsed
        except Exception:
            logger.exception("evidence_updater_failed")
            return UpdaterResult(
                content="证据更新器未能生成结论（LLM 调用失败），建议基于已有信息谨慎回复。",
                confidence=0.3,
                reasoning="LLM 调用异常",
                source="evidence",
                metadata={"error": "llm_call_failed"},
            )


def _parse_updater_json(raw: str, source: str) -> UpdaterResult:
    import json
    import re

    match = re.search(r"\{[^{}]*\}", raw)
    if match:
        try:
            data = json.loads(match.group(0))
            confidence = float(data.get("confidence", 0.5))
            confidence = max(0.0, min(1.0, confidence))
            return UpdaterResult(
                content=str(data.get("content", "")),
                confidence=confidence,
                reasoning=str(data.get("reasoning", "")),
                source=source,
            )
        except (json.JSONDecodeError, ValueError, KeyError):
            pass

    return UpdaterResult(
        content=raw.strip(),
        confidence=0.5,
        reasoning="JSON 解析失败，使用原始输出",
        source=source,
    )