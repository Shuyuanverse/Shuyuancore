from __future__ import annotations

import json
import uuid
from typing import Any, AsyncIterator

from src.core.interfaces import (
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
    ) -> None:
        self._model_provider = model_provider
        self._belief_store = belief_store
        self._reader = reader
        self._tool_registry = tool_registry or MockToolRegistry()
        self._memory_store = memory_store or NoOpMemoryStore()
        self._persona_guard = persona_guard or NoOpPersonaGuard()
        self._skill_engine = skill_engine or NoOpSkillEngine()

    async def chat_stream(
        self,
        message: str,
        conversation_id: str | None = None,
    ) -> AsyncIterator[str]:
        if conversation_id is None:
            conversation_id = str(uuid.uuid4())

        user_belief = self._belief_store.create_belief(
            content=message,
            source="user",
        )
        self._belief_store.add(conversation_id, user_belief)

        tool_call_count = 0
        while tool_call_count < _MAX_TOOL_CALLS_PER_TURN:
            context = self._reader.read(
                conversation_id=conversation_id,
                user_query=message,
                max_tokens=4000,
            )

            full_response = ""
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
                assistant_belief = self._belief_store.create_belief(
                    content=full_response,
                    source="assistant",
                )
                self._belief_store.add(
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

                tool_belief = self._belief_store.create_belief(
                    content=result,
                    source="tool",
                    metadata={
                        "tool_name": tool_name,
                        "tool_call_id": tool_call_id,
                    },
                )
                self._belief_store.add(
                    conversation_id, tool_belief
                )

            tool_call_count += 1

        if full_response and pending_tool_calls:
            assistant_belief = self._belief_store.create_belief(
                content=full_response,
                source="assistant",
            )
            self._belief_store.add(conversation_id, assistant_belief)
            yield full_response

    async def _background_update(
        self,
        message: str,
        response: str,
        conversation_id: str,
    ) -> None:
        pass
