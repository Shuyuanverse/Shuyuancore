from __future__ import annotations

import logging

from src.agents.interfaces import IUpdater, UpdateContext, UpdaterResult
from src.config import get_settings
from src.models.interfaces import IModelProvider

logger = logging.getLogger(__name__)

_INNOVATION_SYSTEM_PROMPT = """你是一个创新探索者（创新更新器）。
你的职责：跳出框架，提供非显而易见的替代方案或新思路。
不要天马行空，要合理且有逻辑支撑。
如果没有好思路，可以说明"常规方案已足够，暂无明显创新点"。

请按以下格式输出（严格 JSON）：
{"content": "你的创新思路文本", "confidence": 0.0-1.0之间的小数, "reasoning": "简要推理依据（≤100字）"}
仅输出 JSON，不要包含任何其他内容。"""


class InnovationUpdater(IUpdater):

    def __init__(self, model_provider: IModelProvider) -> None:
        self._model_provider = model_provider

    async def update(self, ctx: UpdateContext) -> UpdaterResult:
        cfg = get_settings()
        model = cfg.models.routing.review

        messages: list[dict[str, str]] = [
            {"role": "system", "content": _INNOVATION_SYSTEM_PROMPT},
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
                "content": f"用户的当前消息：{ctx.message}\n\n请跳出框架，提供非显而易见的替代方案或创新思路。",
            }
        )

        try:
            from src.agents.updater_evidence import _parse_updater_json

            result = await self._model_provider.chat(
                history=messages,
                model=model,
                temperature=0.7,
                max_tokens=500,
            )
            parsed = _parse_updater_json(result.content, "innovation")
            return parsed
        except Exception:
            logger.exception("innovation_updater_failed")
            return UpdaterResult(
                content="创新更新器未能生成思路（LLM 调用失败），可沿用常规方案。",
                confidence=0.3,
                reasoning="LLM 调用异常",
                source="innovation",
                metadata={"error": "llm_call_failed"},
            )
