from __future__ import annotations

import logging

from src.agents.interfaces import IUpdater, UpdateContext, UpdaterResult
from src.config import get_settings
from src.models.interfaces import IModelProvider

logger = logging.getLogger(__name__)

_RISK_SYSTEM_PROMPT = """你是一个风险分析师（风险更新器）。
你的职责：识别潜在问题、失败模式、边界条件和隐患。
不要只否定，要指出具体风险点和可能性。
如果无明显风险，请说明"未发现明显风险"。

请按以下格式输出（严格 JSON）：
{"content": "你的风险分析文本", "confidence": 0.0-1.0之间的小数, "reasoning": "简要推理依据（≤100字）"}
仅输出 JSON，不要包含任何其他内容。"""


class RiskUpdater(IUpdater):

    def __init__(self, model_provider: IModelProvider) -> None:
        self._model_provider = model_provider

    async def update(self, ctx: UpdateContext) -> UpdaterResult:
        cfg = get_settings()
        model = cfg.models.routing.review

        messages: list[dict[str, str]] = [
            {"role": "system", "content": _RISK_SYSTEM_PROMPT},
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
                "content": f"用户的当前消息：{ctx.message}\n\n请从风险角度分析潜在的失败模式和隐患。",
            }
        )

        try:
            from src.agents.updater_evidence import _parse_updater_json

            result = await self._model_provider.chat(
                history=messages,
                model=model,
                temperature=0.3,
                max_tokens=500,
            )
            parsed = _parse_updater_json(result.content, "risk")
            return parsed
        except Exception:
            logger.exception("risk_updater_failed")
            return UpdaterResult(
                content="风险更新器未能生成分析（LLM 调用失败），建议人工审查。",
                confidence=0.3,
                reasoning="LLM 调用异常",
                source="risk",
                metadata={"error": "llm_call_failed"},
            )
