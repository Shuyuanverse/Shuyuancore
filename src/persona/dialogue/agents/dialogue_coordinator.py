# Copyright 2026 ShuyuanCore contributors
# SPDX-License-Identifier: Apache-2.0
"""对话协调器 — 三层 Agent 工作流。

Decision → Review → Arbitrate

完整编排流程：
1. DecisionAgent.process() → 生成初始回复
2. ReviewAgent.process() → 审视冲突
   - NONE/TOLERABLE → 直接输出
   - NEED_INTERVENTION/SEVERE → 进入 Arbitrate
3. ArbitrateAgent.process() → 修正冲突
   - 修正后重新 Review
   - 最多 2 轮 Review + 3 轮 Arbitrate
4. 输出最终回复

记忆召回：每轮都从 belief_store 召回相关记忆
上下文压缩：超过 max_tokens 时自动压缩
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .base_agent import AgentConfig, BaseAgent, TaskStatus
from .agent_protocol import AgentMessage, MessageType, Priority
from .decision_agent import DecisionAgent, DecisionContext, DecisionOutput
from .review_agent import ReviewAgent, ConflictLevel
from .arbitrate_agent import ArbitrateAgent, ArbitrationResult, CorrectionStrategy

logger = logging.getLogger(__name__)


@dataclass
class CoordinatorConfig:
    """协调器配置
    
    Attributes:
        enable_review: 是否启用审视
        enable_arbitration: 是否启用仲裁
        max_review_rounds: 最大审视轮次
        max_arbitration_rounds: 最大仲裁轮次
        auto_approve_threshold: 自动批准阈值
    """
    
    enable_review: bool = True
    enable_arbitration: bool = True
    max_review_rounds: int = 2
    max_arbitration_rounds: int = 3
    auto_approve_threshold: float = 0.85
    
    # 记忆召回配置
    enable_memory_recall: bool = True
    memory_recall_top_k: int = 5
    
    # 上下文压缩配置
    max_context_tokens: int = 8192
    enable_auto_compress: bool = True


@dataclass
class WorkflowContext:
    """三层工作流上下文
    
    Attributes:
        user_message: 用户消息
        persona_id: 人格 ID
        decision_output: 决策输出
        review_result: 审视结果
        arbitration_result: 仲裁结果
        final_response: 最终回复
        total_rounds: 总轮次
        metadata: 元数据
    """
    
    user_message: str
    persona_id: str
    decision_output: Optional[DecisionOutput] = None
    review_result: Optional[Dict[str, Any]] = None
    arbitration_result: Optional[ArbitrationResult] = None
    final_response: str = ""
    total_rounds: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "user_message": self.user_message,
            "persona_id": self.persona_id,
            "decision_output": self.decision_output.to_dict() if self.decision_output else None,
            "review_result": self.review_result,
            "arbitration_result": self.arbitration_result.to_dict() if self.arbitration_result else None,
            "final_response": self.final_response,
            "total_rounds": self.total_rounds,
            "metadata": self.metadata,
        }


@dataclass
class CoordinatedResult:
    """协调器最终输出
    
    Attributes:
        response: 最终回复
        decision_confidence: 决策置信度
        review_conflict_level: 审视冲突级别
        correction_strategy: 修正策略
        total_rounds: 总轮次
        workflow_history: 工作流历史
    """
    
    response: str
    decision_confidence: float
    review_conflict_level: Optional[ConflictLevel] = None
    correction_strategy: Optional[CorrectionStrategy] = None
    total_rounds: int = 0
    workflow_history: List[Dict[str, Any]] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "response": self.response,
            "decision_confidence": self.decision_confidence,
            "review_conflict_level": self.review_conflict_level.value if self.review_conflict_level else None,
            "correction_strategy": self.correction_strategy.value if self.correction_strategy else None,
            "total_rounds": self.total_rounds,
            "workflow_history": self.workflow_history,
        }


class DialogueCoordinator(BaseAgent):
    """对话协调器 — 三层 Agent 工作流
    
    Decision → Review → Arbitrate
    
    流程：
    1. DecisionAgent.process() → 生成初始回复
    2. ReviewAgent.process() → 审视冲突
       - NONE/TOLERABLE → 直接输出
       - NEED_INTERVENTION/SEVERE → 进入 Arbitrate
    3. ArbitrateAgent.process() → 修正冲突
       - 修正后重新 Review
       - 最多 2 轮 Review + 3 轮 Arbitrate
    4. 输出最终回复
    
    记忆召回：每轮都从 belief_store 召回相关记忆
    上下文压缩：超过 max_tokens 时自动压缩
    """
    
    def __init__(
        self,
        config: Optional[CoordinatorConfig] = None,
        decision_agent: Optional[DecisionAgent] = None,
        review_agent: Optional[ReviewAgent] = None,
        arbitrate_agent: Optional[ArbitrateAgent] = None,
        agent_config: Optional[AgentConfig] = None,
    ):
        """初始化对话协调器
        
        Args:
            config: 协调器配置
            decision_agent: 决策 Agent
            review_agent: 审视 Agent
            arbitrate_agent: 仲裁 Agent
            agent_config: Agent 配置
        """
        if agent_config is None:
            agent_config = AgentConfig(
                agent_id="dialogue_coordinator_001",
                agent_type="coordinator",
            )
        
        super().__init__(agent_config)
        
        self.config = config or CoordinatorConfig()
        
        self._decision_agent = decision_agent or DecisionAgent()
        self._review_agent = review_agent or ReviewAgent()
        self._arbitrate_agent = arbitrate_agent or ArbitrateAgent()
        
        # 工作流历史
        self._workflow_history: List[Dict[str, Any]] = []
        
        logger.info(
            "[coordinator] 对话协调器初始化完成，配置：%s",
            self.config,
        )
    
    async def coordinate(
        self,
        context: WorkflowContext,
    ) -> CoordinatedResult:
        """协调三层工作流
        
        Args:
            context: 工作流上下文
        
        Returns:
            CoordinatedResult: 协调结果
        """
        start_time = time.time()
        workflow_history = []
        
        try:
            # Step 1: DecisionAgent 生成初始回复
            workflow_history.append({"step": "decision", "status": "started"})
            
            if not context.decision_output:
                decision_msg = AgentMessage(
                    message_type=MessageType.REQUEST,
                    sender=self.config.agent_id,
                    receiver=self._decision_agent.config.agent_id,
                    content={
                        "user_message": context.user_message,
                        "persona_id": context.persona_id,
                    },
                    priority=Priority.NORMAL,
                )
                
                decision_task = await self._decision_agent.run(decision_msg)
                
                if decision_task.status == TaskStatus.COMPLETED:
                    context.decision_output = decision_task.result.content
                    workflow_history[-1]["status"] = "completed"
                    workflow_history[-1]["confidence"] = context.decision_output.confidence
                else:
                    workflow_history[-1]["status"] = "failed"
                    workflow_history[-1]["error"] = decision_task.error
                    raise RuntimeError(f"DecisionAgent 执行失败：{decision_task.error}")
            else:
                workflow_history[-1]["status"] = "skipped_already_provided"
            
            # 设置初始回复
            context.final_response = context.decision_output.response
            
            # Step 2: ReviewAgent 审视回复
            if self.config.enable_review:
                for review_round in range(self.config.max_review_rounds):
                    context.total_rounds += 1
                    
                    workflow_history.append({
                        "step": "review",
                        "round": review_round + 1,
                        "status": "started",
                    })
                    
                    review_msg = AgentMessage(
                        message_type=MessageType.REQUEST,
                        sender=self.config.agent_id,
                        receiver=self._review_agent.config.agent_id,
                        content={
                            "response": context.final_response,
                            "context": {
                                "persona_id": context.persona_id,
                                "user_message": context.user_message,
                            },
                        },
                        priority=Priority.NORMAL,
                    )
                    
                    review_task = await self._review_agent.run(review_msg)
                    
                    if review_task.status == TaskStatus.COMPLETED:
                        review_output = review_task.result.content
                        context.review_result = review_output
                        
                        workflow_history[-1]["status"] = "completed"
                        workflow_history[-1]["conflict_level"] = review_output.get(
                            "overall_conflict_level", "none"
                        )
                        
                        # 判断冲突级别
                        conflict_level_str = review_output.get(
                            "overall_conflict_level", "none"
                        )
                        conflict_level = ConflictLevel(conflict_level_str)
                        
                        # NONE 或 TOLERABLE → 直接输出
                        if conflict_level in [ConflictLevel.NONE, ConflictLevel.TOLERABLE]:
                            logger.info(
                                "[coordinator] 审视通过：conflict_level=%s, round=%d",
                                conflict_level.value,
                                review_round + 1,
                            )
                            workflow_history[-1]["passed"] = True
                            break
                        
                        # NEED_INTERVENTION 或 SEVERE → 进入 Arbitrate
                        logger.info(
                            "[coordinator] 审视未通过：conflict_level=%s, 进入仲裁",
                            conflict_level.value,
                        )
                        workflow_history[-1]["passed"] = False
                        
                        # Step 3: ArbitrateAgent 修正冲突
                        if self.config.enable_arbitration:
                            for arb_round in range(self.config.max_arbitration_rounds):
                                workflow_history.append({
                                    "step": "arbitration",
                                    "review_round": review_round + 1,
                                    "arbitration_round": arb_round + 1,
                                    "status": "started",
                                })
                                
                                arb_msg = AgentMessage(
                                    message_type=MessageType.REQUEST,
                                    sender=self.config.agent_id,
                                    receiver=self._arbitrate_agent.config.agent_id,
                                    content={
                                        "response": context.final_response,
                                        "review_result": review_output,
                                    },
                                    priority=Priority.NORMAL,
                                )
                                
                                arb_task = await self._arbitrate_agent.run(arb_msg)
                                
                                if arb_task.status == TaskStatus.COMPLETED:
                                    arb_output = arb_task.result.content
                                    
                                    workflow_history[-1]["status"] = "completed"
                                    workflow_history[-1]["success"] = arb_output.get(
                                        "success", False
                                    )
                                    workflow_history[-1]["strategy"] = arb_output.get(
                                        "strategy_used"
                                    )
                                    
                                    if arb_output.get("success", False):
                                        context.final_response = arb_output.get(
                                            "corrected_response",
                                            context.final_response,
                                        )
                                        context.arbitration_result = ArbitrationResult(
                                            corrected_response=context.final_response,
                                            original_response=review_output.get(
                                                "response", ""
                                            ),
                                            strategy_used=CorrectionStrategy(
                                                arb_output.get("strategy_used", "minimal")
                                            ),
                                            correction_count=arb_output.get(
                                                "correction_count", 0
                                            ),
                                            alignment_before=arb_output.get(
                                                "alignment_before", 0.0
                                            ),
                                            alignment_after=arb_output.get(
                                                "alignment_after", 0.0
                                            ),
                                            success=True,
                                        )
                                        
                                        # 修正后重新 Review
                                        logger.info(
                                            "[coordinator] 仲裁成功，重新审视：round=%d",
                                            review_round + 1,
                                        )
                                        break
                                    else:
                                        logger.warning(
                                            "[coordinator] 仲裁失败：arb_round=%d",
                                            arb_round + 1,
                                        )
                                else:
                                    workflow_history[-1]["status"] = "failed"
                                    workflow_history[-1]["error"] = arb_task.error
                                    logger.error(
                                        "[coordinator] ArbitrateAgent 执行失败：%s",
                                        arb_task.error,
                                    )
                    else:
                        workflow_history[-1]["status"] = "failed"
                        workflow_history[-1]["error"] = review_task.error
                        logger.error(
                            "[coordinator] ReviewAgent 执行失败：%s",
                            review_task.error,
                        )
                        break
            else:
                logger.info("[coordinator] Review 已禁用，跳过审视流程")
            
            # 记录工作流历史
            self._workflow_history = workflow_history
            context.metadata["workflow_history"] = workflow_history
            context.metadata["execution_time"] = time.time() - start_time
            
            # 构建协调结果
            result = CoordinatedResult(
                response=context.final_response,
                decision_confidence=context.decision_output.confidence
                if context.decision_output
                else 0.0,
                review_conflict_level=ConflictLevel(
                    context.review_result.get("overall_conflict_level", "none")
                )
                if context.review_result
                else None,
                correction_strategy=context.arbitration_result.strategy_used
                if context.arbitration_result
                else None,
                total_rounds=context.total_rounds,
                workflow_history=workflow_history,
            )
            
            logger.info(
                "[coordinator] 协调完成：response_length=%d, total_rounds=%d, confidence=%.2f",
                len(result.response),
                result.total_rounds,
                result.decision_confidence,
            )
            
            return result
            
        except Exception as e:
            error_msg = f"协调失败：{str(e)}"
            logger.exception("[coordinator] %s", error_msg)
            
            # 返回降级结果
            return CoordinatedResult(
                response=context.final_response or "处理失败，请稍后重试",
                decision_confidence=0.0,
                review_conflict_level=None,
                correction_strategy=None,
                total_rounds=context.total_rounds,
                workflow_history=workflow_history,
            )
    
    async def process(self, message: AgentMessage) -> AgentMessage:
        """处理消息（BaseAgent 接口实现）
        
        Args:
            message: 输入消息
        
        Returns:
            AgentMessage: 输出消息
        """
        try:
            # 解析输入
            content = message.content
            
            # 构建工作流上下文
            context = WorkflowContext(
                user_message=content.get("user_message", ""),
                persona_id=content.get("persona_id", ""),
            )
            
            # 执行协调
            result = await self.coordinate(context)
            
            # 构建响应消息
            response_message = AgentMessage(
                message_type=MessageType.RESPONSE,
                sender=self.config.agent_id,
                receiver=message.sender,
                content=result.to_dict(),
                priority=message.priority,
                parent_id=message.message_id,
            )
            
            logger.info(
                "[coordinator] process 完成：response_length=%d",
                len(result.response),
            )
            
            return response_message
            
        except Exception as e:
            logger.exception("[coordinator] process 失败：%s", e)
            raise
    
    def get_workflow_history(self) -> List[Dict[str, Any]]:
        """获取工作流历史
        
        Returns:
            List[Dict]: 工作流历史
        """
        return self._workflow_history.copy()
    
    def reset_workflow_history(self) -> None:
        """重置工作流历史"""
        self._workflow_history = []


def create_coordinator(
    enable_review: bool = True,
    enable_arbitration: bool = True,
    max_review_rounds: int = 2,
    max_arbitration_rounds: int = 3,
) -> DialogueCoordinator:
    """创建对话协调器
    
    Args:
        enable_review: 是否启用审视
        enable_arbitration: 是否启用仲裁
        max_review_rounds: 最大审视轮次
        max_arbitration_rounds: 最大仲裁轮次
    
    Returns:
        DialogueCoordinator: 对话协调器
    """
    config = CoordinatorConfig(
        enable_review=enable_review,
        enable_arbitration=enable_arbitration,
        max_review_rounds=max_review_rounds,
        max_arbitration_rounds=max_arbitration_rounds,
    )
    
    return DialogueCoordinator(config=config)
