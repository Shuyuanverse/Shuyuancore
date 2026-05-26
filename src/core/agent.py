from __future__ import annotations

import json
import uuid
from typing import Any, AsyncIterator

from src.core.interfaces import (
    Belief,
    IBeliefStore,
    IMemoryStore,
    IPersonaGuard,
    IReader,
    ISkillEngine,
    IToolRegistry,
)
from src.core.noop_implementations import (
    MockToolRegistry,
    NoOpMemoryStore,
    NoOpPersonaGuard,
    NoOpSkillEngine,
)
from src.memory.decay import current_time_ms
from src.memory.extractor import (
    JiebaEntityExtractor,
    SnowNlpEmotionAnalyzer,
)
from src.memory.interfaces import IEmotionAnalyzer, IEntityExtractor
from src.memory.wake import wake_readiness, wake_score
from src.memory.writer import (
    AiInferenceWriter,
    CompositeBeliefDetector,
    ManualMemoryWriter,
    RuleBasedWriter,
)
from src.models.interfaces import (
    IModelProvider,
)

_MAX_TOOL_CALLS_PER_TURN = 5


class Agent:

    def __init__(
        self,
        model_provider: IModelProvider,
        belief_store: IBeliefStore,
        reader: IReader,
        tool_registry: IToolRegistry | None = None,
        memory_store: IMemoryStore | None = None,
        persona_guard: IPersonaGuard | None = None,
        skill_engine: ISkillEngine | None = None,
        entity_extractor: IEntityExtractor | None = None,
        emotion_analyzer: IEmotionAnalyzer | None = None,
    ) -> None:
        self._model_provider = model_provider
        self._belief_store = belief_store
        self._reader = reader
        self._tool_registry = tool_registry or MockToolRegistry()
        self._memory_store = memory_store or NoOpMemoryStore()
        self._persona_guard = persona_guard or NoOpPersonaGuard()
        self._skill_engine = skill_engine or NoOpSkillEngine()
        self._entity_extractor = entity_extractor or JiebaEntityExtractor()
        self._emotion_analyzer = emotion_analyzer or SnowNlpEmotionAnalyzer()

    async def chat_stream(
        self,
        message: str,
        conversation_id: str | None = None,
    ) -> AsyncIterator[str]:
        if conversation_id is None:
            conversation_id = str(uuid.uuid4())

        user_belief = Belief(
            content=message,
            source="user",
            id=str(uuid.uuid4()),
            timestamp=current_time_ms(),
            last_accessed=current_time_ms(),
        )
        await self._belief_store.add(conversation_id, user_belief)

        readiness = wake_readiness(message)
        if readiness > 0.5:
            similar = await self._belief_store.search_similar(
                message, top_k=5, min_confidence=0.1
            )
            for belief, score in similar:
                ws = wake_score(
                    belief=belief,
                    user_msg=message,
                    entity_extractor=self._entity_extractor,
                    emotion_analyzer=self._emotion_analyzer,
                )
                if ws > 0.6:
                    snippet = belief.content[:80]
                    yield f"[唤醒相关记忆: {snippet}]"

        tool_call_count = 0
        full_response = ""
        while tool_call_count < _MAX_TOOL_CALLS_PER_TURN:
            context = await self._reader.read(
                conversation_id=conversation_id,
                user_query=message,
                max_tokens=4000,
            )

            pending_tool_calls: list[dict[str, Any]] = []

            async for event in self._model_provider.chat_stream(
                history=context
            ):
                if event.type == "content":
                    full_response += event.content
                    yield event.content
                elif event.type == "tool_call":
                    pending_tool_calls.append(
                        {
                            "id": event.tool_name or "",
                            "function": {
                                "name": event.tool_name or "",
                                "arguments": event.tool_params or "{}",
                            },
                        }
                    )
                elif event.type == "done":
                    if event.tool_name:
                        pending_tool_calls.append(
                            {
                                "id": event.tool_name,
                                "function": {
                                    "name": event.tool_name,
                                    "arguments": event.tool_params or "{}",
                                },
                            }
                        )

            if not pending_tool_calls:
                assistant_belief = Belief(
                    content=full_response,
                    source="assistant",
                    id=str(uuid.uuid4()),
                    timestamp=current_time_ms(),
                    last_accessed=current_time_ms(),
                )
                await self._belief_store.add(
                    conversation_id, assistant_belief
                )
                break

            tool_results: list[dict[str, Any]] = []
            for tc in pending_tool_calls:
                tool_call_id = tc.get("id", "")
                func_info = tc.get("function", {})
                tool_name = func_info.get("name", "")
                raw_args = func_info.get("arguments", "{}")
                try:
                    arguments = (
                        json.loads(raw_args)
                        if isinstance(raw_args, str)
                        else raw_args
                    )
                except json.JSONDecodeError:
                    arguments = {}

                try:
                    result = await self._tool_registry.execute(
                        tool_name, arguments
                    )
                except Exception as exc:
                    result = f"error: {exc}"

                tool_results.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call_id,
                        "content": result,
                    }
                )

                tool_belief = Belief(
                    content=result,
                    source="tool",
                    id=str(uuid.uuid4()),
                    timestamp=current_time_ms(),
                    last_accessed=current_time_ms(),
                    metadata={
                        "tool_name": tool_name,
                        "tool_call_id": tool_call_id,
                    },
                )
                await self._belief_store.add(
                    conversation_id, tool_belief
                )

            tool_call_count += 1

        if full_response and pending_tool_calls:
            assistant_belief = Belief(
                content=full_response,
                source="assistant",
                id=str(uuid.uuid4()),
                timestamp=current_time_ms(),
                last_accessed=current_time_ms(),
            )
            await self._belief_store.add(conversation_id, assistant_belief)
            yield full_response

    async def _background_update(
        self,
        message: str,
        response: str,
        conversation_id: str,
    ) -> None:
        now_ms = current_time_ms()

        rule_writer = RuleBasedWriter(
            store=self._belief_store,
            entity_extractor=self._entity_extractor,
            emotion_analyzer=self._emotion_analyzer,
            conversation_id=conversation_id,
            source="user",
        )
        rule_beliefs = await rule_writer.process(message, now_ms)

        manual_writer = ManualMemoryWriter(
            store=self._belief_store,
            entity_extractor=self._entity_extractor,
            emotion_analyzer=self._emotion_analyzer,
            conversation_id=conversation_id,
            source="user",
        )
        manual_beliefs = await manual_writer.process(message, now_ms)

        ai_writer = AiInferenceWriter(
            store=self._belief_store,
            entity_extractor=self._entity_extractor,
            emotion_analyzer=self._emotion_analyzer,
            conversation_id=conversation_id,
            source="assistant",
        )
        ai_belief = await ai_writer.process_llm_output(
            llm_content=response,
            importance=0.6,
            timestamp_ms=now_ms,
        )

        recent_beliefs = await self._belief_store.get(
            conversation_id, limit=10
        )
        turns = [
            {"content": b.content, "source": b.source}
            for b in recent_beliefs
        ]
        composite_detector = CompositeBeliefDetector(
            store=self._belief_store,
            entity_extractor=self._entity_extractor,
            emotion_analyzer=self._emotion_analyzer,
            conversation_id=conversation_id,
            source="assistant",
        )
        composite_beliefs = await composite_detector.process_multi_turn(
            turns, now_ms
        )

        all_new_beliefs = rule_beliefs + manual_beliefs
        if ai_belief is not None:
            all_new_beliefs.append(ai_belief)
        all_new_beliefs.extend(composite_beliefs)

        for new_belief in all_new_beliefs:
            if not new_belief.entities:
                continue
            similar = await self._belief_store.search_similar(
                new_belief.content,
                top_k=3,
                min_confidence=0.3,
            )
            for existing, sim_score in similar:
                if (
                    sim_score > 0.8
                    and existing.id != new_belief.id
                    and existing.status == "active"
                ):
                    emotion_diff = abs(
                        existing.emotion - new_belief.emotion
                    )
                    if emotion_diff > 0.5:
                        await self._belief_store.overthrow(
                            old_id=existing.id,
                            new_id=new_belief.id,
                            reason=(
                                f"Contradicting emotion: "
                                f"{existing.emotion:.2f} vs "
                                f"{new_belief.emotion:.2f}"
                            ),
                        )

        for belief in recent_beliefs:
            belief.last_accessed = now_ms
            await self._belief_store.update(belief)
