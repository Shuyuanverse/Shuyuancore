# Copyright 2026 ShuyuanCore contributors
# SPDX-License-Identifier: Apache-2.0
"""多智能体对话系统。

包含：
- agents: Agent 模块（Decision/Review/Arbitrate/Coordinator）
- style_consistency_checker: 风格一致性检测
- style_constraint: 风格约束编码
- hard_fact_guard: 硬事实守卫
- context_manager: 上下文管理
- memory_mechanism: 记忆机制
- dialog_state_machine: 对话状态机
- constrained_decoder: 约束引导解码
- backtrack_rewriter: 回溯重写器
"""

from __future__ import annotations

from .agents import (
    # Base Agent
    AgentConfig,
    # Protocol
    AgentMessage,
    AgentStatus,
    # Arbitrate Agent
    ArbitrateAgent,
    ArbitrationResult,
    BaseAgent,
    # Review Agent
    ConflictDetectionResult,
    ConflictLevel,
    CoordinatedResult,
    # Coordinator
    CoordinatorConfig,
    CorrectionStrategy,
    # Decision Agent
    DecisionAgent,
    DecisionConfig,
    DecisionContext,
    DecisionOutput,
    DialogueCoordinator,
    MessageBuilder,
    MessageType,
    Priority,
    Protocol,
    ReviewAgent,
    ReviewAgentContextExtension,
    TaskPriority,
    TaskResult,
    TaskStatus,
    VectorSpaceCorrector,
    WorkflowContext,
    create_coordinator,
)
from .backtrack_rewriter import (
    BacktrackRewriter,
    RewriteCandidate,
    RewritePoint,
    RewriteResult,
    RewriteStrategy,
    RewriteTrigger,
)
from .constrained_decoder import (
    ConstrainedDecoder,
    DecodingResult,
)
from .context_manager import (
    CompressionStrategy,
    ContextConfig,
    ContextManager,
    DialogMessage,
    MessageImportance,
    MessageRole,
)
from .dialog_state_machine import (
    DialogContext,
    DialogState,
    DialogStateMachine,
    StateHandler,
)
from .hard_fact_guard import (
    HardFactGuard,
    InputCheckResult,
    OutputCheckResult,
)
from .memory_mechanism import (
    MemoryEntry,
    MemoryMechanism,
    MemoryType,
    RecallResult,
)
from .style_consistency_checker import (
    ConsistencyLevel,
    ConsistencyResult,
    DimensionScore,
    StyleConsistencyChecker,
)
from .style_constraint import (
    ConstraintDimension,
    ConstraintType,
    ConstraintVector,
    StyleConstraintEncoder,
)

__all__ = [
    # Agents
    "AgentMessage",
    "MessageBuilder",
    "MessageType",
    "Priority",
    "Protocol",
    "AgentConfig",
    "AgentStatus",
    "BaseAgent",
    "TaskPriority",
    "TaskResult",
    "TaskStatus",
    "DecisionAgent",
    "DecisionConfig",
    "DecisionContext",
    "DecisionOutput",
    "ConflictDetectionResult",
    "ConflictLevel",
    "ReviewAgent",
    "ReviewAgentContextExtension",
    "ArbitrateAgent",
    "ArbitrationResult",
    "CorrectionStrategy",
    "VectorSpaceCorrector",
    "CoordinatorConfig",
    "DialogueCoordinator",
    "CoordinatedResult",
    "WorkflowContext",
    "CoordinatedResult",
    "create_coordinator",
    # Style Consistency
    "ConsistencyLevel",
    "DimensionScore",
    "StyleConsistencyChecker",
    "ConsistencyResult",
    # Style Constraint
    "ConstraintDimension",
    "ConstraintType",
    "ConstraintVector",
    "StyleConstraintEncoder",
    # Hard Fact Guard
    "HardFactGuard",
    "InputCheckResult",
    "OutputCheckResult",
    # Context Manager
    "CompressionStrategy",
    "ContextConfig",
    "ContextManager",
    "DialogMessage",
    "MessageImportance",
    "MessageRole",
    # Memory Mechanism
    "MemoryEntry",
    "MemoryMechanism",
    "MemoryType",
    "RecallResult",
    # Dialog State Machine
    "DialogContext",
    "DialogState",
    "DialogStateMachine",
    "StateHandler",
    # Constrained Decoder
    "ConstrainedDecoder",
    "DecodingResult",
    # Backtrack Rewriter
    "BacktrackRewriter",
    "RewriteCandidate",
    "RewritePoint",
    "RewriteResult",
    "RewriteStrategy",
    "RewriteTrigger",
]
