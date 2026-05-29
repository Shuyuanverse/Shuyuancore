# Copyright 2026 ShuyuanCore contributors
# SPDX-License-Identifier: Apache-2.0
"""内心反应管线编排。

Feature Flag 控制：
- enable_perception: bool = True
- enable_reaction: bool = True
- enable_synergy_bus: bool = True

错误兜底：任何步骤失败，返回空字符串，不阻塞主流程
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .perception import PerceptionEngine, PerceptionResult
from .persona_synergy_bus import PersonaSynergyBus, SynergyBusResult
from .reaction import InnerReaction, InnerReactionBuilder

logger = logging.getLogger(__name__)


@dataclass
class InnerReactionConfig:
    """内心反应配置"""

    enable_perception: bool = True  # 启用感知
    enable_reaction: bool = True  # 启用反应
    enable_synergy_bus: bool = True  # 启用感知总线
    enable_error_fallback: bool = True  # 启用错误兜底

    # 感知参数
    perception_history_window: int = 5  # 感知历史窗口大小
    enable_wolf_detection: bool = True  # 启用狼来了检测

    # 反应参数
    enable_anti_inertia: bool = True  # 启用对抗 AI 惯性

    # 协同参数
    min_synergy_score: float = 0.3  # 最小协同度阈值


@dataclass
class InnerReactionResult:
    """内心反应结果"""

    perception_result: Optional[PerceptionResult] = None  # 感知结果
    inner_reaction: Optional[InnerReaction] = None  # 内心反应
    synergy_result: Optional[SynergyBusResult] = None  # 协同结果
    final_prompt: str = ""  # 最终提示词
    errors: List[str] = field(default_factory=list)  # 错误列表
    warnings: List[str] = field(default_factory=list)  # 警告列表
    metadata: Dict[str, Any] = field(default_factory=dict)  # 元数据

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "perception_result": self.perception_result.to_dict()
            if self.perception_result
            else None,
            "inner_reaction": self.inner_reaction.to_dict() if self.inner_reaction else None,
            "synergy_result": self.synergy_result.to_dict() if self.synergy_result else None,
            "final_prompt": self.final_prompt,
            "errors": self.errors,
            "warnings": self.warnings,
            "metadata": self.metadata,
        }


class InnerReactionPipeline:
    """内心反应管线编排

    Feature Flag 控制，错误兜底

    orchestrate(response, style_dimensions, persona_id) → InnerReactionResult
    1. PerceptionEngine.perceive() → PerceptionResult
    2. InnerReactionBuilder.build_inner_reaction_prompt() → reaction_prompt
    3. PersonaSynergyBus.synergy_process() → SynergyBusResult
    4. 组装 InnerReactionResult
    """

    def __init__(self, config: Optional[InnerReactionConfig] = None):
        """初始化内心反应管线

        Args:
            config: 配置参数
        """
        self.config = config or InnerReactionConfig()

        # 初始化组件
        self._perception_engine = PerceptionEngine()
        self._reaction_builder = InnerReactionBuilder()
        self._synergy_bus = PersonaSynergyBus()

        logger.info("[pipeline] 内心反应管线初始化完成，配置：%s", self.config)

    def orchestrate(
        self,
        user_message: str,
        history: List[str],
        persona_id: str,
    ) -> InnerReactionResult:
        """编排流程

        Args:
            user_message: 用户消息
            history: 历史消息列表
            persona_id: 人格 ID

        Returns:
            InnerReactionResult: 内心反应结果

        流程：
        1. PerceptionEngine.perceive() → PerceptionResult
        2. InnerReactionBuilder.build_inner_reaction_prompt() → reaction_prompt
        3. PersonaSynergyBus.synergy_process() → SynergyBusResult
        4. 组装 InnerReactionResult
        """
        result = InnerReactionResult()

        try:
            # Step 1: 感知
            if self.config.enable_perception:
                try:
                    perception_result = self._perception_engine.perceive(
                        user_message=user_message,
                        history=history,
                        persona_id=persona_id,
                    )
                    result.perception_result = perception_result
                    result.metadata["perception_enabled"] = True
                except Exception as e:
                    error_msg = f"感知失败：{str(e)}"
                    logger.exception("[pipeline] %s", error_msg)

                    if self.config.enable_error_fallback:
                        result.errors.append(error_msg)
                        result.warnings.append("使用默认感知结果")
                        result.perception_result = PerceptionResult()
                    else:
                        result.errors.append(error_msg)
                        return result
            else:
                result.warnings.append("感知已禁用")
                result.perception_result = PerceptionResult()

            # Step 2: 反应构建
            if self.config.enable_reaction and result.perception_result:
                try:
                    inner_reaction = self._reaction_builder.build_inner_reaction_prompt(
                        perception_result=result.perception_result,
                    )
                    result.inner_reaction = inner_reaction
                    result.metadata["reaction_enabled"] = True
                except Exception as e:
                    error_msg = f"反应构建失败：{str(e)}"
                    logger.exception("[pipeline] %s", error_msg)

                    if self.config.enable_error_fallback:
                        result.errors.append(error_msg)
                        result.warnings.append("使用默认反应")
                        result.inner_reaction = InnerReaction(
                            inner_state_prompt="[内心状态]\n感知到：默认状态",
                            atmosphere_description="默认",
                            emotion_description="默认",
                            identity_description="默认",
                            patience_description="默认",
                            anti_inertia_instructions=[],
                        )
                    else:
                        result.errors.append(error_msg)
                        return result
            else:
                result.warnings.append("反应已禁用")

            # Step 3: 协同处理
            if self.config.enable_synergy_bus and result.perception_result:
                try:
                    synergy_result = self._synergy_bus.synergy_process(
                        perception_result=result.perception_result,
                    )
                    result.synergy_result = synergy_result
                    result.metadata["synergy_enabled"] = True

                    # 检查协同度
                    if synergy_result.synergy_score < self.config.min_synergy_score:
                        result.warnings.append(
                            f"协同度偏低：{synergy_result.synergy_score:.2f} < {self.config.min_synergy_score}"
                        )
                except Exception as e:
                    error_msg = f"协同处理失败：{str(e)}"
                    logger.exception("[pipeline] %s", error_msg)

                    if self.config.enable_error_fallback:
                        result.errors.append(error_msg)
                        result.warnings.append("使用默认协同结果")
                        result.synergy_result = SynergyBusResult(
                            signals=[],
                            intents=[],
                            param_suggestions={},
                            synergy_score=0.0,
                        )
                    else:
                        result.errors.append(error_msg)
                        return result
            else:
                result.warnings.append("协同处理已禁用")

            # Step 4: 组装最终提示词
            result.final_prompt = self._assemble_final_prompt(result)

            result.metadata["pipeline_success"] = True
            result.metadata["step_count"] = sum(
                [
                    self.config.enable_perception,
                    self.config.enable_reaction,
                    self.config.enable_synergy_bus,
                ]
            )

            logger.info(
                "[pipeline] 编排完成：persona=%s, errors=%d, warnings=%d, synergy=%.2f",
                persona_id,
                len(result.errors),
                len(result.warnings),
                result.synergy_result.synergy_score if result.synergy_result else 0.0,
            )

        except Exception as e:
            error_msg = f"管线编排失败：{str(e)}"
            logger.exception("[pipeline] %s", error_msg)
            result.errors.append(error_msg)
            result.metadata["pipeline_success"] = False

        return result

    def _assemble_final_prompt(self, result: InnerReactionResult) -> str:
        """组装最终提示词

        Args:
            result: 内心反应结果

        Returns:
            str: 最终提示词
        """
        lines = []

        # 内心状态
        if result.inner_reaction:
            lines.append(result.inner_reaction.inner_state_prompt)
            lines.append("")

        # 对抗 AI 惯性指令
        if result.inner_reaction and result.inner_reaction.anti_inertia_instructions:
            lines.append("[对抗 AI 惯性]")
            for instruction in result.inner_reaction.anti_inertia_instructions:
                lines.append(f"- {instruction}")
            lines.append("")

        # 参数建议
        if result.synergy_result and result.synergy_result.param_suggestions:
            lines.append("[参数建议]")
            for key, value in result.synergy_result.param_suggestions.items():
                lines.append(f"- {key}: {value}")
            lines.append("")

        # 协同度
        if result.synergy_result:
            lines.append(f"[协同度：{result.synergy_result.synergy_score:.2f}]")

        return "\n".join(lines)

    def quick_perceive(
        self,
        user_message: str,
        persona_id: str,
    ) -> PerceptionResult:
        """快速感知（无历史）

        Args:
            user_message: 用户消息
            persona_id: 人格 ID

        Returns:
            PerceptionResult: 感知结果
        """
        return self._perception_engine.perceive(
            user_message=user_message,
            history=[],
            persona_id=persona_id,
        )

    def get_perception_engine(self) -> PerceptionEngine:
        """获取感知引擎

        Returns:
            PerceptionEngine: 感知引擎实例
        """
        return self._perception_engine

    def get_reaction_builder(self) -> InnerReactionBuilder:
        """获取反应构建器

        Returns:
            InnerReactionBuilder: 反应构建器实例
        """
        return self._reaction_builder

    def get_synergy_bus(self) -> PersonaSynergyBus:
        """获取感知总线

        Returns:
            PersonaSynergyBus: 感知总线实例
        """
        return self._synergy_bus
