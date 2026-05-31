from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any


class JobStatus(enum.Enum):
    """任务状态枚举 / Job status enumeration."""

    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"
    skipped = "skipped"


class JobPriority(enum.IntEnum):
    """任务优先级枚举 / Job priority enumeration."""

    low = 0
    normal = 1
    high = 2
    critical = 3


@dataclass
class CronJob:
    """定时任务数据类 / Cron job data class.

    Args:
        id: 任务唯一标识 / Unique job identifier.
        name: 任务名称 / Job name.
        task_type: 任务类型 / Task type.
        task_message: 任务消息内容 / Task message content.
        cron_expression: Cron 表达式（5位） / Cron expression (5-field).
        timezone: 时区 / Timezone.
        priority: 优先级 / Priority.
        timeout: 超时时间（秒） / Timeout in seconds.
        max_retries: 最大重试次数 / Maximum retry count.
        retry_count: 当前重试次数 / Current retry count.
        status: 任务状态 / Job status.
        created_at: 创建时间戳 / Creation timestamp.
        updated_at: 更新时间戳 / Update timestamp.
        last_run_at: 上次执行时间戳 / Last run timestamp.
        next_run_at: 下次执行时间戳 / Next run timestamp.
        tags: 标签列表 / Tag list.
        metadata: 元数据字典 / Metadata dictionary.
    """

    id: str
    name: str
    task_type: str
    task_message: str
    cron_expression: str
    timezone: str = "UTC"
    priority: JobPriority = JobPriority.normal
    timeout: int = 300
    max_retries: int = 0
    retry_count: int = 0
    status: JobStatus = JobStatus.pending
    created_at: float = 0.0
    updated_at: float = 0.0
    last_run_at: float | None = None
    next_run_at: float | None = None
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RecurringJob(CronJob):
    """循环任务数据类，继承 CronJob / Recurring job data class, inherits CronJob.

    Args:
        is_active: 是否激活 / Whether the job is active.
        total_runs: 总执行次数 / Total run count.
        success_runs: 成功执行次数 / Successful run count.
        fail_runs: 失败执行次数 / Failed run count.
    """

    is_active: bool = True
    total_runs: int = 0
    success_runs: int = 0
    fail_runs: int = 0