from __future__ import annotations

import logging

from src.agents.interfaces import IReviewer, UpdateContext
from src.config import get_settings
from src.models.interfaces import IModelProvider
from src.models.router import Router

logger = logging.getLogger(__name__)

_REVIEW_SYSTEM_PROMPT = """你是一个逻辑审查员。
你的职责：仅对以下文本进行逻辑质量审查，不检查风格、语法或格式。

请检查以下四个维度并输出 JSON：

1. completeness（完整性）：文本是否回答了问题的所有方面？
2. accuracy（准确性）：文本中的事实声明是否合理且不矛盾？
3. consistency（一致性）：文本内部逻辑是否自洽？
4. safety（安全底线）：是否遵守了基本安全准则（不违法、不有害）？

输出格式（严格 JSON）：
{
  "pass": true/false,
  "issues": [{"dimension": "completeness/accuracy/consistency/safety", "description": "问题描述"}],
  "suggestions": ["修改建议1", "修改建议2"]
}

仅输出 JSON，不要包含任何其他内容。"""


class Reviewer(IReviewer):
    def __init__(
        self,
        model_provider: IModelProvider,
        router: Router | None = None,
    ) -> None:
        self._model_provider = model_provider
        self._router = router

    async def review(self, ctx: UpdateContext, draft: str) -> dict:
        if self._router:
            result = await self._router.chat(
                history=[
                    {"role": "system", "content": _REVIEW_SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": (
                            f"用户问题：{ctx.message}\n\n"
                            f"待审查文本：\n{draft}\n\n"
                            "请审查以上文本的逻辑质量。"
                        ),
                    },
                ],
                task_type="review",
                temperature=0.1,
                max_tokens=500,
            )
            return _parse_review_json(result.content)

        cfg = get_settings()
        model = cfg.models.routing.review

        messages: list[dict[str, str]] = [
            {"role": "system", "content": _REVIEW_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"用户问题：{ctx.message}\n\n"
                    f"待审查文本：\n{draft}\n\n"
                    "请审查以上文本的逻辑质量。"
                ),
            },
        ]

        try:
            result = await self._model_provider.chat(
                history=messages,
                model=model,
                temperature=0.1,
                max_tokens=500,
            )
            return _parse_review_json(result.content)
        except Exception:
            logger.exception("reviewer_failed")
            return _default_review_pass()

    async def _check_against_beliefs(self, ctx: UpdateContext, draft: str) -> list[dict[str, str]]:
        issues: list[dict[str, str]] = []
        if not ctx.belief_store:
            return issues

        try:
            similar = await ctx.belief_store.search_similar(draft, top_k=5, min_confidence=0.6)
            for belief, sim in similar:
                if belief.confidence > 0.9 and sim > 0.8:
                    if belief.content.lower() != draft[: len(belief.content)].lower():
                        key_terms = _extract_key_terms(belief.content)
                        all_in_draft = all(t in draft for t in key_terms)
                        if not all_in_draft:
                            issues.append(
                                {
                                    "dimension": "accuracy",
                                    "description": (f"与高置信信念不一致 (id={belief.id[:8]}..)"),
                                }
                            )
        except Exception:
            logger.exception("belief_check_failed")

        return issues


def _parse_review_json(raw: str) -> dict:
    import json

    start = raw.find("{")
    if start == -1:
        return _default_review_pass()

    depth = 0
    end = start
    for i, ch in enumerate(raw[start:], start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break

    try:
        data = json.loads(raw[start:end])
        return {
            "pass": bool(data.get("pass", True)),
            "issues": list(data.get("issues", [])),
            "suggestions": list(data.get("suggestions", [])),
        }
    except (json.JSONDecodeError, ValueError):
        pass
    return _default_review_pass()


def _default_review_pass() -> dict:
    return {
        "pass": True,
        "issues": [],
        "suggestions": [],
    }


def _extract_key_terms(text: str) -> list[str]:
    words = [w.strip(".,!?;:()[]") for w in text.split() if len(w) > 2]
    return words[:5]
