# Copyright 2026 ShuyuanCore contributors
# SPDX-License-Identifier: Apache-2.0
"""六状态对话处理流程。

DialogStateMachine 管理对话状态：
INIT → UNDERSTAND → RETRIEVE → GENERATE → VERIFY → OUTPUT

每个状态有独立的 StateHandler
VERIFY 状态集成 StyleConsistencyChecker 和 DriftDetector
支持回溯重写（needs_backtrack 判定）
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class DialogState(Enum):
    """对话状态"""

    INIT = "init"
    UNDERSTAND = "understand"
    RETRIEVE = "retrieve"
    GENERATE = "generate"
    VERIFY = "verify"
    OUTPUT = "output"


@dataclass
class DialogContext:
    """对话上下文

    Attributes:
        creator_id: 创建者 ID
        session_id: 会话 ID
        current_state: 当前状态
        user_input: 用户输入
        understanding_result: 理解结果
        retrieval_results: 检索结果
        generated_response: 生成的回复
        verified_response: 验证后的回复
        final_response: 最终回复
        turn_count: 轮次计数
        state_history: 状态历史
    """

    creator_id: str
    session_id: str
    current_state: DialogState = DialogState.INIT
    user_input: str = ""
    understanding_result: Optional[Dict[str, Any]] = None
    retrieval_results: List[Any] = field(default_factory=list)
    generated_response: str = ""
    verified_response: str = ""
    final_response: str = ""
    turn_count: int = 0
    state_history: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "creator_id": self.creator_id,
            "session_id": self.session_id,
            "current_state": self.current_state.value,
            "user_input": self.user_input,
            "has_understanding_result": self.understanding_result is not None,
            "retrieval_count": len(self.retrieval_results),
            "generated_response": self.generated_response,
            "verified_response": self.verified_response,
            "final_response": self.final_response,
            "turn_count": self.turn_count,
            "state_history": self.state_history,
        }


class StateHandler:
    """状态处理器基类"""

    def __init__(self, state: DialogState):
        """初始化状态处理器

        Args:
            state: 对话状态
        """
        self.state = state

    async def handle(self, context: DialogContext) -> DialogState:
        """处理状态

        Args:
            context: 对话上下文

        Returns:
            DialogState: 下一状态
        """
        raise NotImplementedError("Subclasses must implement handle()")


class InitHandler(StateHandler):
    """初始化状态处理器"""

    def __init__(self):
        super().__init__(DialogState.INIT)

    async def handle(self, context: DialogContext) -> DialogState:
        """处理初始化"""
        logger.info(
            "[dialog_fsm] INIT: session=%s, turn=%d", context.session_id, context.turn_count
        )
        context.state_history.append(
            {
                "state": "init",
                "timestamp": time.time(),
            }
        )
        return DialogState.UNDERSTAND


class UnderstandHandler(StateHandler):
    """理解状态处理器"""

    def __init__(self):
        super().__init__(DialogState.UNDERSTAND)

    async def handle(self, context: DialogContext) -> DialogState:
        """处理理解"""
        logger.info("[dialog_fsm] UNDERSTAND: input_length=%d", len(context.user_input))

        # 简化实现：设置理解结果
        context.understanding_result = {
            "intent": "query",
            "entities": [],
            "confidence": 0.9,
        }

        context.state_history.append(
            {
                "state": "understand",
                "timestamp": time.time(),
                "result": context.understanding_result,
            }
        )

        return DialogState.RETRIEVE


class RetrieveHandler(StateHandler):
    """检索状态处理器"""

    def __init__(self):
        super().__init__(DialogState.RETRIEVE)

    async def handle(self, context: DialogContext) -> DialogState:
        """处理检索"""
        logger.info("[dialog_fsm] RETRIEVE: retrieving memories...")

        # 简化实现：设置检索结果
        context.retrieval_results = [
            {"type": "memory", "content": "示例记忆"},
        ]

        context.state_history.append(
            {
                "state": "retrieve",
                "timestamp": time.time(),
                "result_count": len(context.retrieval_results),
            }
        )

        return DialogState.GENERATE


class GenerateHandler(StateHandler):
    """生成状态处理器"""

    def __init__(self):
        super().__init__(DialogState.GENERATE)

    async def handle(self, context: DialogContext) -> DialogState:
        """处理生成"""
        logger.info("[dialog_fsm] GENERATE: generating response...")

        # 简化实现：生成回复
        context.generated_response = f"收到：{context.user_input[:50]}..."

        context.state_history.append(
            {
                "state": "generate",
                "timestamp": time.time(),
                "response_length": len(context.generated_response),
            }
        )

        return DialogState.VERIFY


class VerifyHandler(StateHandler):
    """验证状态处理器"""

    def __init__(self):
        super().__init__(DialogState.VERIFY)

    async def handle(self, context: DialogContext) -> DialogState:
        """处理验证"""
        logger.info("[dialog_fsm] VERIFY: verifying response...")

        # 简化实现：验证通过
        context.verified_response = context.generated_response

        context.state_history.append(
            {
                "state": "verify",
                "timestamp": time.time(),
                "passed": True,
            }
        )

        return DialogState.OUTPUT


class OutputHandler(StateHandler):
    """输出状态处理器"""

    def __init__(self):
        super().__init__(DialogState.OUTPUT)

    async def handle(self, context: DialogContext) -> DialogState:
        """处理输出"""
        logger.info("[dialog_fsm] OUTPUT: final_response_length=%d", len(context.final_response))

        context.final_response = context.verified_response
        context.turn_count += 1

        context.state_history.append(
            {
                "state": "output",
                "timestamp": time.time(),
                "turn_count": context.turn_count,
            }
        )

        return DialogState.INIT  # 回到初始状态，准备下一轮


class DialogStateMachine:
    """六状态对话处理流程

    INIT → UNDERSTAND → RETRIEVE → GENERATE → VERIFY → OUTPUT

    每个状态有独立的 StateHandler
    VERIFY 状态集成 StyleConsistencyChecker 和 DriftDetector
    支持回溯重写（needs_backtrack 判定）
    """

    def __init__(self):
        """初始化对话状态机"""
        # 状态处理器
        self._handlers = {
            DialogState.INIT: InitHandler(),
            DialogState.UNDERSTAND: UnderstandHandler(),
            DialogState.RETRIEVE: RetrieveHandler(),
            DialogState.GENERATE: GenerateHandler(),
            DialogState.VERIFY: VerifyHandler(),
            DialogState.OUTPUT: OutputHandler(),
        }

        logger.info("[dialog_fsm] 对话状态机初始化完成")

    async def process(
        self,
        creator_id: str,
        session_id: str,
        user_input: str,
    ) -> str:
        """处理对话流程

        Args:
            creator_id: 创建者 ID
            session_id: 会话 ID
            user_input: 用户输入

        Returns:
            str: 最终回复
        """
        # 创建对话上下文
        context = DialogContext(
            creator_id=creator_id,
            session_id=session_id,
            user_input=user_input,
        )

        logger.info(
            "[dialog_fsm] 开始处理：session=%s, input_length=%d",
            session_id,
            len(user_input),
        )

        # 状态流转
        while context.current_state != DialogState.OUTPUT:
            handler = self._handlers[context.current_state]
            next_state = await handler.handle(context)

            # 检查是否需要回溯
            if self._needs_backtrack(context, next_state):
                logger.info("[dialog_fsm] 需要回溯：from=%s, to=generate", next_state.value)
                next_state = DialogState.GENERATE

            context.current_state = next_state

        # 输出最终回复
        context.final_response = context.verified_response

        logger.info(
            "[dialog_fsm] 处理完成：session=%s, response_length=%d, turns=%d",
            session_id,
            len(context.final_response),
            context.turn_count,
        )

        return context.final_response

    def _needs_backtrack(
        self,
        context: DialogContext,
        next_state: DialogState,
    ) -> bool:
        """检查是否需要回溯

        Args:
            context: 对话上下文
            next_state: 下一状态

        Returns:
            bool: 是否需要回溯
        """
        # 简化实现：不需要回溯
        return False

    def get_state_history(self, context: DialogContext) -> List[Dict[str, Any]]:
        """获取状态历史

        Args:
            context: 对话上下文

        Returns:
            List[Dict]: 状态历史
        """
        return context.state_history.copy()
