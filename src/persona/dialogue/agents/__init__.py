# Copyright 2026 ShuyuanCore contributors
# SPDX-License-Identifier: Apache-2.0
"""多智能体对话系统 — Agent 模块。

包含：
- agent_protocol：消息协议
- base_agent：Agent 基类
- decision_agent：决策 Agent
- review_agent：审视 Agent
- arbitrate_agent：仲裁 Agent
- dialogue_coordinator：对话协调器
"""

from __future__ import annotations

from .agent_protocol import (
    AgentMessage,
    MessageBuilder,
    MessageType,
    Priority,
    Protocol,
)
from .base_agent import (
    AgentConfig,
    AgentStatus,
    BaseAgent,
    TaskPriority,
    TaskResult,
    TaskStatus,
)
from .decision_agent import (
    DecisionAgent,
    DecisionConfig,
    DecisionContext,
    DecisionOutput,
)
from .review_agent import (
    ConflictDetectionResult,
    ConflictLevel,
    ReviewAgent,
    ReviewAgentContextExtension,
)
from .arbitrate_agent import (
    ArbitrateAgent,
    ArbitrationResult,
    CorrectionStrategy,
    VectorSpaceCorrector,
)
from .dialogue_coordinator import (
    DialogueConfig,
    DialogueCoordinator,
    DialogueResult,
    create_coordinator,
)

__all__ = [
    # Protocol
    "AgentMessage",
    "MessageBuilder",
    "MessageType",
    "Priority",
    "Protocol",
    # Base Agent
    "AgentConfig",
    "AgentStatus",
    "BaseAgent",
    "TaskPriority",
    "TaskResult",
    "TaskStatus",
    # Decision Agent
    "DecisionAgent",
    "DecisionConfig",
    "DecisionContext",
    "DecisionOutput",
    # Review Agent
    "ConflictDetectionResult",
    "ConflictLevel",
    "ReviewAgent",
    "ReviewAgentContextExtension",
    # Arbitrate Agent
    "ArbitrateAgent",
    "ArbitrationResult",
    "CorrectionStrategy",
    "VectorSpaceCorrector",
    # Coordinator
    "DialogueConfig",
    "DialogueCoordinator",
    "DialogueResult",
    "create_coordinator",
]
