# Copyright 2026 ShuyuanCore contributors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Callable, Optional

from src.config import get_settings
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
from src.memory.relational import RelationalMemory
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

logger = logging.getLogger(__name__)


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
        skill_store: Any | None = None,
        entity_extractor: IEntityExtractor | None = None,
        emotion_analyzer: IEmotionAnalyzer | None = None,
        coordinator: Any | None = None,
    ) -> None:
        self._model_provider = model_provider
        self._belief_store = belief_store
        self._reader = reader
        self._tool_registry = tool_registry or MockToolRegistry()
        self._memory_store = memory_store or NoOpMemoryStore()
        self._persona_guard = persona_guard or NoOpPersonaGuard()
        self._skill_engine = skill_engine or NoOpSkillEngine()
        self._skill_store = skill_store
        self._entity_extractor = entity_extractor or JiebaEntityExtractor()
        self._emotion_analyzer = emotion_analyzer or SnowNlpEmotionAnalyzer()
        self._coordinator = coordinator
        self._dangerous_tools: set[str] = set()
        self._pending_resume_event: asyncio.Event | None = None
        self._approval_approved: bool = True
        
        # 预测式建模集成
        self._settings = get_settings()
        self.user_model = RelationalMemory(db_path="data/state.db")
        self._last_activity_time: float = time.time()
        self._idle_monitor_task: Optional[asyncio.Task] = None
        self._proactive_count: int = 0
        self._current_conversation_id: Optional[str] = None
        self._is_cli: bool = True
        self._sse_send: Optional[Callable] = None
        self._proactive_queue: asyncio.Queue = asyncio.Queue()

    def set_dangerous_tools(self, tool_names: list[str]) -> None:
        self._dangerous_tools = set(tool_names)

    async def chat_stream(
        self,
        message: str,
        conversation_id: str | None = None,
        resume_event: asyncio.Event | None = None,
    ) -> AsyncIterator[str | dict[str, Any]]:
        if conversation_id is None:
            conversation_id = str(uuid.uuid4())
        
        # 更新活动时间和重置计数
        self._last_activity_time = time.time()
        self._proactive_count = 0
        self._current_conversation_id = conversation_id
        
        # 取消旧监控任务并启动新的
        if self._idle_monitor_task and not self._idle_monitor_task.done():
            self._idle_monitor_task.cancel()
            try:
                await self._idle_monitor_task
            except asyncio.CancelledError:
                pass
        
        if self._settings.prediction.enable_proactive:
            self._idle_monitor_task = asyncio.create_task(self._idle_monitor())
        
        conversation_date = datetime.now(timezone.utc).date().isoformat()

        user_belief = Belief(
            content=message,
            source="user",
            id=str(uuid.uuid4()),
            timestamp=current_time_ms(),
            last_accessed=current_time_ms(),
            conversation_date=conversation_date,
        )
        await self._belief_store.add(conversation_id, user_belief)

        readiness = wake_readiness(message)
        if readiness > 0.5:
            similar = await self._belief_store.search_similar(message, top_k=5, min_confidence=0.1)
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

        skill_context: list[dict[str, Any]] = []
        if self._skill_store:
            try:
                from src.memory.embedding import EmbeddingService
                from src.skills.matcher import (
                    format_skill_for_prompt,
                    match_skill,
                )

                embedding_service = EmbeddingService(self._model_provider)
                matched = await match_skill(
                    user_message=message,
                    belief_store=self._belief_store,
                    skill_store=self._skill_store,
                    embedding_service=embedding_service,
                )
                if matched is not None:
                    skill_prompt = format_skill_for_prompt(matched)
                    skill_context = [
                        {
                            "role": "system",
                            "content": skill_prompt,
                        }
                    ]
            except Exception:
                logger.exception("skill_matching_error")

        while tool_call_count < _MAX_TOOL_CALLS_PER_TURN:
            context = await self._reader.read(
                conversation_id=conversation_id,
                user_query=message,
                max_tokens=4000,
            )
            if skill_context:
                context = skill_context + context

            if self._coordinator is not None and tool_call_count == 0:
                try:
                    from src.agents.interfaces import UpdateContext
                    from src.config import get_settings

                    cfg = get_settings()
                    ctx = UpdateContext(
                        conversation_id=conversation_id,
                        user_id=conversation_id,
                        message=message,
                        history=context,
                        belief_store=self._belief_store,
                        skill_store=self._skill_store,
                        user_preference_weights=cfg.agents.user_preference_weights,
                    )
                    coordinator_result = await self._coordinator.run(ctx)
                    full_response = coordinator_result
                    yield coordinator_result
                    assistant_belief = Belief(
                        content=full_response,
                        source="assistant",
                        id=str(uuid.uuid4()),
                        timestamp=current_time_ms(),
                        last_accessed=current_time_ms(),
                        conversation_date=conversation_date,
                    )
                    await self._belief_store.add(conversation_id, assistant_belief)
                    break
                except Exception:
                    logger.exception("coordinator_failed_fallback_to_llm")

            pending_tool_calls: list[dict[str, Any]] = []

            async for event in self._model_provider.chat_stream(history=context):
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
                    conversation_date=conversation_date,
                )
                await self._belief_store.add(conversation_id, assistant_belief)
                break

            tool_results: list[dict[str, Any]] = []
            for tc in pending_tool_calls:
                tool_call_id = tc.get("id", "")
                func_info = tc.get("function", {})
                tool_name = func_info.get("name", "")
                raw_args = func_info.get("arguments", "{}")
                try:
                    arguments = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                except json.JSONDecodeError:
                    arguments = {}

                try:
                    require_approval = (
                        tool_name in self._dangerous_tools and resume_event is not None
                    )
                    if require_approval:
                        assert resume_event is not None
                        approval_id = f"stream_{uuid.uuid4().hex[:8]}"
                        self._pending_resume_event = resume_event
                        yield {
                            "type": "approval",
                            "approval_id": approval_id,
                            "tool_name": tool_name,
                            "arguments": arguments,
                            "message": f"工具 {tool_name} 需要审批",
                        }
                        await resume_event.wait()
                        resume_event.clear()
                        self._pending_resume_event = None
                        if not getattr(self, "_approval_approved", True):
                            result = f"error: tool {tool_name} rejected by user"
                            yield {
                                "type": "approval_result",
                                "approved": False,
                                "tool_name": tool_name,
                            }
                            tool_results.append(
                                {
                                    "role": "tool",
                                    "tool_call_id": tool_call_id,
                                    "content": result,
                                }
                            )
                            continue

                    result = await self._tool_registry.execute(tool_name, arguments)
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
                    conversation_date=conversation_date,
                    metadata={
                        "tool_name": tool_name,
                        "tool_call_id": tool_call_id,
                    },
                )
                await self._belief_store.add(conversation_id, tool_belief)

            tool_call_count += 1

        if full_response and pending_tool_calls:
            assistant_belief = Belief(
                content=full_response,
                source="assistant",
                id=str(uuid.uuid4()),
                timestamp=current_time_ms(),
                last_accessed=current_time_ms(),
                conversation_date=conversation_date,
            )
            await self._belief_store.add(conversation_id, assistant_belief)
            yield full_response

        if full_response:
            asyncio.create_task(
                self._background_update(
                    message=message,
                    response=full_response,
                    conversation_id=conversation_id,
                )
            )

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

        recent_beliefs = await self._belief_store.get(conversation_id, limit=10)
        turns = [{"content": b.content, "source": b.source} for b in recent_beliefs]
        composite_detector = CompositeBeliefDetector(
            store=self._belief_store,
            entity_extractor=self._entity_extractor,
            emotion_analyzer=self._emotion_analyzer,
            conversation_id=conversation_id,
            source="assistant",
        )
        composite_beliefs = await composite_detector.process_multi_turn(turns, now_ms)

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
                if sim_score > 0.8 and existing.id != new_belief.id and existing.status == "active":
                    emotion_diff = abs(existing.emotion - new_belief.emotion)
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

        if self._skill_store:
            try:
                from src.skills.extractor import extract_skill

                await extract_skill(
                    conversation_id=conversation_id,
                    message=message,
                    response=response,
                    belief_store=self._belief_store,
                    skill_store=self._skill_store,
                    model_provider=self._model_provider,
                )
            except Exception:
                logger.exception("skill extraction failed conv=%s", conversation_id)

    async def _idle_monitor(self) -> None:
        """后台空闲监控任务：检测用户长时间不输入，主动发起预测提醒。"""
        cfg = self._settings.prediction
        if not cfg.enable_proactive:
            return
        
        while True:
            try:
                await asyncio.sleep(cfg.idle_timeout_seconds)
                
                # 如果已经达到最大提醒次数，停止监控
                if self._proactive_count >= cfg.max_idle_checks_per_conversation:
                    return
                
                # 检查空闲时间
                now = time.time()
                if now - self._last_activity_time < cfg.idle_timeout_seconds:
                    continue
                
                # 尝试预测
                pred = await self.user_model.predict_next(self._current_conversation_id or "")
                if not pred:
                    continue
                
                confidence = pred.get("confidence", 0)
                if confidence < cfg.confidence_threshold:
                    continue
                
                # 将提醒放入队列（供 API 模式消费）
                await self._proactive_queue.put(pred)
                
                # 发送提醒（CLI 模式直接打印，API 模式通过回调）
                await self._send_proactive_prompt(pred)
                self._proactive_count += 1
                
            except asyncio.CancelledError:
                logger.debug("Idle monitor task cancelled")
                return
            except Exception as e:
                logger.warning("Idle monitor error: %s", e)
                continue

    async def _send_proactive_prompt(self, prediction: dict[str, Any]) -> None:
        """发送主动提醒。
        
        Args:
            prediction: 预测结果，包含 predicted_action, confidence, suggested_response
        """
        message = prediction.get("suggested_response") or prediction.get("predicted_action")
        if not message:
            return
        
        if self._is_cli:
            # CLI 模式，直接打印
            print(f"\n[💡 主动提醒] {message}\n")
        else:
            # API 模式，通过 SSE 发送事件
            if self._sse_send:
                try:
                    await self._sse_send(
                        "prompt",
                        {
                            "message": message,
                            "confidence": prediction.get("confidence"),
                            "predicted_action": prediction.get("predicted_action"),
                        },
                    )
                except Exception as e:
                    logger.warning("SSE send failed: %s", e)
