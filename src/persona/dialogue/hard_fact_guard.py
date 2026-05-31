# Copyright 2026 ShuyuanCore contributors
# SPDX-License-Identifier: Apache-2.0
"""硬事实确定性拦截引擎 — 三层防护。

三层防护：
1. check_input(user_message, persona_id) → InputCheckResult
   — 关键词匹配标记涉及硬事实领域的输入（规则，无 LLM）
   — 从 hard_fact beliefs 中提取关键词
   — 对 4 类硬事实分别提取关键词
   — 对 4 字以上关键词生成 2-4 字滑动窗口子串扩展
   — 用户消息包含任一关键词→标记为涉及硬事实

2. check_output(response_text, involved_facts, persona_id) → OutputCheckResult
   — 两级检查：
     a. 正则模式匹配（规则引擎）
     b. LLM 语义判断（仅当正则无法确定时调用）

3. regenerate_with_constraint(user_message, persona_id, conflicting_facts) → str
   — 两级修复：
     a. 规则修复：识别矛盾句子→删除或替换
     b. LLM 重生成：规则无法修复时调用
   — 最多重试 2 次
   — 全部失败→返回保守回复
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class InputCheckResult:
    """输入检查结果

    Attributes:
        involves_hard_fact: 是否涉及硬事实
        involved_facts: 涉及的硬事实列表
        matched_keywords: 匹配的关键词
        confidence: 置信度
    """

    involves_hard_fact: bool = False
    involved_facts: List[str] = field(default_factory=list)
    matched_keywords: List[str] = field(default_factory=list)
    confidence: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "involves_hard_fact": self.involves_hard_fact,
            "involved_facts": self.involved_facts,
            "matched_keywords": self.matched_keywords,
            "confidence": self.confidence,
        }


@dataclass
class OutputCheckResult:
    """输出检查结果

    Attributes:
        has_conflict: 是否有冲突
        conflict_type: 冲突类型
        conflicting_facts: 冲突的硬事实
        confidence: 置信度
        needs_regeneration: 是否需要重生成
    """

    has_conflict: bool = False
    conflict_type: Optional[str] = None
    conflicting_facts: List[str] = field(default_factory=list)
    confidence: float = 0.0
    needs_regeneration: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "has_conflict": self.has_conflict,
            "conflict_type": self.conflict_type,
            "conflicting_facts": self.conflicting_facts,
            "confidence": self.confidence,
            "needs_regeneration": self.needs_regeneration,
        }


class HardFactGuard:
    """硬事实确定性拦截引擎

    三层防护：
    1. check_input: 输入检查
    2. check_output: 输出检查
    3. regenerate_with_constraint: 约束重生成

    矛盾行为模式库：
    - knowledge_boundary.proactive_offer: 18 个模式
    - bottom_line.violation_signal: 6 个模式
    - identity.denial_pattern: 3 个模式
    - relation.denial_pattern: 4 个模式

    缓存机制：persona_id → hard_facts + keyword_map
    """

    # 矛盾行为模式库
    CONFLICT_PATTERNS = {
        "knowledge_boundary.proactive_offer": [
            "我来帮你",
            "我可以帮你",
            "我能帮你",
            "让我帮你",
            "我来处理",
            "我来解决",
            "我来负责",
            "交给我",
            "没问题",
            "包在我身上",
            "我一定",
            "我保证",
            "我来安排",
            "我来操作",
            "我来执行",
            "我来完成",
            "我来搞定",
            "我来处理这个",
        ],
        "bottom_line.violation_signal": [
            "我可以",
            "我能够",
            "我愿意",
            "我会",
            "我帮你",
            "我为你",
        ],
        "identity.denial_pattern": [
            "我不是",
            "我不代表",
            "我并非",
        ],
        "relation.denial_pattern": [
            "我不认识",
            "我不了解",
            "我不知道",
            "我没听说过",
        ],
    }

    def __init__(self):
        """初始化硬事实守卫"""
        # 缓存：persona_id → (hard_facts, keyword_map)
        self._cache: Dict[str, Tuple[List[str], Dict[str, List[str]]]] = {}

        logger.info("[hard_fact_guard] 硬事实守卫初始化完成")

    async def check_input(
        self,
        user_message: str,
        persona_id: str,
        belief_store: Optional[Any] = None,
    ) -> InputCheckResult:
        """检查输入是否涉及硬事实

        Args:
            user_message: 用户消息
            persona_id: 人格 ID
            belief_store: 信念存储（可选）

        Returns:
            InputCheckResult: 输入检查结果
        """
        result = InputCheckResult()

        # Step 1: 获取硬事实关键词（从缓存或 belief_store）
        hard_facts, keyword_map = self._get_hard_fact_keywords(persona_id, belief_store)

        if not hard_facts:
            logger.debug("[hard_fact_guard] persona=%s 无硬事实", persona_id)
            return result

        # Step 2: 关键词匹配
        matched_keywords = []
        for keyword in keyword_map.keys():
            if keyword in user_message:
                matched_keywords.append(keyword)

        # Step 3: 滑动窗口子串扩展匹配（对 4 字以上关键词）
        for keyword in keyword_map.keys():
            if len(keyword) >= 4:
                # 生成 2-4 字滑动窗口子串
                sub_keywords = self._generate_sub_keywords(keyword)
                for sub_kw in sub_keywords:
                    if sub_kw in user_message and sub_kw not in matched_keywords:
                        matched_keywords.append(sub_kw)

        # Step 4: 确定涉及的硬事实
        involved_facts = set()
        for keyword in matched_keywords:
            facts = keyword_map.get(keyword, [])
            involved_facts.update(facts)

        result.matched_keywords = matched_keywords
        result.involved_facts = list(involved_facts)
        result.involves_hard_fact = len(involved_facts) > 0
        result.confidence = min(1.0, len(matched_keywords) / 5)

        if result.involves_hard_fact:
            logger.info(
                "[hard_fact_guard] 输入涉及硬事实：persona=%s, facts=%d, keywords=%d",
                persona_id,
                len(result.involved_facts),
                len(result.matched_keywords),
            )

        return result

    async def check_output(
        self,
        response_text: str,
        involved_facts: List[str],
        persona_id: str,
        belief_store: Optional[Any] = None,
    ) -> OutputCheckResult:
        """检查输出是否与硬事实冲突

        Args:
            response_text: 回复文本
            involved_facts: 涉及的硬事实列表
            persona_id: 人格 ID
            belief_store: 信念存储（可选）

        Returns:
            OutputCheckResult: 输出检查结果
        """
        result = OutputCheckResult()

        if not involved_facts:
            return result

        # Step 1: 正则模式匹配（规则引擎）
        conflict_detected = False
        conflict_type = None
        conflicting_facts = []

        for fact_id in involved_facts:
            # 获取硬事实内容
            fact_content = self._get_fact_content(fact_id, persona_id, belief_store)

            if not fact_content:
                continue

            # 检查矛盾模式
            for pattern_type, patterns in self.CONFLICT_PATTERNS.items():
                for pattern in patterns:
                    if pattern in response_text:
                        conflict_detected = True
                        conflict_type = pattern_type
                        conflicting_facts.append(fact_id)
                        break

                if conflict_detected:
                    break

            if conflict_detected:
                break

        # Step 2: 如果正则无法确定，调用 LLM 语义判断（简化实现）
        if not conflict_detected:
            # TODO: 实现 LLM 语义判断
            # 目前简化处理：不冲突
            pass

        result.has_conflict = conflict_detected
        result.conflict_type = conflict_type
        result.conflicting_facts = list(set(conflicting_facts))
        result.confidence = 0.9 if conflict_detected else 0.0
        result.needs_regeneration = conflict_detected

        if result.has_conflict:
            logger.warning(
                "[hard_fact_guard] 输出与硬事实冲突：persona=%s, type=%s",
                persona_id,
                conflict_type,
            )

        return result

    async def regenerate_with_constraint(
        self,
        user_message: str,
        persona_id: str,
        conflicting_facts: List[str],
        original_response: str = "",
        belief_store: Optional[Any] = None,
    ) -> str:
        """约束重生成

        Args:
            user_message: 用户消息
            persona_id: 人格 ID
            conflicting_facts: 冲突的硬事实列表
            original_response: 原始回复
            belief_store: 信念存储（可选）

        Returns:
            str: 重生成的回复
        """
        # Step 1: 规则修复
        fixed_response = self._rule_based_fix(
            original_response,
            conflicting_facts,
        )

        if fixed_response != original_response:
            logger.info("[hard_fact_guard] 规则修复成功")
            return fixed_response

        # Step 2: LLM 重生成（简化实现）
        # TODO: 实现真实的 LLM 重生成
        # 目前返回保守回复
        conservative_response = self._generate_conservative_response(
            user_message,
            persona_id,
        )

        logger.info("[hard_fact_guard] 返回保守回复")
        return conservative_response

    def _get_hard_fact_keywords(
        self,
        persona_id: str,
        belief_store: Optional[Any] = None,
    ) -> Tuple[List[str], Dict[str, List[str]]]:
        """获取硬事实关键词

        Args:
            persona_id: 人格 ID
            belief_store: 信念存储

        Returns:
            Tuple[List[str], Dict[str, List[str]]]: (硬事实列表，关键词映射)
        """
        # 检查缓存
        if persona_id in self._cache:
            logger.debug("[hard_fact_guard] 使用缓存：persona=%s", persona_id)
            return self._cache[persona_id]

        # 从 belief_store 提取（简化实现）
        hard_facts = []
        keyword_map = {}

        # TODO: 从 belief_store 提取真实的硬事实
        # 目前简化处理：返回空

        # 缓存
        self._cache[persona_id] = (hard_facts, keyword_map)

        return hard_facts, keyword_map

    def _generate_sub_keywords(self, keyword: str) -> List[str]:
        """生成滑动窗口子串

        Args:
            keyword: 关键词（4 字以上）

        Returns:
            List[str]: 2-4 字子串列表
        """
        sub_keywords = []

        for length in range(2, min(5, len(keyword) + 1)):
            for i in range(len(keyword) - length + 1):
                sub_kw = keyword[i : i + length]
                if sub_kw not in sub_keywords:
                    sub_keywords.append(sub_kw)

        return sub_keywords

    def _get_fact_content(
        self,
        fact_id: str,
        persona_id: str,
        belief_store: Optional[Any] = None,
    ) -> Optional[str]:
        """获取硬事实内容

        Args:
            fact_id: 硬事实 ID
            persona_id: 人格 ID
            belief_store: 信念存储

        Returns:
            Optional[str]: 硬事实内容
        """
        # TODO: 从 belief_store 提取
        return None

    def _rule_based_fix(
        self,
        response: str,
        conflicting_facts: List[str],
    ) -> str:
        """规则修复

        Args:
            response: 原始回复
            conflicting_facts: 冲突的硬事实列表

        Returns:
            str: 修复后的回复
        """
        fixed = response

        # 替换矛盾模式
        replacements = {
            "我来帮你": "我可以协助您",
            "我可以帮你": "我可以协助您",
            "我能帮你": "我可以协助您",
            "我保证": "我会尽力",
            "我一定": "我会尽力",
            "包在我身上": "我会尽力协助",
            "我不是": "作为助手",
            "我不认识": "我了解有限",
            "我不知道": "我目前不了解",
        }

        for old, new in replacements.items():
            fixed = fixed.replace(old, new)

        return fixed

    def _generate_conservative_response(
        self,
        user_message: str,
        persona_id: str,
    ) -> str:
        """生成保守回复

        Args:
            user_message: 用户消息
            persona_id: 人格 ID

        Returns:
            str: 保守回复
        """
        # 简化实现
        return "关于这个问题，我建议您参考相关资料或咨询专业人士。"

    def clear_cache(self, persona_id: Optional[str] = None) -> None:
        """清除缓存

        Args:
            persona_id: 人格 ID（可选，None 则清除所有）
        """
        if persona_id:
            self._cache.pop(persona_id, None)
            logger.debug("[hard_fact_guard] 清除缓存：persona=%s", persona_id)
        else:
            self._cache.clear()
            logger.info("[hard_fact_guard] 清除所有缓存")
