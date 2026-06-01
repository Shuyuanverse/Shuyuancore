# Copyright 2026 ShuyuanCore contributors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import logging
from enum import StrEnum
from typing import Any

logger = logging.getLogger(__name__)


class AgentMode(StrEnum):
    CHAT = "chat"
    AGENT = "agent"
    SKILL = "skill"
    TOOL = "tool"


class CoreRouter:
    def __init__(self) -> None:
        self._agent_mode_enabled: bool = False

    def set_agent_mode(self, enabled: bool) -> None:
        self._agent_mode_enabled = enabled

    async def route_message(
        self,
        conversation_id: str,
        message: str,
        context: dict[str, Any] | None = None,
    ) -> str:
        if not message or not message.strip():
            return AgentMode.CHAT

        ctx = context or {}

        if self._agent_mode_enabled:
            return AgentMode.AGENT

        message_lower = message.strip().lower()

        trigger_prefixes = ctx.get("agent_triggers", None)
        if trigger_prefixes is not None:
            for prefix in trigger_prefixes:
                if isinstance(prefix, str) and message_lower.startswith(prefix.lower()):
                    return AgentMode.AGENT

        matched_skill = ctx.get("matched_skill", None)
        if matched_skill is not None:
            return AgentMode.SKILL

        return AgentMode.CHAT

    async def route_to_agent(
        self,
        conversation_id: str,
        message: str,
        mode: str | None = None,
    ) -> dict[str, Any]:
        logger.info(
            "Routing to agent: conv=%s mode=%s message_preview=%s",
            conversation_id,
            mode or "default",
            message[:60],
        )
        return {
            "conversation_id": conversation_id,
            "mode": mode or "default",
            "handler": "agent",
        }

    async def route_to_skill(
        self,
        conversation_id: str,
        message: str,
        matched_skill: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        skill_name = (matched_skill or {}).get("name", "unknown")
        logger.info(
            "Routing to skill: conv=%s skill=%s message_preview=%s",
            conversation_id,
            skill_name,
            message[:60],
        )
        return {
            "conversation_id": conversation_id,
            "skill": skill_name,
            "handler": "skill",
        }

    async def route_to_tool(
        self,
        conversation_id: str,
        tool_name: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        logger.info(
            "Routing to tool: conv=%s tool=%s params=%s",
            conversation_id,
            tool_name,
            params,
        )
        return {
            "conversation_id": conversation_id,
            "tool": tool_name,
            "params": params or {},
            "handler": "tool",
        }
