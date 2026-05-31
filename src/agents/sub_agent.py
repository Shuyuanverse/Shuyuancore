from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

from src.agents.interfaces import ISubAgent
from src.config import get_settings
from src.core.interfaces import Belief, IBeliefStore
from src.memory.decay import current_time_ms

logger = logging.getLogger(__name__)

_LLM_SUBAGENT_PROMPT = (
    "你是一个子代理，负责执行以下任务。\n\n"
    "作用域: {scope}\n"
    "任务: {task}\n\n"
    "以下是相关的上下文信念:\n{belief_context}\n\n"
    "请基于以上上下文，完成指派的任务。"
    "返回一个清晰、简洁的结果（不超过 500 字）。"
)


class SubAgent(ISubAgent):
    def __init__(
        self,
        belief_store: IBeliefStore,
        scope: str,
        timeout: int | None = None,
        router: Any | None = None,
    ) -> None:
        self._belief_store = belief_store
        self._scope = scope
        cfg = get_settings()
        self._timeout = timeout or cfg.agents.sub_agent_timeout_seconds
        self._router = router
        self._belief_threshold = cfg.agents.sub_agent_belief_threshold

    async def run(self, task: str, scope: str, context: dict[str, str]) -> str:
        scope = scope or self._scope
        try:
            result = await asyncio.wait_for(
                self._execute(task, scope, context),
                timeout=self._timeout,
            )
        except asyncio.TimeoutError:
            logger.warning("sub_agent_timeout: scope=%s timeout=%ds", scope, self._timeout)
            return ""
        except Exception:
            logger.exception("sub_agent_run_failed: scope=%s", scope)
            return ""

        return result

    async def _execute(self, task: str, scope: str, context: dict[str, str]) -> str:
        conversation_id = context.get("conversation_id", "sub_agent_default")
        beliefs_raw = await self._belief_store.get(conversation_id, limit=10)

        threshold = self._belief_threshold
        filtered = [b for b in beliefs_raw if b.confidence >= threshold]
        context_summary = "\n".join(
            f"[{b.source}] (conf={b.confidence:.2f}) {b.content[:100]}"
            for b in (filtered or beliefs_raw[:3])
        )

        if self._router is not None:
            try:
                prompt = _LLM_SUBAGENT_PROMPT.format(
                    scope=scope,
                    task=task,
                    belief_context=context_summary[:1500],
                )
                result = await self._router.chat(
                    history=[{"role": "user", "content": prompt}],
                    temperature=0.5,
                    max_tokens=512,
                )
                summary = result.content.strip()
            except Exception:
                logger.exception("sub_agent_llm_failed: scope=%s", scope)
                summary = self._build_text_summary(task, scope, context_summary)
        else:
            summary = self._build_text_summary(task, scope, context_summary)

        belief = Belief(
            id=str(uuid.uuid4()),
            content=summary,
            source=f"sub_agent:{scope}",
            confidence=0.7,
            base_confidence=0.7,
            last_accessed=current_time_ms(),
            timestamp=current_time_ms(),
            memory_type="fact",
            layer=3,
            metadata={"task": task, "scope": scope},
        )

        try:
            await self._belief_store.add(conversation_id, belief)
        except Exception:
            logger.exception("sub_agent_belief_write_failed")

        return summary

    def _build_text_summary(self, task: str, scope: str, context_summary: str) -> str:
        return f"[子代理 scope={scope}] 任务: {task}\n上下文: {context_summary[:500]}"
