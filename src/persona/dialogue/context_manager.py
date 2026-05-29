# Copyright 2026 ShuyuanCore contributors
# SPDX-License-Identifier: Apache-2.0
"""上下文管理器 — 滑动窗口 + 重要性排序 + 压缩。

ContextManager 管理对话上下文：
- add_message(role, content, importance) → DialogMessage
- get_context(max_tokens) → List[Dict]
- get_context_for_llm(system_prompt, max_tokens) → List[Dict]
- compress() → str  # 按策略压缩

压缩策略：
- TRUNCATE: 只保留最近 N 条
- SUMMARY: 旧消息摘要合并
- SELECTIVE: 按重要性保留
- HYBRID: 摘要 + 选择性
"""
from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class MessageRole(Enum):
    """消息角色"""
    
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class MessageImportance(Enum):
    """消息重要性"""
    
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


class CompressionStrategy(Enum):
    """压缩策略"""
    
    NONE = "none"
    TRUNCATE = "truncate"
    SUMMARY = "summary"
    SELECTIVE = "selective"
    HYBRID = "hybrid"


@dataclass
class DialogMessage:
    """对话消息
    
    Attributes:
        role: 消息角色
        content: 消息内容
        timestamp: 时间戳
        importance: 重要性
        token_count: 估算 token 数（中文约 1.5 字符=1 token）
        message_id: 消息 ID（MD5(role+content+timestamp)[:12]）
    """
    
    role: MessageRole
    content: str
    timestamp: float = field(default_factory=time.time)
    importance: MessageImportance = MessageImportance.MEDIUM
    token_count: int = 0
    message_id: str = ""
    
    def __post_init__(self):
        """后处理"""
        # 计算 token 数（简化：中文约 1.5 字符=1 token）
        if self.token_count == 0:
            self.token_count = max(1, len(self.content) // 2)
        
        # 生成消息 ID
        if not self.message_id:
            raw = f"{self.role.value}{self.content}{self.timestamp}"
            self.message_id = hashlib.md5(raw.encode()).hexdigest()[:12]
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "role": self.role.value,
            "content": self.content,
            "timestamp": self.timestamp,
            "importance": self.importance.value,
            "token_count": self.token_count,
            "message_id": self.message_id,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> DialogMessage:
        """从字典创建"""
        return cls(
            role=MessageRole(data["role"]),
            content=data["content"],
            timestamp=data.get("timestamp", time.time()),
            importance=MessageImportance(data.get("importance", 2)),
            token_count=data.get("token_count", 0),
            message_id=data.get("message_id", ""),
        )


@dataclass
class ContextConfig:
    """上下文配置
    
    Attributes:
        max_tokens: 最大 token 数
        window_size: 窗口大小
        compression_threshold: 压缩阈值
        compression_strategy: 压缩策略
        min_messages_to_keep: 最小保留消息数
        enable_auto_compress: 是否启用自动压缩
    """
    
    max_tokens: int = 8192
    window_size: int = 50
    compression_threshold: float = 0.8
    compression_strategy: CompressionStrategy = CompressionStrategy.HYBRID
    min_messages_to_keep: int = 5
    enable_auto_compress: bool = True


class ContextManager:
    """上下文管理器 — 滑动窗口 + 重要性排序 + 压缩
    
    管理对话上下文，支持：
    - 添加消息
    - 获取上下文（按 token 限制）
    - 自动压缩（按策略）
    - LLM 格式输出
    """
    
    def __init__(self, config: Optional[ContextConfig] = None):
        """初始化上下文管理器
        
        Args:
            config: 上下文配置
        """
        self.config = config or ContextConfig()
        self._messages: List[DialogMessage] = []
        self._total_tokens = 0
        
        logger.info(
            "[context_manager] 初始化完成，max_tokens=%d, strategy=%s",
            self.config.max_tokens,
            self.config.compression_strategy.value,
        )
    
    def add_message(
        self,
        role: MessageRole,
        content: str,
        importance: MessageImportance = MessageImportance.MEDIUM,
    ) -> DialogMessage:
        """添加消息
        
        Args:
            role: 消息角色
            content: 消息内容
            importance: 重要性
        
        Returns:
            DialogMessage: 添加的消息
        """
        message = DialogMessage(
            role=role,
            content=content,
            importance=importance,
        )
        
        self._messages.append(message)
        self._total_tokens += message.token_count
        
        logger.debug(
            "[context_manager] 添加消息：role=%s, tokens=%d, total=%d",
            role.value,
            message.token_count,
            self._total_tokens,
        )
        
        # 自动压缩
        if self.config.enable_auto_compress:
            self._auto_compress()
        
        return message
    
    def get_context(
        self,
        max_tokens: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """获取上下文
        
        Args:
            max_tokens: 最大 token 数（可选，默认使用配置值）
        
        Returns:
            List[Dict]: 上下文消息列表
        """
        actual_max = max_tokens or self.config.max_tokens
        
        # 按时间倒序（最新消息优先）
        reversed_messages = list(reversed(self._messages))
        
        selected = []
        current_tokens = 0
        
        for msg in reversed_messages:
            if current_tokens + msg.token_count > actual_max:
                break
            
            selected.append(msg.to_dict())
            current_tokens += msg.token_count
        
        # 恢复正序
        selected.reverse()
        
        logger.debug(
            "[context_manager] 获取上下文：selected=%d, tokens=%d",
            len(selected),
            current_tokens,
        )
        
        return selected
    
    def get_context_for_llm(
        self,
        system_prompt: str = "",
        max_tokens: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """获取 LLM 格式的上下文
        
        Args:
            system_prompt: 系统提示词
            max_tokens: 最大 token 数
        
        Returns:
            List[Dict]: LLM 格式消息列表
        """
        context = self.get_context(max_tokens)
        
        # 构建 LLM 格式
        llm_messages = []
        
        # 添加系统消息
        if system_prompt:
            llm_messages.append({
                "role": "system",
                "content": system_prompt,
            })
        
        # 添加上下文消息
        llm_messages.extend(context)
        
        logger.debug(
            "[context_manager] LLM 格式：total_messages=%d",
            len(llm_messages),
        )
        
        return llm_messages
    
    def compress(self) -> str:
        """压缩上下文
        
        Returns:
            str: 压缩报告
        """
        strategy = self.config.compression_strategy
        
        if strategy == CompressionStrategy.NONE:
            return "压缩策略：NONE（未压缩）"
        
        elif strategy == CompressionStrategy.TRUNCATE:
            return self._truncate()
        
        elif strategy == CompressionStrategy.SUMMARY:
            return self._summary_compress()
        
        elif strategy == CompressionStrategy.SELECTIVE:
            return self._selective_compress()
        
        elif strategy == CompressionStrategy.HYBRID:
            return self._hybrid_compress()
        
        else:
            return "未知压缩策略"
    
    def _auto_compress(self) -> None:
        """自动压缩"""
        threshold = int(self.config.max_tokens * self.config.compression_threshold)
        
        if self._total_tokens > threshold:
            logger.info(
                "[context_manager] 触发自动压缩：total=%d, threshold=%d",
                self._total_tokens,
                threshold,
            )
            self.compress()
    
    def _truncate(self) -> str:
        """截断压缩（只保留最近 N 条）"""
        window_size = self.config.window_size
        
        if len(self._messages) <= window_size:
            return f"截断压缩：无需压缩（{len(self._messages)} <= {window_size}）"
        
        # 保留最近 window_size 条
        removed = self._messages[:-window_size]
        self._messages = self._messages[-window_size:]
        
        # 重新计算 token 数
        self._total_tokens = sum(msg.token_count for msg in self._messages)
        
        removed_tokens = sum(msg.token_count for msg in removed)
        
        return f"截断压缩：移除 {len(removed)} 条消息（{removed_tokens} tokens），保留 {len(self._messages)} 条"
    
    def _summary_compress(self) -> str:
        """摘要压缩（旧消息摘要合并）"""
        # 简化实现：将旧消息合并为一条摘要
        if len(self._messages) <= 5:
            return "摘要压缩：消息较少，无需压缩"
        
        # 保留最近 5 条
        old_messages = self._messages[:-5]
        recent_messages = self._messages[-5:]
        
        # 生成摘要（简化：直接拼接）
        summary_content = f"[摘要] 之前的 {len(old_messages)} 条对话..."
        summary = DialogMessage(
            role=MessageRole.SYSTEM,
            content=summary_content,
            importance=MessageImportance.LOW,
        )
        
        # 替换
        self._messages = [summary] + recent_messages
        self._total_tokens = sum(msg.token_count for msg in self._messages)
        
        return f"摘要压缩：合并 {len(old_messages)} 条旧消息为 1 条摘要"
    
    def _selective_compress(self) -> str:
        """选择性压缩（按重要性保留）"""
        # 保留 HIGH 和 CRITICAL 重要性的消息
        important_messages = [
            msg for msg in self._messages
            if msg.importance in [MessageImportance.HIGH, MessageImportance.CRITICAL]
        ]
        
        # 保留最近 5 条普通消息
        recent_normal = [
            msg for msg in self._messages
            if msg.importance in [MessageImportance.LOW, MessageImportance.MEDIUM]
        ][-5:]
        
        removed_count = len(self._messages) - len(important_messages) - len(recent_normal)
        
        self._messages = important_messages + recent_normal
        self._total_tokens = sum(msg.token_count for msg in self._messages)
        
        return f"选择性压缩：保留 {len(important_messages)} 条重要消息 + {len(recent_normal)} 条近期消息，移除 {removed_count} 条"
    
    def _hybrid_compress(self) -> str:
        """混合压缩（摘要 + 选择性）"""
        # 先选择性保留
        self._selective_compress()
        
        # 再摘要
        if len(self._messages) > 10:
            self._summary_compress()
        
        return f"混合压缩：最终保留 {len(self._messages)} 条消息"
    
    def clear(self) -> None:
        """清空上下文"""
        self._messages.clear()
        self._total_tokens = 0
        logger.info("[context_manager] 上下文已清空")
    
    def get_message_count(self) -> int:
        """获取消息数量
        
        Returns:
            int: 消息数量
        """
        return len(self._messages)
    
    def get_total_tokens(self) -> int:
        """获取总 token 数
        
        Returns:
            int: 总 token 数
        """
        return self._total_tokens
    
    def get_messages(self) -> List[DialogMessage]:
        """获取所有消息
        
        Returns:
            List[DialogMessage]: 消息列表
        """
        return self._messages.copy()
