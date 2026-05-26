from __future__ import annotations

import asyncio
import logging
import uuid

from src.agents.interfaces import ISubAgent
from src.config import get_settings
from src.core.interfaces import Belief, IBeliefStore
from src.memory.decay import current_time_ms

logger = logging.getLogger(__name__)


class SubAgent(ISubAgent):

    def __init__(
        self,
        belief_store: IBeliefStore,
        scope: str,
        timeout: int | None = None,
    ) -> None:
        self._belief_store = belief_store
        self._scope = scope
        cfg = get_settings()
        self._timeout = timeout or cfg.agents.sub_agent_timeout_seconds

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
        context_summary = "\n".join(
            f"[{b.source}] {b.content[:100]}" for b in beliefs_raw
        )

        summary = (
            f"[子代理 scope={scope}] 任务: {task}\n"
            f"上下文: {context_summary[:500]}"
        )

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