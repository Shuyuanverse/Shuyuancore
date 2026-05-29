# Copyright 2026 ShuyuanCore contributors
# SPDX-License-Identifier: Apache-2.0
"""人格编译器 — 完整编译管线。

基于 2.1-2.4 修复后的组件，实现完整编译管线：
- compile_generic：通用模式编译（从对话记录提取风格）
- compile_persona：人格模式编译（从 CORE.md+ 对话样本生成完整人格）
- update_anchor：基于用户反馈更新锚点
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.persona.style.text_style import TextStyleAnalyzer
from src.persona.style.style_encoder import StyleEncoder, StyleProfile
from src.persona.style.style_vector import StyleVectorGenerator
from src.persona.style.style_anchor import StyleAnchorEncoder
from src.persona.anchor.decision_anchor import DecisionEncoder, DecisionEncoderLight
from src.persona.anchor.anchor_manager import AnchorVersionManager
from src.persona.anchor.semantic_translator import SemanticTranslator
from src.persona.anchor.value_dimensions import ValueDimensionsRegistry
from src.persona.hard_fact_guard import HardFactGuard
from src.persona.protection import StyleProtectionPipeline, ProtectionConfig
from src.persona.profile import PersonaProfile, StyleDimensions

logger = logging.getLogger(__name__)


@dataclass
class CompilerConfig:
    """编译器配置参数"""
    # 风格编码配置
    style_vector_dim: int = 60
    style_anchor_dim: int = 128
    decision_anchor_dim: int = 256
    
    # 阈值配置（锁定参数）
    drift_threshold_protection: float = 0.25  # 保护层漂移阈值
    drift_threshold_review: float = 0.15  # 审查 Agent 漂移阈值
    
    # 编译配置
    min_language_samples: int = 500  # 最小语言样本数（字）
    max_language_samples: int = 1000000  # 最大语言样本数（字）
    default_core_md: str = ""  # 默认 CORE.md 内容
    
    # Feature Flags
    enable_style_protection: bool = True
    enable_hard_fact_extraction: bool = True
    enable_value_translation: bool = True
    enable_anchor_versioning: bool = True


@dataclass
class CompilationMetadata:
    """编译元数据"""
    compilation_steps: List[str] = field(default_factory=list)
    execution_time_ms: float = 0.0
    style_analysis_result: Optional[Dict[str, Any]] = None
    anchor_version_id: Optional[str] = None
    hard_fact_count: int = 0
    value_profile_generated: bool = False
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


class PersonaCompiler:
    """人格编译器 — 完整管线编排
    
    依赖注入组件：
    - TextStyleAnalyzer：文本风格分析
    - StyleEncoder：7 维风格画像编码
    - StyleVectorGenerator：60 维风格向量生成
    - StyleAnchorEncoder：128 维风格锚点编码
    - DecisionEncoder/DecisionEncoderLight：256 维决策锚点编码
    - AnchorVersionManager：锚点版本管理
    - HardFactGuard：硬事实提取与守卫
    - StyleProtectionPipeline：风格保护流水线
    - SemanticTranslator：语义翻译器（价值观映射）
    """
    
    def __init__(
        self,
        text_analyzer: Optional[TextStyleAnalyzer] = None,
        style_encoder: Optional[StyleEncoder] = None,
        style_vector_gen: Optional[StyleVectorGenerator] = None,
        style_anchor_encoder: Optional[StyleAnchorEncoder] = None,
        decision_encoder: Optional[DecisionEncoder | DecisionEncoderLight] = None,
        anchor_version_manager: Optional[AnchorVersionManager] = None,
        hard_fact_guard: Optional[HardFactGuard] = None,
        style_protection: Optional[StyleProtectionPipeline] = None,
        semantic_translator: Optional[SemanticTranslator] = None,
        config: Optional[CompilerConfig] = None,
    ):
        """初始化编译器，注入所有依赖组件
        
        Args:
            text_analyzer: 文本风格分析器
            style_encoder: 风格编码器（7 维画像）
            style_vector_gen: 风格向量生成器（60 维）
            style_anchor_encoder: 风格锚点编码器（128 维）
            decision_encoder: 决策编码器（256 维），支持 PyTorch 或 Light 降级
            anchor_version_manager: 锚点版本管理器
            hard_fact_guard: 硬事实守卫
            style_protection: 风格保护流水线
            semantic_translator: 语义翻译器
            config: 编译器配置
        """
        self.config = config or CompilerConfig()
        
        # 注入依赖组件（使用默认实例或传入实例）
        self._text_analyzer = text_analyzer or TextStyleAnalyzer()
        self._style_encoder = style_encoder or StyleEncoder()
        self._style_vector_gen = style_vector_gen or StyleVectorGenerator()
        self._style_anchor_encoder = style_anchor_encoder or StyleAnchorEncoder()
        
        # 决策编码器：优先使用 PyTorch 版本，降级到 Light 版本
        if decision_encoder is None:
            try:
                self._decision_encoder = DecisionEncoder()
                logger.info("[compiler] 使用 PyTorch DecisionEncoder")
            except Exception:
                self._decision_encoder = DecisionEncoderLight()
                logger.info("[compiler] 使用 NumPy DecisionEncoderLight（降级模式）")
        else:
            self._decision_encoder = decision_encoder
        
        self._anchor_version_manager = anchor_version_manager or AnchorVersionManager()
        self._hard_fact_guard = hard_fact_guard or HardFactGuard()
        self._style_protection = style_protection or StyleProtectionPipeline(
            ProtectionConfig(
                drift_threshold=self.config.drift_threshold_protection,
                review_drift_threshold=self.config.drift_threshold_review,
            )
        )
        self._semantic_translator = semantic_translator or SemanticTranslator()
        
        logger.info("[compiler] 初始化完成，配置：%s", self.config)
    
    async def compile_generic(
        self,
        persona_id: str,
        conversation_samples: list[str],
        core_md: str = "",
    ) -> PersonaProfile:
        """通用模式编译 — 从对话记录提取风格
        
        完整管线（8 步流程）：
        1. TextStyleAnalyzer.extract() → StyleExtractionResult
        2. StyleEncoder.encode() → StyleProfile (7 维)
        3. StyleVectorGenerator.generate() → StyleVector (60 维)
        4. StyleAnchorEncoder.encode_deterministic() → style_anchor (128 维)
        5. DecisionEncoderLight.encode() → decision_anchor (256 维)
        6. AnchorVersionManager.create_new_version() → AnchorVersion
        7. HardFactGuard.extract_from_core_md() → hard_fact_belief_ids
        8. 组装 PersonaProfile
        
        Args:
            persona_id: 人格 ID
            conversation_samples: 对话样本列表
            core_md: CORE.md 内容（可选）
        
        Returns:
            PersonaProfile: 完整人格画像
        
        Raises:
            ValueError: 当样本量不足或超过限制时
        """
        import time
        start_time = time.time()
        metadata = CompilationMetadata()
        
        try:
            # Step 1: 文本风格分析
            metadata.compilation_steps.append("step_1_text_analysis")
            combined_text = "\n".join(conversation_samples)
            
            # 验证样本量
            char_count = len(combined_text)
            if char_count < self.config.min_language_samples:
                raise ValueError(
                    f"对话样本量不足：{char_count} 字 < {self.config.min_language_samples} 字"
                )
            if char_count > self.config.max_language_samples:
                logger.warning(
                    "对话样本量过大：%d 字 > %d 字，将截断至前 %d 字",
                    char_count,
                    self.config.max_language_samples,
                    self.config.max_language_samples,
                )
                combined_text = combined_text[: self.config.max_language_samples]
            
            style_extraction = await self._text_analyzer.extract(combined_text)
            metadata.style_analysis_result = {
                "sentence_count": len(style_extraction.sentence_features),
                "avg_sentence_length": style_extraction.length_stats.get("mean", 0),
                "ttr": style_extraction.lexical_diversity.get("ttr", 0),
                "hapax_ratio": style_extraction.lexical_diversity.get("hapax_ratio", 0),
            }
            logger.info(
                "[compiler] Step 1 完成：文本分析完成，句子数=%d, 平均长度=%.2f",
                len(style_extraction.sentence_features),
                style_extraction.length_stats.get("mean", 0),
            )
            
            # Step 2: 7 维风格画像编码
            metadata.compilation_steps.append("step_2_style_profile")
            style_profile = self._style_encoder.encode(combined_text)
            logger.info(
                "[compiler] Step 2 完成：7 维风格画像，overall=%.4f, type=%s",
                style_profile.overall_score,
                style_profile.style_type,
            )
            
            # Step 3: 60 维风格向量生成
            metadata.compilation_steps.append("step_3_style_vector")
            style_vector = await self._style_vector_gen.generate(
                style_profile=style_profile,
                extraction_result=style_extraction,
            )
            logger.info(
                "[compiler] Step 3 完成：60 维风格向量，consistency=%.4f",
                style_vector.consistency_score,
            )
            
            # Step 4: 128 维风格锚点编码（确定性降级）
            metadata.compilation_steps.append("step_4_style_anchor")
            style_anchor = await self._style_anchor_encoder.encode_deterministic(
                style_vector=style_vector.vector,
                persona_id=persona_id,
            )
            logger.info(
                "[compiler] Step 4 完成：128 维风格锚点，checksum=%s",
                style_anchor.checksum[:8] if style_anchor.checksum else "N/A",
            )
            
            # Step 5: 256 维决策锚点编码
            metadata.compilation_steps.append("step_5_decision_anchor")
            decision_anchor = await self._decision_encoder.encode(
                user_goal="通用助手",
                priorities=["helpful", "honest", "harmless"],
                constraints=["不涉及敏感话题", "不提供专业建议"],
                persona_id=persona_id,
            )
            logger.info(
                "[compiler] Step 5 完成：256 维决策锚点，mode=%s",
                "pytorch" if hasattr(self._decision_encoder, "forward") else "numpy",
            )
            
            # Step 6: 创建锚点版本
            metadata.compilation_steps.append("step_6_anchor_version")
            anchor_version = None
            if self.config.enable_anchor_versioning:
                anchor_version = await self._anchor_version_manager.create_new_version(
                    persona_id=persona_id,
                    style_anchor=style_anchor.vector,
                    decision_anchor=decision_anchor.vector,
                    source_text=combined_text[:500],  # 前 500 字作为源文本
                )
                metadata.anchor_version_id = anchor_version.version_id
                logger.info(
                    "[compiler] Step 6 完成：锚点版本 v%s 创建成功",
                    anchor_version.version_number,
                )
            
            # Step 7: 硬事实提取
            metadata.compilation_steps.append("step_7_hard_fact")
            hard_fact_ids: list[str] = []
            if self.config.enable_hard_fact_extraction and core_md.strip():
                hard_fact_ids = await self._hard_fact_guard.extract_from_core_md(
                    core_md=core_md,
                    persona_id=persona_id,
                )
                metadata.hard_fact_count = len(hard_fact_ids)
                logger.info(
                    "[compiler] Step 7 完成：提取 %d 条硬事实",
                    len(hard_fact_ids),
                )
            
            # Step 8: 组装 PersonaProfile
            metadata.compilation_steps.append("step_8_assemble")
            style_dimensions = StyleDimensions.from_style_profile(style_profile)
            
            profile = PersonaProfile(
                persona_id=persona_id,
                mode="generic",
                style_dimensions=style_dimensions,
                style_anchor_vector=style_anchor.vector,
                decision_anchor_vector=decision_anchor.vector,
                style_vector=style_vector.vector,
                hard_fact_belief_ids=hard_fact_ids,
                language_samples=conversation_samples,
                anchor_version=metadata.anchor_version_id,
                version=1,
                metadata={
                    "compilation_time_ms": (time.time() - start_time) * 1000,
                    "style_type": style_profile.style_type,
                    "compilation_steps": metadata.compilation_steps,
                },
            )
            
            metadata.execution_time_ms = (time.time() - start_time) * 1000
            logger.info(
                "[compiler] compile_generic 完成：persona_id=%s, 耗时=%.2fms",
                persona_id,
                metadata.execution_time_ms,
            )
            
            return profile
            
        except Exception as e:
            metadata.errors.append(str(e))
            logger.exception("[compiler] compile_generic 失败：%s", e)
            raise
    
    async def compile_persona(
        self,
        persona_id: str,
        input_text: str,
        core_md: str = "",
        language_samples: list[str] | None = None,
    ) -> PersonaProfile:
        """人格模式编译 — 从 CORE.md+ 对话样本生成完整人格
        
        完整管线（9 步流程）：
        1. TextStyleAnalyzer.extract(input_text) → StyleExtractionResult
        2. StyleEncoder.encode() → StyleProfile (7 维)
        3. StyleVectorGenerator.generate() → StyleVector (60 维)
        4. StyleAnchorEncoder.encode_deterministic() → style_anchor (128 维)
        5. DecisionEncoder/DecisionEncoderLight.encode() → decision_anchor (256 维)
           输入：{user_goal, priorities, constraints} 从 core_md 提取
        6. AnchorVersionManager.create_new_version() → AnchorVersion
        7. HardFactGuard.extract_from_core_md() → hard_fact_belief_ids
        8. SemanticTranslator.translate() → ValueProfile (25 维价值观)
        9. 组装 PersonaProfile
        
        Args:
            persona_id: 人格 ID
            input_text: 输入文本（对话样本或语言样本）
            core_md: CORE.md 人格定义
            language_samples: 语言样本列表（可选）
        
        Returns:
            PersonaProfile: 完整人格画像
        
        Raises:
            ValueError: 当样本量不足或 CORE.md 缺失关键信息时
        """
        import time
        start_time = time.time()
        metadata = CompilationMetadata()
        
        try:
            # Step 1: 文本风格分析
            metadata.compilation_steps.append("step_1_text_analysis")
            
            # 验证样本量
            char_count = len(input_text)
            if char_count < self.config.min_language_samples:
                metadata.warnings.append(
                    f"语言样本量偏低：{char_count} 字 < {self.config.min_language_samples} 字（推荐最小值）"
                )
                logger.warning(
                    "[compiler] 语言样本量偏低：%d 字，可能影响风格分析质量",
                    char_count,
                )
            if char_count > self.config.max_language_samples:
                logger.warning(
                    "语言样本量过大：%d 字 > %d 字，将截断",
                    char_count,
                    self.config.max_language_samples,
                )
                input_text = input_text[: self.config.max_language_samples]
            
            style_extraction = await self._text_analyzer.extract(input_text)
            metadata.style_analysis_result = {
                "sentence_count": len(style_extraction.sentence_features),
                "avg_sentence_length": style_extraction.length_stats.get("mean", 0),
                "ttr": style_extraction.lexical_diversity.get("ttr", 0),
                "hapax_ratio": style_extraction.lexical_diversity.get("hapax_ratio", 0),
            }
            logger.info(
                "[compiler] Step 1 完成：文本分析完成，句子数=%d, 平均长度=%.2f",
                len(style_extraction.sentence_features),
                style_extraction.length_stats.get("mean", 0),
            )
            
            # Step 2: 7 维风格画像编码
            metadata.compilation_steps.append("step_2_style_profile")
            style_profile = self._style_encoder.encode(input_text)
            logger.info(
                "[compiler] Step 2 完成：7 维风格画像，overall=%.4f, type=%s",
                style_profile.overall_score,
                style_profile.style_type,
            )
            
            # Step 3: 60 维风格向量生成
            metadata.compilation_steps.append("step_3_style_vector")
            style_vector = await self._style_vector_gen.generate(
                style_profile=style_profile,
                extraction_result=style_extraction,
            )
            logger.info(
                "[compiler] Step 3 完成：60 维风格向量，consistency=%.4f",
                style_vector.consistency_score,
            )
            
            # Step 4: 128 维风格锚点编码
            metadata.compilation_steps.append("step_4_style_anchor")
            style_anchor = await self._style_anchor_encoder.encode_deterministic(
                style_vector=style_vector.vector,
                persona_id=persona_id,
            )
            logger.info(
                "[compiler] Step 4 完成：128 维风格锚点，checksum=%s",
                style_anchor.checksum[:8] if style_anchor.checksum else "N/A",
            )
            
            # Step 5: 256 维决策锚点编码（从 core_md 提取）
            metadata.compilation_steps.append("step_5_decision_anchor")
            user_goal, priorities, constraints = self._extract_from_core_md(core_md)
            
            decision_anchor = await self._decision_encoder.encode(
                user_goal=user_goal or "人格化助手",
                priorities=priorities or ["authentic", "consistent", "empathetic"],
                constraints=constraints or ["保持人格一致性", "不违背硬事实"],
                persona_id=persona_id,
            )
            logger.info(
                "[compiler] Step 5 完成：256 维决策锚点，goal=%s",
                user_goal or "default",
            )
            
            # Step 6: 创建锚点版本
            metadata.compilation_steps.append("step_6_anchor_version")
            anchor_version = None
            if self.config.enable_anchor_versioning:
                anchor_version = await self._anchor_version_manager.create_new_version(
                    persona_id=persona_id,
                    style_anchor=style_anchor.vector,
                    decision_anchor=decision_anchor.vector,
                    source_text=input_text[:500],
                )
                metadata.anchor_version_id = anchor_version.version_id
                logger.info(
                    "[compiler] Step 6 完成：锚点版本 v%s 创建成功",
                    anchor_version.version_number,
                )
            
            # Step 7: 硬事实提取
            metadata.compilation_steps.append("step_7_hard_fact")
            hard_fact_ids: list[str] = []
            if self.config.enable_hard_fact_extraction and core_md.strip():
                hard_fact_ids = await self._hard_fact_guard.extract_from_core_md(
                    core_md=core_md,
                    persona_id=persona_id,
                )
                metadata.hard_fact_count = len(hard_fact_ids)
                logger.info(
                    "[compiler] Step 7 完成：提取 %d 条硬事实",
                    len(hard_fact_ids),
                )
            
            # Step 8: 25 维价值观翻译
            metadata.compilation_steps.append("step_8_value_translation")
            values_profile = None
            if self.config.enable_value_translation:
                values_profile = await self._semantic_translator.translate(
                    core_md=core_md,
                    style_profile=style_profile,
                    persona_id=persona_id,
                )
                metadata.value_profile_generated = True
                logger.info(
                    "[compiler] Step 8 完成：25 维价值观画像生成成功",
                )
            
            # Step 9: 组装 PersonaProfile
            metadata.compilation_steps.append("step_9_assemble")
            style_dimensions = StyleDimensions.from_style_profile(style_profile)
            
            profile = PersonaProfile(
                persona_id=persona_id,
                mode="persona",
                style_dimensions=style_dimensions,
                style_anchor_vector=style_anchor.vector,
                decision_anchor_vector=decision_anchor.vector,
                style_vector=style_vector.vector,
                hard_fact_belief_ids=hard_fact_ids,
                language_samples=language_samples or [input_text],
                anchor_version=metadata.anchor_version_id,
                values_profile=values_profile,
                version=1,
                metadata={
                    "compilation_time_ms": (time.time() - start_time) * 1000,
                    "style_type": style_profile.style_type,
                    "compilation_steps": metadata.compilation_steps,
                    "core_md_parsed": bool(core_md.strip()),
                    "user_goal": user_goal,
                },
            )
            
            metadata.execution_time_ms = (time.time() - start_time) * 1000
            logger.info(
                "[compiler] compile_persona 完成：persona_id=%s, 耗时=%.2fms",
                persona_id,
                metadata.execution_time_ms,
            )
            
            return profile
            
        except Exception as e:
            metadata.errors.append(str(e))
            logger.exception("[compiler] compile_persona 失败：%s", e)
            raise
    
    async def update_anchor(
        self,
        persona_id: str,
        recent_feedback: list[Dict[str, Any]],
    ) -> Optional[AnchorVersion]:
        """基于用户反馈更新锚点
        
        管线：
        1. AnchorVersionManager.check_and_update(recent_feedback)
        2. 如果需要更新，平滑过渡到新版本
        
        Args:
            persona_id: 人格 ID
            recent_feedback: 近期反馈列表，格式：
                [
                    {"rating": 1-5, "comment": "用户反馈内容"},
                    ...
                ]
        
        Returns:
            Optional[AnchorVersion]: 如果触发更新则返回新版本，否则返回 None
        """
        import time
        start_time = time.time()
        
        try:
            logger.info(
                "[compiler] update_anchor 开始：persona_id=%s, feedback_count=%d",
                persona_id,
                len(recent_feedback),
            )
            
            # Step 1: 检查并更新锚点
            anchor_version = await self._anchor_version_manager.check_and_update(
                persona_id=persona_id,
                recent_feedback=recent_feedback,
            )
            
            if anchor_version:
                logger.info(
                    "[compiler] update_anchor 完成：创建新版本 v%s, 耗时=%.2fms",
                    anchor_version.version_number,
                    (time.time() - start_time) * 1000,
                )
                return anchor_version
            else:
                logger.info(
                    "[compiler] update_anchor 完成：未触发更新，耗时=%.2fms",
                    (time.time() - start_time) * 1000,
                )
                return None
                
        except Exception as e:
            logger.exception("[compiler] update_anchor 失败：%s", e)
            raise
    
    def _extract_from_core_md(
        self,
        core_md: str,
    ) -> tuple[Optional[str], list[str], list[str]]:
        """从 CORE.md 提取用户目标、优先级和约束
        
        简化实现：基于关键词匹配提取
        
        Args:
            core_md: CORE.md 内容
        
        Returns:
            (user_goal, priorities, constraints): 三元组
        """
        if not core_md.strip():
            return None, [], []
        
        user_goal = None
        priorities = []
        constraints = []
        
        lines = core_md.strip().split("\n")
        for line in lines:
            line = line.strip().lower()
            
            # 提取用户目标
            if any(kw in line for kw in ["目标", "goal", "purpose"]):
                if ":" in line:
                    user_goal = line.split(":", 1)[1].strip()
                elif "是" in line:
                    user_goal = line.split("是", 1)[1].strip()
            
            # 提取优先级
            if any(kw in line for kw in ["优先", "priority", "重要"]):
                if "真实" in line or "authentic" in line:
                    priorities.append("authentic")
                if "一致" in line or "consistent" in line:
                    priorities.append("consistent")
                if "共情" in line or "empathetic" in line:
                    priorities.append("empathetic")
                if "高效" in line or "efficient" in line:
                    priorities.append("efficient")
            
            # 提取约束
            if any(kw in line for kw in ["约束", "constraint", "禁止", "不要"]):
                constraints.append(line)
        
        return user_goal, priorities, constraints
    
    def get_compilation_status(self, profile: PersonaProfile) -> Dict[str, Any]:
        """获取编译状态报告
        
        Args:
            profile: 人格画像
        
        Returns:
            Dict: 状态报告，包含：
                - is_valid: 是否有效
                - missing_components: 缺失组件列表
                - warnings: 警告列表
                - recommendations: 建议列表
        """
        status = {
            "is_valid": True,
            "missing_components": [],
            "warnings": [],
            "recommendations": [],
        }
        
        # 检查必需字段
        if not profile.style_anchor_vector:
            status["missing_components"].append("style_anchor_vector")
            status["is_valid"] = False
        
        if not profile.decision_anchor_vector:
            status["missing_components"].append("decision_anchor_vector")
            status["is_valid"] = False
        
        # 检查可选字段
        if not profile.values_profile:
            status["warnings"].append("values_profile 未生成（可能未启用价值观翻译）")
        
        if not profile.anchor_version:
            status["warnings"].append("anchor_version 未设置（可能未启用版本管理）")
        
        # 检查样本量
        if profile.language_samples:
            total_chars = sum(len(s) for s in profile.language_samples)
            if total_chars < self.config.min_language_samples:
                status["recommendations"].append(
                    f"建议增加语言样本至 {self.config.min_language_samples} 字以上（当前：{total_chars} 字）"
                )
        
        return status


def build_persona_prompt(profile: PersonaProfile) -> str:
    """构建人格提示词
    
    Args:
        profile: 人格画像
    
    Returns:
        str: 格式化后的提示词
    """
    from src.persona.identity_prompt import IdentityPromptBuilder
    
    builder = IdentityPromptBuilder(profile)
    return builder.build()
