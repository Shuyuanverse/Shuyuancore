# Copyright 2026 ShuyuanCore contributors
# SPDX-License-Identifier: Apache-2.0
"""Agent 基类。

包含：
- AgentStatus：Agent 状态枚举
- TaskPriority：任务优先级
- TaskStatus：任务状态
- AgentConfig：Agent 配置
- TaskResult：任务结果
- BaseAgent：Agent 抽象基类
"""

from __future__ import annotations

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from .agent_protocol import AgentMessage, Priority

logger = logging.getLogger(__name__)


class AgentStatus(Enum):
    """Agent 状态"""

    IDLE = "idle"  # 空闲
    RUNNING = "running"  # 运行中
    ERROR = "error"  # 错误
    STOPPED = "stopped"  # 已停止


class TaskPriority(Enum):
    """任务优先级"""

    LOW = 1
    NORMAL = 2
    HIGH = 3
    CRITICAL = 4


class TaskStatus(Enum):
    """任务状态"""

    PENDING = "pending"  # 等待中
    RUNNING = "running"  # 运行中
    COMPLETED = "completed"  # 已完成
    FAILED = "failed"  # 失败


@dataclass
class AgentConfig:
    """Agent 配置

    Attributes:
        agent_id: Agent ID
        agent_type: Agent 类型
        max_retries: 最大重试次数
        timeout: 超时时间（秒）
        enable_metrics: 是否启用指标统计
    """

    agent_id: str
    agent_type: str
    max_retries: int = 3
    timeout: float = 30.0
    enable_metrics: bool = True


@dataclass
class TaskResult:
    """任务结果

    Attributes:
        task_id: 任务 ID
        status: 任务状态
        result: 任务结果
        error: 错误信息
        execution_time: 执行时间（秒）
    """

    task_id: str
    status: TaskStatus
    result: Any = None
    error: Optional[str] = None
    execution_time: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "task_id": self.task_id,
            "status": self.status.value,
            "result": self.result,
            "error": self.error,
            "execution_time": self.execution_time,
        }


class BaseAgent(ABC):
    """Agent 抽象基类

    生命周期：IDLE → RUNNING → IDLE
    任务执行：run() 带超时保护
    事件管理：注册/触发事件回调
    指标统计：执行次数、成功率、平均耗时
    """

    def __init__(self, config: AgentConfig):
        """初始化 Agent

        Args:
            config: Agent 配置
        """
        self.config = config
        self._status = AgentStatus.IDLE
        self._events: Dict[str, List[Callable]] = {}
        self._metrics = {
            "execution_count": 0,
            "success_count": 0,
            "failure_count": 0,
            "total_execution_time": 0.0,
        }
        logger.info(
            "[agent] %s 初始化完成：agent_id=%s, type=%s",
            self.__class__.__name__,
            config.agent_id,
            config.agent_type,
        )

    @property
    def status(self) -> AgentStatus:
        """获取 Agent 状态"""
        return self._status

    @abstractmethod
    async def process(self, message: AgentMessage) -> AgentMessage:
        """处理消息（抽象方法，子类实现）

        Args:
            message: 输入消息

        Returns:
            AgentMessage: 输出消息
        """
        pass

    async def run(
        self,
        message: AgentMessage,
        timeout: Optional[float] = None,
    ) -> TaskResult:
        """带超时保护的任务执行

        Args:
            message: 输入消息
            timeout: 超时时间（秒），None 使用配置值

        Returns:
            TaskResult: 任务结果
        """
        import uuid

        task_id = str(uuid.uuid4())
        start_time = time.time()

        self._status = AgentStatus.RUNNING
        self._metrics["execution_count"] += 1

        try:
            # 设置超时
            actual_timeout = timeout or self.config.timeout

            # 执行任务
            result = await asyncio.wait_for(
                self.process(message),
                timeout=actual_timeout,
            )

            execution_time = time.time() - start_time
            self._metrics["success_count"] += 1
            self._metrics["total_execution_time"] += execution_time

            task_result = TaskResult(
                task_id=task_id,
                status=TaskStatus.COMPLETED,
                result=result,
                execution_time=execution_time,
            )

            self._emit_event("task_completed", task_result)

        except asyncio.TimeoutError:
            execution_time = time.time() - start_time
            self._metrics["failure_count"] += 1

            error_msg = f"任务超时（{actual_timeout}秒）"
            logger.error("[agent] %s", error_msg)

            task_result = TaskResult(
                task_id=task_id,
                status=TaskStatus.FAILED,
                error=error_msg,
                execution_time=execution_time,
            )

            self._emit_event("task_failed", task_result)

        except Exception as e:
            execution_time = time.time() - start_time
            self._metrics["failure_count"] += 1

            error_msg = f"任务失败：{str(e)}"
            logger.exception("[agent] %s", error_msg)

            task_result = TaskResult(
                task_id=task_id,
                status=TaskStatus.FAILED,
                error=error_msg,
                execution_time=execution_time,
            )

            self._emit_event("task_failed", task_result)

        finally:
            self._status = AgentStatus.IDLE

        return task_result

    def register_event(self, event_type: str, callback: Callable) -> None:
        """注册事件回调

        Args:
            event_type: 事件类型
            callback: 回调函数
        """
        if event_type not in self._events:
            self._events[event_type] = []
        self._events[event_type].append(callback)
        logger.debug("[agent] 注册事件回调：event_type=%s", event_type)

    def _emit_event(self, event_type: str, data: Any) -> None:
        """触发事件

        Args:
            event_type: 事件类型
            data: 事件数据
        """
        if event_type in self._events:
            for callback in self._events[event_type]:
                try:
                    callback(data)
                except Exception as e:
                    logger.error(
                        "[agent] 事件回调失败：event_type=%s, error=%s",
                        event_type,
                        e,
                    )

    def get_metrics(self) -> Dict[str, Any]:
        """获取指标统计

        Returns:
            Dict: 指标数据
        """
        metrics = self._metrics.copy()

        # 计算成功率
        if metrics["execution_count"] > 0:
            metrics["success_rate"] = metrics["success_count"] / metrics["execution_count"]
        else:
            metrics["success_rate"] = 0.0

        # 计算平均耗时
        if metrics["success_count"] > 0:
            metrics["avg_execution_time"] = (
                metrics["total_execution_time"] / metrics["success_count"]
            )
        else:
            metrics["avg_execution_time"] = 0.0

        return metrics

    def stop(self) -> None:
        """停止 Agent"""
        self._status = AgentStatus.STOPPED
        logger.info("[agent] Agent 已停止：agent_id=%s", self.config.agent_id)
