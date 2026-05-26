from __future__ import annotations

import logging

from src.agents.interfaces import IArbitrator, UpdateContext, UpdaterResult
from src.config import get_settings
from src.models.interfaces import IModelProvider

logger = logging.getLogger(__name__)

_ARBITRATOR_POLISH_PROMPT = """你是一个文本润色助手。
请将以下各视角的分析融合成一段自然流畅的回复。

要求：
1. 保留每个视角的核心结论和置信度
2. 冲突时优先采信置信度高的视角
3. 输出包含 [综合] 部分，给出最终建议
4. 使用中文

输入数据：
{input_data}

请直接输出润色后的文本，不要添加前缀或说明。"""


class Arbitrator(IArbitrator):

    def __init__(self, model_provider: IModelProvider) -> None:
        self._model_provider = model_provider

    async def arbitrate(
        self, ctx: UpdateContext, updater_results: list[UpdaterResult]
    ) -> str:
        if not updater_results:
            return "无可用更新器结果，无法生成回复。"

        if len(updater_results) == 1:
            return _format_single_result(updater_results[0])

        conflict_detected = _detect_conflict(updater_results)

        if not conflict_detected:
            best = max(updater_results, key=lambda r: r.confidence)
            return _format_single_result(best)

        weighted = _weighted_fusion(updater_results, ctx.user_preference_weights)

        return await self._polish(ctx, weighted)

    async def _polish(
        self, ctx: UpdateContext, weighted: list[UpdaterResult]
    ) -> str:
        cfg = get_settings()
        model = cfg.models.routing.tool

        input_data = _format_structured_data(weighted, ctx.user_preference_weights)

        try:
            result = await self._model_provider.chat(
                history=[
                    {
                        "role": "system",
                        "content": _ARBITRATOR_POLISH_PROMPT.format(
                            input_data=input_data
                        ),
                    },
                    {
                        "role": "user",
                        "content": f"用户问题：{ctx.message}\n\n请润色并融合以上分析。",
                    },
                ],
                model=model,
                temperature=0.3,
                max_tokens=1000,
            )
            return result.content.strip()
        except Exception:
            logger.exception("arbitrator_polish_failed")
            return input_data


def _detect_conflict(results: list[UpdaterResult], threshold: float = 0.5) -> bool:
    if len(results) < 2:
        return False

    confidences = [r.confidence for r in results]
    max_conf = max(confidences) if confidences else 0
    min_conf = min(confidences) if confidences else 0

    if max_conf - min_conf > 0.4:
        return True

    for i in range(len(results)):
        for j in range(i + 1, len(results)):
            if _content_similarity(results[i].content, results[j].content) < threshold:
                return True

    return False


def _content_similarity(a: str, b: str) -> float:
    import re

    def tokenize(text: str) -> set[str]:
        words = re.findall(r"[\u4e00-\u9fff]+|[a-zA-Z]+", text.lower())
        return set(words)

    tokens_a = tokenize(a)
    tokens_b = tokenize(b)
    if not tokens_a or not tokens_b:
        return 1.0

    intersection = tokens_a & tokens_b
    if len(intersection) >= 1:
        return 0.5 + 0.5 * (len(intersection) / len(tokens_a | tokens_b))

    return len(intersection) / len(tokens_a | tokens_b)


def _weighted_fusion(
    results: list[UpdaterResult],
    weights: dict[str, float],
) -> list[UpdaterResult]:
    fused: list[UpdaterResult] = []
    for r in results:
        weight = weights.get(r.source, 1.0)
        fused.append(
            UpdaterResult(
                content=r.content,
                confidence=r.confidence * weight,
                reasoning=r.reasoning,
                source=r.source,
                metadata=r.metadata,
            )
        )
    return fused


def _format_single_result(result: UpdaterResult) -> str:
    return f"[{_source_label(result.source)}视角] {result.content}\n（置信度 {result.confidence:.2f}）"


def _format_structured_data(
    results: list[UpdaterResult],
    weights: dict[str, float],
) -> str:
    lines: list[str] = []
    for r in results:
        label = _source_label(r.source)
        weight = weights.get(r.source, 1.0)
        lines.append(
            f"[{label}视角] (置信度 {r.confidence:.2f}, 权重 {weight})\n"
            f"  结论：{r.content}\n"
            f"  依据：{r.reasoning}"
        )

    best = max(results, key=lambda r: r.confidence)
    lines.append(
        f"\n[综合] 加权置信度最高的视角：{_source_label(best.source)} "
        f"({best.confidence:.2f})"
    )
    return "\n".join(lines)


def _source_label(source: str) -> str:
    labels = {
        "evidence": "证据",
        "risk": "风险",
        "innovation": "创新",
    }
    return labels.get(source, source)