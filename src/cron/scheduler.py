from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from typing import Any

import aiosqlite

from src.cron.job import CronJob, JobPriority, JobStatus, RecurringJob
from src.exceptions import CronError, ResourceNotFoundError

logger = logging.getLogger(__name__)

_DB_PATH: str = "data/state.db"

_SCHEDULER_INSTANCE: CronScheduler | None = None


def _cron_job_from_row(row: aiosqlite.Row) -> CronJob:
    """将数据库行转换为 CronJob 对象 / Convert a database row to a CronJob object.

    Args:
        row: 数据库查询结果行 / Database query result row.

    Returns:
        CronJob 实例 / CronJob instance.
    """
    return CronJob(
        id=row["id"],
        name=row["name"],
        task_type=row["task_type"],
        task_message=row["task_message"],
        cron_expression=row["cron_expression"],
        timezone=row["timezone"],
        priority=JobPriority(row["priority"]),
        timeout=row["timeout"],
        max_retries=row["max_retries"],
        retry_count=row["retry_count"],
        status=JobStatus(row["status"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        last_run_at=row["last_run_at"],
        next_run_at=row["next_run_at"],
        tags=json.loads(row["tags_json"]) if row["tags_json"] else [],
        metadata=json.loads(row["metadata_json"]) if row["metadata_json"] else {},
    )


def _recurring_job_from_row(row: aiosqlite.Row) -> RecurringJob:
    """将数据库行转换为 RecurringJob 对象 / Convert a database row to a RecurringJob object.

    Args:
        row: 数据库查询结果行 / Database query result row.

    Returns:
        RecurringJob 实例 / RecurringJob instance.
    """
    return RecurringJob(
        id=row["id"],
        name=row["name"],
        task_type=row["task_type"],
        task_message=row["task_message"],
        cron_expression=row["cron_expression"],
        timezone=row["timezone"],
        priority=JobPriority(row["priority"]),
        timeout=row["timeout"],
        max_retries=row["max_retries"],
        retry_count=row["retry_count"],
        status=JobStatus(row["status"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        last_run_at=row["last_run_at"],
        next_run_at=row["next_run_at"],
        tags=json.loads(row["tags_json"]) if row["tags_json"] else [],
        metadata=json.loads(row["metadata_json"]) if row["metadata_json"] else {},
        is_active=bool(row["is_active"]),
        total_runs=row["total_runs"],
        success_runs=row["success_runs"],
        fail_runs=row["fail_runs"],
    )


class CronScheduler:
    """定时任务调度器 / Cron job scheduler.

    提供基于 aiosqlite 的异步定时任务 CRUD 和调度功能。
    Provides async CRUD and scheduling for cron jobs via aiosqlite.

    Args:
        db_path: SQLite 数据库文件路径 / SQLite database file path.
    """

    def __init__(self, db_path: str = _DB_PATH) -> None:
        self._db_path: str = db_path
        self._conn: aiosqlite.Connection | None = None

    async def _get_conn(self) -> aiosqlite.Connection:
        """获取数据库连接（懒加载） / Get database connection (lazy load).

        Returns:
            aiosqlite Connection 实例 / aiosqlite Connection instance.
        """
        if self._conn is None:
            self._conn = await aiosqlite.connect(self._db_path)
            self._conn.row_factory = aiosqlite.Row
            await self._conn.execute("PRAGMA journal_mode = WAL;")
            await self._conn.execute("PRAGMA foreign_keys = ON;")
            await self._conn.execute("PRAGMA busy_timeout = 5000;")
            await self._conn.commit()
        return self._conn

    async def initialize(self) -> None:
        """初始化数据库表结构 / Initialize database table schema."""
        conn = await self._get_conn()
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS cron_jobs (
                id              TEXT PRIMARY KEY,
                name            TEXT NOT NULL,
                task_type       TEXT NOT NULL,
                task_message    TEXT NOT NULL,
                cron_expression TEXT NOT NULL,
                timezone        TEXT NOT NULL DEFAULT 'UTC',
                priority        INTEGER NOT NULL DEFAULT 1,
                timeout         INTEGER NOT NULL DEFAULT 300,
                max_retries     INTEGER NOT NULL DEFAULT 0,
                retry_count     INTEGER NOT NULL DEFAULT 0,
                status          TEXT NOT NULL DEFAULT 'pending',
                created_at      REAL NOT NULL,
                updated_at      REAL NOT NULL,
                last_run_at     REAL,
                next_run_at     REAL,
                tags_json       TEXT NOT NULL DEFAULT '[]',
                metadata_json   TEXT NOT NULL DEFAULT '{}',
                is_active       INTEGER NOT NULL DEFAULT 1,
                total_runs      INTEGER NOT NULL DEFAULT 0,
                success_runs    INTEGER NOT NULL DEFAULT 0,
                fail_runs       INTEGER NOT NULL DEFAULT 0
            );
            """
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_cron_jobs_status ON cron_jobs(status);"
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_cron_jobs_next_run ON cron_jobs(next_run_at);"
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_cron_jobs_is_active ON cron_jobs(is_active);"
        )
        await conn.commit()
        logger.info(
            "定时任务表初始化完成 / Cron jobs table initialized (path=%s)", self._db_path
        )

    async def create_job(self, job: CronJob | RecurringJob) -> str:
        """创建定时任务 / Create a cron job.

        Args:
            job: CronJob 或 RecurringJob 实例 / CronJob or RecurringJob instance.

        Returns:
            创建的任务 ID / Created job ID.

        Raises:
            CronError: 创建任务失败 / Failed to create job.
        """
        conn = await self._get_conn()
        is_recurring = isinstance(job, RecurringJob)
        try:
            await conn.execute(
                """
                INSERT INTO cron_jobs (
                    id, name, task_type, task_message, cron_expression,
                    timezone, priority, timeout, max_retries, retry_count,
                    status, created_at, updated_at, last_run_at, next_run_at,
                    tags_json, metadata_json, is_active, total_runs, success_runs, fail_runs
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job.id,
                    job.name,
                    job.task_type,
                    job.task_message,
                    job.cron_expression,
                    job.timezone,
                    job.priority.value,
                    job.timeout,
                    job.max_retries,
                    job.retry_count,
                    job.status.value,
                    job.created_at,
                    job.updated_at,
                    job.last_run_at,
                    job.next_run_at,
                    json.dumps(job.tags, ensure_ascii=False),
                    json.dumps(job.metadata, ensure_ascii=False),
                    1 if is_recurring and job.is_active else 1,
                    job.total_runs if is_recurring else 0,
                    job.success_runs if is_recurring else 0,
                    job.fail_runs if is_recurring else 0,
                ),
            )
            await conn.commit()
            logger.info("定时任务创建成功 / Cron job created: %s (%s)", job.id, job.name)
            return job.id
        except Exception as e:
            logger.error("创建定时任务失败 / Failed to create cron job: %s", e)
            raise CronError(
                f"创建定时任务失败 / Failed to create cron job: {e}"
            ) from e

    async def get_job(self, job_id: str) -> CronJob | None:
        """根据 ID 获取定时任务 / Get a cron job by ID.

        Args:
            job_id: 任务 ID / Job ID.

        Returns:
            CronJob 实例（不存在时返回 None） / CronJob instance (or None if not found).
        """
        conn = await self._get_conn()
        cursor = await conn.execute(
            "SELECT * FROM cron_jobs WHERE id = ?", (job_id,)
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return _cron_job_from_row(row)

    async def list_jobs(
        self, status: JobStatus | None = None, limit: int = 50
    ) -> list[CronJob]:
        """获取定时任务列表 / List cron jobs.

        Args:
            status: 按状态筛选（可选） / Filter by status (optional).
            limit: 返回数量上限 / Maximum number of results.

        Returns:
            CronJob 实例列表 / List of CronJob instances.
        """
        conn = await self._get_conn()
        if status is not None:
            cursor = await conn.execute(
                "SELECT * FROM cron_jobs WHERE status = ? ORDER BY created_at DESC LIMIT ?",
                (status.value, limit),
            )
        else:
            cursor = await conn.execute(
                "SELECT * FROM cron_jobs ORDER BY created_at DESC LIMIT ?",
                (limit,),
            )
        rows = await cursor.fetchall()
        return [_cron_job_from_row(r) for r in rows]

    async def update_job(self, job: CronJob | RecurringJob) -> None:
        """更新定时任务 / Update a cron job.

        Args:
            job: 包含更新后数据的 CronJob 实例 / CronJob instance with updated data.

        Raises:
            ResourceNotFoundError: 任务不存在 / Job not found.
            CronError: 更新失败 / Update failed.
        """
        conn = await self._get_conn()
        is_recurring = isinstance(job, RecurringJob)
        try:
            cursor = await conn.execute(
                "SELECT id FROM cron_jobs WHERE id = ?", (job.id,)
            )
            existing = await cursor.fetchone()
            if existing is None:
                raise ResourceNotFoundError(
                    f"定时任务不存在 / Cron job not found: {job.id}"
                )

            await conn.execute(
                """
                UPDATE cron_jobs SET
                    name = ?, task_type = ?, task_message = ?, cron_expression = ?,
                    timezone = ?, priority = ?, timeout = ?, max_retries = ?,
                    retry_count = ?, status = ?, updated_at = ?,
                    last_run_at = ?, next_run_at = ?,
                    tags_json = ?, metadata_json = ?,
                    is_active = ?, total_runs = ?, success_runs = ?, fail_runs = ?
                WHERE id = ?
                """,
                (
                    job.name,
                    job.task_type,
                    job.task_message,
                    job.cron_expression,
                    job.timezone,
                    job.priority.value,
                    job.timeout,
                    job.max_retries,
                    job.retry_count,
                    job.status.value,
                    job.updated_at,
                    job.last_run_at,
                    job.next_run_at,
                    json.dumps(job.tags, ensure_ascii=False),
                    json.dumps(job.metadata, ensure_ascii=False),
                    1 if is_recurring and job.is_active else 1,
                    job.total_runs if is_recurring else 0,
                    job.success_runs if is_recurring else 0,
                    job.fail_runs if is_recurring else 0,
                    job.id,
                ),
            )
            await conn.commit()
            logger.info("定时任务更新成功 / Cron job updated: %s", job.id)
        except ResourceNotFoundError:
            raise
        except Exception as e:
            logger.error("更新定时任务失败 / Failed to update cron job: %s", e)
            raise CronError(
                f"更新定时任务失败 / Failed to update cron job: {e}"
            ) from e

    async def delete_job(self, job_id: str) -> None:
        """删除定时任务 / Delete a cron job.

        Args:
            job_id: 任务 ID / Job ID.

        Raises:
            ResourceNotFoundError: 任务不存在 / Job not found.
        """
        conn = await self._get_conn()
        cursor = await conn.execute(
            "SELECT id FROM cron_jobs WHERE id = ?", (job_id,)
        )
        existing = await cursor.fetchone()
        if existing is None:
            raise ResourceNotFoundError(
                f"定时任务不存在 / Cron job not found: {job_id}"
            )
        await conn.execute("DELETE FROM cron_jobs WHERE id = ?", (job_id,))
        await conn.commit()
        logger.info("定时任务已删除 / Cron job deleted: %s", job_id)

    async def pause_job(self, job_id: str) -> None:
        """暂停定时任务 / Pause a cron job.

        Args:
            job_id: 任务 ID / Job ID.

        Raises:
            ResourceNotFoundError: 任务不存在 / Job not found.
        """
        conn = await self._get_conn()
        cursor = await conn.execute(
            "SELECT id, is_active FROM cron_jobs WHERE id = ?", (job_id,)
        )
        existing = await cursor.fetchone()
        if existing is None:
            raise ResourceNotFoundError(
                f"定时任务不存在 / Cron job not found: {job_id}"
            )
        await conn.execute(
            "UPDATE cron_jobs SET is_active = 0, updated_at = ? WHERE id = ?",
            (time.time(), job_id),
        )
        await conn.commit()
        logger.info("定时任务已暂停 / Cron job paused: %s", job_id)

    async def resume_job(self, job_id: str) -> None:
        """恢复定时任务 / Resume a cron job.

        Args:
            job_id: 任务 ID / Job ID.

        Raises:
            ResourceNotFoundError: 任务不存在 / Job not found.
        """
        conn = await self._get_conn()
        cursor = await conn.execute(
            "SELECT id, is_active FROM cron_jobs WHERE id = ?", (job_id,)
        )
        existing = await cursor.fetchone()
        if existing is None:
            raise ResourceNotFoundError(
                f"定时任务不存在 / Cron job not found: {job_id}"
            )
        await conn.execute(
            "UPDATE cron_jobs SET is_active = 1, updated_at = ? WHERE id = ?",
            (time.time(), job_id),
        )
        await conn.commit()
        logger.info("定时任务已恢复 / Cron job resumed: %s", job_id)

    async def get_due_jobs(self) -> list[CronJob]:
        """获取到期待执行的任务 / Get jobs that are due to run.

        筛选条件为：is_active=1，status 为 pending 或 failed（且 retry_count < max_retries），
        且 next_run_at <= 当前时间。

        Filters: is_active=1, status is pending/failed (with retries remaining),
        and next_run_at <= current time.

        Returns:
            到期待执行的 CronJob 列表 / List of due CronJob instances.
        """
        conn = await self._get_conn()
        now = time.time()
        cursor = await conn.execute(
            """
            SELECT * FROM cron_jobs
            WHERE is_active = 1
              AND (status = ? OR (status = ? AND retry_count < max_retries))
              AND next_run_at IS NOT NULL
              AND next_run_at <= ?
            ORDER BY priority DESC, next_run_at ASC
            """,
            (JobStatus.pending.value, JobStatus.failed.value, now),
        )
        rows = await cursor.fetchall()
        return [_cron_job_from_row(r) for r in rows]

    async def mark_running(self, job_id: str) -> None:
        """将任务标记为运行中 / Mark a job as running.

        Args:
            job_id: 任务 ID / Job ID.

        Raises:
            ResourceNotFoundError: 任务不存在 / Job not found.
        """
        conn = await self._get_conn()
        cursor = await conn.execute(
            "SELECT id FROM cron_jobs WHERE id = ?", (job_id,)
        )
        existing = await cursor.fetchone()
        if existing is None:
            raise ResourceNotFoundError(
                f"定时任务不存在 / Cron job not found: {job_id}"
            )
        now = time.time()
        await conn.execute(
            """
            UPDATE cron_jobs
            SET status = ?, last_run_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (JobStatus.running.value, now, now, job_id),
        )
        await conn.commit()

    async def mark_completed(self, job_id: str) -> None:
        """将任务标记为已完成 / Mark a job as completed.

        Args:
            job_id: 任务 ID / Job ID.

        Raises:
            ResourceNotFoundError: 任务不存在 / Job not found.
        """
        conn = await self._get_conn()
        cursor = await conn.execute(
            "SELECT id FROM cron_jobs WHERE id = ?", (job_id,)
        )
        existing = await cursor.fetchone()
        if existing is None:
            raise ResourceNotFoundError(
                f"定时任务不存在 / Cron job not found: {job_id}"
            )
        now = time.time()
        next_run = self._compute_next_run(job_id)
        await conn.execute(
            """
            UPDATE cron_jobs
            SET status = ?, retry_count = 0, total_runs = total_runs + 1,
                success_runs = success_runs + 1, next_run_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (JobStatus.completed.value, next_run, now, job_id),
        )
        await conn.commit()
        logger.info("定时任务已完成 / Cron job completed: %s", job_id)

    async def mark_failed(self, job_id: str, error_message: str = "") -> None:
        """将任务标记为失败 / Mark a job as failed.

        如果 retry_count < max_retries，状态将保持为 pending 以允许重试，
        否则状态变为 failed。

        If retry_count < max_retries, status stays pending for retry,
        otherwise status becomes failed.

        Args:
            job_id: 任务 ID / Job ID.
            error_message: 错误信息 / Error message.

        Raises:
            ResourceNotFoundError: 任务不存在 / Job not found.
        """
        conn = await self._get_conn()
        cursor = await conn.execute(
            "SELECT * FROM cron_jobs WHERE id = ?", (job_id,)
        )
        row = await cursor.fetchone()
        if row is None:
            raise ResourceNotFoundError(
                f"定时任务不存在 / Cron job not found: {job_id}"
            )
        now = time.time()
        new_retry_count = row["retry_count"] + 1
        has_retries = new_retry_count < row["max_retries"]

        metadata: dict[str, Any] = json.loads(row["metadata_json"]) if row["metadata_json"] else {}
        errors: list[str] = metadata.get("errors", [])
        errors.append(error_message)
        metadata["errors"] = errors

        if has_retries:
            new_status = JobStatus.pending.value
        else:
            new_status = JobStatus.failed.value

        await conn.execute(
            """
            UPDATE cron_jobs
            SET status = ?, retry_count = ?, total_runs = total_runs + 1,
                fail_runs = fail_runs + 1,
                metadata_json = ?, updated_at = ?
            WHERE id = ?
            """,
            (new_status, new_retry_count, json.dumps(metadata, ensure_ascii=False), now, job_id),
        )
        await conn.commit()

        if has_retries:
            logger.warning(
                "定时任务执行失败，将重试 (%d/%d): %s - %s",
                new_retry_count,
                row["max_retries"],
                job_id,
                error_message,
            )
        else:
            logger.error(
                "定时任务已失败（无更多重试） / Cron job failed (no more retries): %s - %s",
                job_id,
                error_message,
            )

    async def cleanup(self, max_age_days: int = 30) -> int:
        """清理旧的已完成/已取消任务记录 / Clean up old completed/cancelled job records.

        Args:
            max_age_days: 保留天数 / Retention period in days.

        Returns:
            清理的记录数 / Number of cleaned records.
        """
        conn = await self._get_conn()
        cutoff = time.time() - max_age_days * 86400
        cursor = await conn.execute(
            """
            DELETE FROM cron_jobs
            WHERE status IN (?, ?)
              AND updated_at < ?
            """,
            (JobStatus.completed.value, JobStatus.cancelled.value, cutoff),
        )
        deleted = cursor.rowcount
        await conn.commit()
        if deleted > 0:
            logger.info(
                "定时任务清理完成 / Cron jobs cleanup done: removed %d records (age > %d days)",
                deleted,
                max_age_days,
            )
        return deleted

    def _parse_cron_expression(self, cron_expr: str) -> list[list[int]]:
        """解析 5 位 Cron 表达式 / Parse a 5-field cron expression.

        支持格式：
        - * （通配符 / wildcard）
        - */n （步长 / step value）
        - 1,2,3 （逗号分隔列表 / comma-separated list）
        - 单个数字 / single number

        Args:
            cron_expr: 5 位 cron 表达式（空格分隔） / 5-field cron expression (space-separated).

        Returns:
            包含 5 个列表的二维数组，每个列表对应各字段的有效值。
            A list of 5 lists, each containing valid values for the respective field.

        Raises:
            CronError: 表达式格式无效 / Invalid cron expression format.
        """
        parts = cron_expr.strip().split()
        if len(parts) != 5:
            raise CronError(
                f"Cron 表达式格式无效，需要 5 个字段（当前 {len(parts)} 个）"
                f" / Invalid cron expression, expected 5 fields (got {len(parts)})"
            )

        ranges = [
            (0, 59),   # minute
            (0, 23),   # hour
            (1, 31),   # day of month
            (1, 12),   # month
            (0, 7),    # day of week (0 and 7 = Sunday)
        ]

        result: list[list[int]] = []
        for i, (part, (low, high)) in enumerate(zip(parts, ranges)):
            values = self._parse_cron_field(part, low, high)
            # Normalize day of week: 7 -> 0 (Sunday)
            if i == 4:
                values = [v if v != 7 else 0 for v in values]
            result.append(sorted(set(values)))
        return result

    def _parse_cron_field(self, field: str, low: int, high: int) -> list[int]:
        """解析单个 Cron 字段 / Parse a single cron field.

        Args:
            field: 字段字符串 / Field string.
            low: 最小值 / Minimum value.
            high: 最大值 / Maximum value.

        Returns:
            有效值列表 / List of valid values.

        Raises:
            CronError: 字段格式无效 / Invalid field format.
        """
        if field == "*":
            return list(range(low, high + 1))

        if field.startswith("*/"):
            try:
                step = int(field[2:])
                if step <= 0:
                    raise ValueError
                return list(range(low, high + 1, step))
            except ValueError:
                raise CronError(
                    f"Cron 字段步长无效 / Invalid cron field step: {field}"
                )

        if "," in field:
            values: list[int] = []
            for part in field.split(","):
                values.extend(self._parse_cron_field(part, low, high))
            return values

        if "-" in field:
            try:
                start_str, end_str = field.split("-", 1)
                start, end = int(start_str), int(end_str)
                if start < low or end > high or start > end:
                    raise ValueError
                return list(range(start, end + 1))
            except ValueError:
                raise CronError(
                    f"Cron 字段范围无效 / Invalid cron field range: {field}"
                )

        try:
            val = int(field)
            if val < low or val > high:
                raise CronError(
                    f"Cron 字段值 {val} 超出范围 [{low}, {high}]"
                    f" / Cron field value {val} out of range [{low}, {high}]"
                )
            return [val]
        except ValueError:
            raise CronError(
                f"Cron 字段无法解析 / Cannot parse cron field: {field}"
            )

    def _match_cron(self, cron_expr: str, current: datetime | None = None) -> bool:
        """检查给定时间是否匹配 Cron 表达式 / Check if a given time matches a cron expression.

        Args:
            cron_expr: 5 位 cron 表达式 / 5-field cron expression.
            current: 待检查的时间（默认当前 UTC 时间） / Time to check (default: current UTC time).

        Returns:
            匹配返回 True / True if matches.
        """
        if current is None:
            current = datetime.now(timezone.utc)
        parsed = self._parse_cron_expression(cron_expr)

        minutes, hours, days, months, weekdays = parsed

        if current.month not in months:
            return False
        if current.day not in days:
            return False
        if current.hour not in hours:
            return False
        if current.minute not in minutes:
            return False

        dow = current.weekday()
        dow = (dow + 1) % 7
        if dow not in weekdays:
            return False

        return True

    def _compute_next_run(self, job_id: str) -> float | None:
        """计算任务的下次执行时间 / Compute the next run time for a job.

        这是一个简化实现，实际使用中建议使用 croniter 等专业库。
        This is a simplified implementation; consider using croniter for production.

        Args:
            job_id: 任务 ID / Job ID.

        Returns:
            下次执行时间戳（无法计算时返回 None） / Next run timestamp (None if cannot compute).
        """
        return None


def get_scheduler(db_path: str = _DB_PATH) -> CronScheduler:
    """获取 CronScheduler 单例 / Get the CronScheduler singleton.

    Args:
        db_path: SQLite 数据库文件路径 / SQLite database file path.

    Returns:
        CronScheduler 实例 / CronScheduler instance.
    """
    global _SCHEDULER_INSTANCE
    if _SCHEDULER_INSTANCE is None:
        _SCHEDULER_INSTANCE = CronScheduler(db_path=db_path)
    return _SCHEDULER_INSTANCE