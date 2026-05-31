import pytest

from src.cron.job import CronJob, JobPriority, JobStatus, RecurringJob
from src.cron.scheduler import CronScheduler


class TestCronJob:
    def test_cron_job_creation(self):
        job = CronJob(
            id="test-1",
            name="test-job",
            task_type="echo",
            task_message="hello",
            cron_expression="0 * * * *",
        )
        assert job.id == "test-1"
        assert job.name == "test-job"
        assert job.task_type == "echo"
        assert job.task_message == "hello"
        assert job.cron_expression == "0 * * * *"
        assert job.priority == JobPriority.normal
        assert job.status == JobStatus.pending

    def test_cron_job_defaults(self):
        job = CronJob(
            id="test-2",
            name="test-job-2",
            task_type="echo",
            task_message="world",
            cron_expression="*/5 * * * *",
        )
        assert job.timezone == "UTC"
        assert job.timeout == 300
        assert job.max_retries == 0
        assert job.retry_count == 0
        assert job.tags == []
        assert job.metadata == {}
        assert job.last_run_at is None
        assert job.next_run_at is None

    def test_recurring_job_defaults(self):
        job = RecurringJob(
            id="recur-1",
            name="recurring-job",
            task_type="echo",
            task_message="recurring",
            cron_expression="0 0 * * *",
        )
        assert job.is_active is True
        assert job.total_runs == 0
        assert job.success_runs == 0
        assert job.fail_runs == 0

    def test_job_status_enum(self):
        assert JobStatus.pending.value == "pending"
        assert JobStatus.running.value == "running"
        assert JobStatus.completed.value == "completed"
        assert JobStatus.failed.value == "failed"
        assert JobStatus.cancelled.value == "cancelled"
        assert JobStatus.skipped.value == "skipped"

    def test_job_priority_enum(self):
        assert JobPriority.low.value == 0
        assert JobPriority.normal.value == 1
        assert JobPriority.high.value == 2
        assert JobPriority.critical.value == 3