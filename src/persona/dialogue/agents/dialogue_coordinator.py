# Copyright 2026 ShuyuanCore contributors
# SPDX-License-Identifier: Apache-2.0
"""对话协调器。

协调多个 Agent 的协作流程
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .base_agent import AgentConfig, BaseAgent, TaskStatus
from .agent_protocol import AgentMessage, MessageType, Priority, Protocol
from .decision_agent import DecisionAgent, DecisionContext, DecisionOutput
from .review_agent import ReviewAgent
from .arbitrate_agent import ArbitrateAgent

logger = logging.getLogger(__name__)


@dataclass
class DialogueConfig:
    """对话配置"""
    
    enable_decision: bool = True
    enable_review: bool = True
    enable_arbitrate: bool = True
    max_review_iterations: int = 3
    enable_caching: bool = True


@dataclass
class DialogueResult:
    """对话结果"""
    
    final_response: str
    decision_output: Optional[DecisionOutput] = None
    review_result: Optional[Dict[str, Any]] = None
    arbitration_result: Optional[Dict[str, Any]] = None
    review_iterations: int = 0
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "final_response": self.final_response,
            "decision_output": self.decision_output.to_dict() if self.decision_output else None,
            "review_result": self.review_result,
            "arbitration_result": self.arbitration_result,
            "review_iterations": self.review_iterations,
            "errors": self.errors,
            "warnings": self.warnings,
            "metadata": self.metadata,
        }


class DialogueCoordinator:
    """对话协调器
    
    协调 Decision/Review/Arbitrate Agent 的协作流程
    
    流程：
    1. DecisionAgent 生成初始回复
    2. ReviewAgent 审视回复
    3. 如果需要修正 → ArbitrateAgent 仲裁
    4. 最多迭代 max_review_iterations 次
    5. 返回最终回复
    """
    
    def __init__(
        self,
        config: Optional[DialogueConfig] = None,
        decision_agent: Optional[DecisionAgent] = None,
        review_agent: Optional[ReviewAgent] = None,
        arbitrate_agent: Optional[ArbitrateAgent] = None,
    ):
        """初始化对话协调器
        
        Args:
            config: 对话配置
            decision_agent: 决策 Agent
            review_agent: 审视 Agent
            arbitrate_agent: 仲裁 Agent
        """
        self.config = config or DialogueConfig()
        
        self._decision_agent = decision_agent or DecisionAgent()
        self._review_agent = review_agent or ReviewAgent()
        self._arbitrate_agent = arbitrate_agent or ArbitrateAgent()
        
        logger.info("[coordinator] 对话协调器初始化完成，配置：%s", self.config)
    
    async def orchestrate(
        self,
        user_message: str,
        persona_id: str,
        style_dimensions: Dict[str, Any],
        anchor_vector: Optional[List[float]] = None,
        conversation_history: List[Dict[str, Any]] = None,
        perception_result: Optional[Any] = None,
        inner_reaction: Optional[str] = None,
    ) -> DialogueResult:
        """编排对话流程
        
        Args:
            user_message: 用户消息
            persona_id: 人格 ID
            style_dimensions: 风格维度
            anchor_vector: 锚点向量
            conversation_history: 对话历史
            perception_result: 感知结果
            inner_reaction: 内心反应
        
        Returns:
            DialogueResult: 对话结果
        """
        result = DialogueResult(final_response="")
        
        try:
            # Step 1: DecisionAgent 生成初始回复
            if self.config.enable_decision:
                decision_output = await self._decision_step(
                    user_message=user_message,
                    persona_id=persona_id,
                    style_dimensions=style_dimensions,
                    anchor_vector=anchor_vector,
                    conversation_history=conversation_history,
                    perception_result=perception_result,
                    inner_reaction=inner_reaction,
                )
                result.decision_output = decision_output
                result.final_response = decision_output.response
            else:
                result.warnings.append("DecisionAgent 已禁用")
                return result
            
            # Step 2: ReviewAgent 审视回复
            if self.config.enable_review:
                for iteration in range(self.config.max_review_iterations):
                    result.review_iterations = iteration + 1
                    
                    review_passed, review_result = await self._review_step(
                        response=result.final_response,
                        style_dimensions=style_dimensions,
                        perception_result=perception_result,
                    )
                    result.review_result = review_result
                    
                    # 如果通过审视，结束
                    if review_passed:
                        logger.info(
                            "[coordinator] 审视通过：iteration=%d",
                            iteration + 1,
                        )
                        break
                    
                    # 如果需要修正，调用 ArbitrateAgent
                    if self.config.enable_arbitrate:
                        arbitration_result = await self._arbitrate_step(
                            response=result.final_response,
                            review_result=review_result,
                            anchor_vector=anchor_vector,
                        )
                        result.arbitration_result = arbitration_result
                        
                        # 更新回复
                        if arbitration_result.get("success", False):
                            result.final_response = arbitration_result.get(
                                "corrected_response",
                                result.final_response,
                            )
                        else:
                            result.warnings.append(
                                f"仲裁失败（iteration={iteration + 1}）"
                            )
                            break
                    else:
                        result.warnings.append("ArbitrateAgent 已禁用")
                        break
            else:
                result.warnings.append("ReviewAgent 已禁用")
            
            result.metadata["pipeline_success"] = True
            result.metadata["config"] = self.config.__dict__
            
            logger.info(
                "[coordinator] 编排完成：response_length=%d, iterations=%d",
                len(result.final_response),
                result.review_iterations,
            )
            
        except Exception as e:
            error_msg = f"编排失败：{str(e)}"
            logger.exception("[coordinator] %s", error_msg)
            result.errors.append(error_msg)
            result.metadata["pipeline_success"] = False
        
        return result
    
    async def _decision_step(
        self,
        user_message: str,
        persona_id: str,
        style_dimensions: Dict[str, Any],
        anchor_vector: Optional[List[float]] = None,
        conversation_history: List[Dict[str, Any]] = None,
        perception_result: Optional[Any] = None,
        inner_reaction: Optional[str] = None,
    ) -> DecisionOutput:
        """决策步骤
        
        Args:
            user_message: 用户消息
            persona_id: 人格 ID
            style_dimensions: 风格维度
            anchor_vector: 锚点向量
            conversation_history: 对话历史
            perception_result: 感知结果
            inner_reaction: 内心反应
        
        Returns:
            DecisionOutput: 决策输出
        """
        # 构建上下文
        context = DecisionContext(
            user_message=user_message,
            persona_id=persona_id,
            style_dimensions=style_dimensions,
            anchor_vector=anchor_vector,
            conversation_history=conversation_history or [],
            perception_result=perception_result,
            inner_reaction=inner_reaction,
        )
        
        # 构建消息
        message = AgentMessage(
            message_type=MessageType.REQUEST,
            sender="coordinator",
            receiver=self._decision_agent.config.agent_id,
            content=context,
            priority=Priority.NORMAL,
        )
        
        # 执行
        task_result = await self._decision_agent.run(message)
        
        if task_result.status != TaskStatus.COMPLETED:
            raise RuntimeError(f"DecisionAgent 执行失败：{task_result.error}")
        
        return task_result.result.content
    
    async def _review_step(
        self,
        response: str,
        style_dimensions: Dict[str, Any],
        perception_result: Optional[Any] = None,
    ) -> Tuple[bool, Dict[str, Any]]:
        """审视步骤
        
        Args:
            response: 回复文本
            style_dimensions: 风格维度
            perception_result: 感知结果
        
        Returns:
            Tuple[bool, Dict]: 是否通过、审视结果
        """
        # 构建上下文
        context = {
            "response": response,
            "context": {
                "style_dimensions": style_dimensions,
                "atmosphere": perception_result.atmosphere if perception_result else "daily",
                "emotion": perception_result.user_emotion if perception_result else "neutral",
            },
        }
        
        # 构建消息
        message = AgentMessage(
            message_type=MessageType.REQUEST,
            sender="coordinator",
            receiver=self._review_agent.config.agent_id,
            content=context,
            priority=Priority.NORMAL,
        )
        
        # 执行
        task_result = await self._review_agent.run(message)
        
        if task_result.status != TaskStatus.COMPLETED:
            raise RuntimeError(f"ReviewAgent 执行失败：{task_result.error}")
        
        output = task_result.result.content
        passed = output.get("review_passed", False)
        
        return passed, output
    
    async def _arbitrate_step(
        self,
        response: str,
        review_result: Dict[str, Any],
        anchor_vector: Optional[List[float]] = None,
    ) -> Dict[str, Any]:
        """仲裁步骤
        
        Args:
            response: 回复文本
            review_result: 审视结果
            anchor_vector: 锚点向量
        
        Returns:
            Dict: 仲裁结果
        """
        # 构建上下文
        context = {
            "response": response,
            "review_result": review_result,
            "anchor_vector": anchor_vector or [],
        }
        
        # 构建消息
        message = AgentMessage(
            message_type=MessageType.REQUEST,
            sender="coordinator",
            receiver=self._arbitrate_agent.config.agent_id,
            content=context,
            priority=Priority.NORMAL,
        )
        
        # 执行
        task_result = await self._arbitrate_agent.run(message)
        
        if task_result.status != TaskStatus.COMPLETED:
            raise RuntimeError(f"ArbitrateAgent 执行失败：{task_result.error}")
        
        return task_result.result.content


def create_coordinator(
    enable_decision: bool = True,
    enable_review: bool = True,
    enable_arbitrate: bool = True,
) -> DialogueCoordinator:
    """创建对话协调器
    
    Args:
        enable_decision: 是否启用决策 Agent
        enable_review: 是否启用审视 Agent
        enable_arbitrate: 是否启用仲裁 Agent
    
    Returns:
        DialogueCoordinator: 对话协调器
    """
    config = DialogueConfig(
        enable_decision=enable_decision,
        enable_review=enable_review,
        enable_arbitrate=enable_arbitrate,
    )
    
    return DialogueCoordinator(config=config)
