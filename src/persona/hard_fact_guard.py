from __future__ import annotations

import logging
from typing import Optional
from uuid import uuid4

from src.core.interfaces import Belief, IBeliefStore

logger = logging.getLogger(__name__)

CATEGORIES = ["identity", "knowledge_boundary", "relation", "bottom_line"]

EXTRACTION_PROMPT = """从以下人格定义文本中提取硬事实，每行一条，格式：
CATEGORY|内容

四类硬事实：
- identity：关于身份、角色、背景的绝对事实
- knowledge_boundary：关于知识范围、能力边界的绝对事实
- relation：关于与他人/环境关系的绝对事实
- bottom_line：不可违背的底线规则

不要解释，不要添加额外内容，只输出 CATEGORY|内容 格式。

文本：
{core_md}"""


class HardFactGuard:
    def __init__(self, belief_store: IBeliefStore):
        self._belief_store = belief_store

    async def extract_from_core_md(self, core_md: str, persona_id: str) -> list[str]:
        from src.config import get_settings
        settings = get_settings()
        hard_fact_conf = settings.persona.hard_fact
        categories = hard_fact_conf.categories

        lines = core_md.strip().split("\n")
        parsed: list[tuple[str, str]] = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            for cat in categories:
                prefix = cat + "|"
                if line.startswith(prefix):
                    content = line[len(prefix):].strip()
                    if content:
                        parsed.append((cat, content))
                    break

        belief_ids: list[str] = []
        for category, content in parsed:
            exists = await self._check_duplicate(content)
            if exists:
                logger.info("[hard_fact] 跳过重复硬事实: %s", content[:50])
                belief_ids.append(exists)
                continue

            belief = Belief(
                id=str(uuid4()),
                content=content,
                source="system",
                confidence=hard_fact_conf.confidence,
                base_confidence=hard_fact_conf.confidence,
                last_accessed=0,
                memory_type=hard_fact_conf.memory_type,
                layer=hard_fact_conf.layer,
                entities=[],
                emotion=0.5,
                depends_on=[],
                child_belief_ids=[],
                superseded_by=None,
                status="active",
                is_composite=False,
                timestamp=0,
                metadata={"persona_id": persona_id, "category": category},
            )
            await self._belief_store.add(conversation_id="persona_global", belief=belief)
            belief_ids.append(belief.id)
            logger.info("[hard_fact] 写入硬事实: %s (%s)", content[:50], category)

        return belief_ids

    async def _check_duplicate(self, content: str) -> Optional[str]:
        results = await self._belief_store.search_similar(query=content, top_k=5)
        for r in results:
            if isinstance(r, Belief) and r.content == content and r.confidence > 0.9:
                return r.id
            if isinstance(r, tuple) and r[0].content == content and r[0].confidence > 0.9:
                return r[0].id
        return None

    def build_guard_prompt(self, belief_ids: list[str]) -> str:
        if not belief_ids:
            return ""

        import asyncio

        async def _fetch():
            facts = []
            for bid in belief_ids:
                belief = await self._belief_store.get(bid)
                if belief:
                    meta = belief.metadata or {}
                    facts.append((meta.get("category", "unknown"), belief.content))
            return facts

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                return self._build_guard_prompt_sync(belief_ids)
            facts = loop.run_until_complete(_fetch())
        except RuntimeError:
            return self._build_guard_prompt_sync(belief_ids)

        return self._format_facts(facts)

    def _build_guard_prompt_sync(self, belief_ids: list[str]) -> str:
        return "\n".join([f"- 硬事实（{bid[:8]}...）" for bid in belief_ids])

    def _format_facts(self, facts: list[tuple[str, str]]) -> str:
        if not facts:
            return ""
        lines = ["以下硬事实不可违背："]
        for category, content in facts:
            lines.append(f"- [{category}] {content}")
        return "\n".join(lines)
