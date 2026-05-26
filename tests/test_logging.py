from __future__ import annotations

import json
import logging
import logging.handlers
import tempfile
from pathlib import Path
from typing import Generator

import pytest

from src.logging import (
    SensitiveDataFilter,
    _parse_size,
    _reset_correlation_id,
    get_correlation_id,
    get_logger,
    reset_logging,
    set_correlation_id,
    setup_logging,
)


@pytest.fixture(autouse=True)
def _reset() -> Generator[None, None, None]:
    reset_logging()
    _reset_correlation_id()
    yield
    reset_logging()
    _reset_correlation_id()


class TestParseSize:

    @pytest.mark.parametrize(
        "input_str,expected",
        [
            ("10MB", 10 * 1024 * 1024),
            ("100KB", 100 * 1024),
            ("1GB", 1 * 1024**3),
            ("512B", 512),
            ("2 MB", 2 * 1024 * 1024),
            ("1gb", 1 * 1024**3),
            ("100", 100),
        ],
    )
    def test_valid(self, input_str: str, expected: int) -> None:
        assert _parse_size(input_str) == expected

    def test_invalid_then_default(self) -> None:
        assert _parse_size("invalid") == 10 * 1024 * 1024


class TestCorrelationIdFilter:

    def test_default_is_dash(self) -> None:
        logger = logging.getLogger("test_cid")
        logger.handlers.clear()
        handler = logging.StreamHandler()
        handler.addFilter(
            __import__(
                "src.logging", fromlist=["CorrelationIdFilter"]
            ).CorrelationIdFilter()
        )
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)
        logger.info("test")

    def test_sets_correlation_id(self) -> None:
        filter_ = __import__("src.logging", fromlist=["CorrelationIdFilter"]).CorrelationIdFilter()
        record = logging.LogRecord("test", logging.INFO, "", 0, "msg", (), None)
        assert filter_.filter(record) is True
        assert hasattr(record, "correlation_id")


class TestSensitiveDataFilter:

    def test_sk_key(self) -> None:
        filter_ = SensitiveDataFilter()
        record = logging.LogRecord(
            "test", logging.INFO, "", 0,
            "using sk-abc123456789012345678901234567890", (), None,
        )
        filter_.filter(record)
        assert "sk-***REDACTED***" in record.getMessage()
        assert "sk-abc123456789012345678901234567890" not in record.getMessage()

    def test_bearer_token(self) -> None:
        filter_ = SensitiveDataFilter()
        record = logging.LogRecord(
            "test", logging.INFO, "", 0,
            "Authorization: Bearer abcdefghijklmnopqrstuvwxyz123456", (), None,
        )
        filter_.filter(record)
        assert "Bearer ***REDACTED***" in record.getMessage()
        assert "abcdefghijklmnopqrstuvwxyz123456" not in record.getMessage()

    def test_api_key_in_message(self) -> None:
        filter_ = SensitiveDataFilter()
        record = logging.LogRecord(
            "test", logging.INFO, "", 0,
            "api_key=sk-abcdef1234567890abcdef1234567890", (), None,
        )
        filter_.filter(record)
        result = record.getMessage()
        assert "api_key=***REDACTED***" in result

    def test_dashscope_key(self) -> None:
        filter_ = SensitiveDataFilter()
        record = logging.LogRecord(
            "test", logging.INFO, "", 0,
            "DASHSCOPE_API_KEY=sk-abcdef1234567890", (), None,
        )
        filter_.filter(record)
        result = record.getMessage()
        assert "DASHSCOPE_API_KEY=***REDACTED***" in result

    def test_clean_message_unchanged(self) -> None:
        filter_ = SensitiveDataFilter()
        record = logging.LogRecord(
            "test", logging.INFO, "", 0,
            "hello world", (), None,
        )
        filter_.filter(record)
        assert record.getMessage() == "hello world"


class TestCorrelationIdFunctions:

    def test_default_is_none(self) -> None:
        assert get_correlation_id() is None

    def test_set_and_get(self) -> None:
        set_correlation_id("abc-123")
        assert get_correlation_id() == "abc-123"

    def test_overwrite(self) -> None:
        set_correlation_id("first")
        set_correlation_id("second")
        assert get_correlation_id() == "second"

    def test_reset(self) -> None:
        set_correlation_id("test")
        _reset_correlation_id()
        assert get_correlation_id() is None


class TestSetupLogging:

    def test_prod_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            setup_logging(
                log_dir=tmpdir,
                log_level="WARNING",
                environment="prod",
            )
            root = logging.getLogger()
            root.info("should not appear")
            root.warning("warning message")

            log_file = Path(tmpdir) / "app.log"
            assert log_file.exists()
            content = log_file.read_text()
            assert '"warning message"' in content

    def test_dev_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            setup_logging(
                log_dir=tmpdir,
                log_level="DEBUG",
                environment="dev",
            )
            root = logging.getLogger()
            root.debug("debug msg")
            root.info("info msg")

            log_file = Path(tmpdir) / "app.log"
            assert log_file.exists()
            content = log_file.read_text()
            lines = [line for line in content.split("\n") if line.strip()]
            assert len(lines) >= 2

    def test_rotating_file_handler(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            setup_logging(
                log_dir=tmpdir,
                log_level="INFO",
                environment="prod",
            )
            root = logging.getLogger()
            handler_found = False
            for handler in root.handlers:
                if isinstance(handler, logging.handlers.RotatingFileHandler):
                    handler_found = True
                    assert handler.maxBytes > 0
                    assert handler.backupCount > 0
            assert handler_found

    def test_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            setup_logging(log_dir=tmpdir)
            handler_count = len(logging.getLogger().handlers)
            setup_logging(log_dir=tmpdir)
            assert len(logging.getLogger().handlers) == handler_count


class TestGetLogger:

    def test_returns_logger(self) -> None:
        logger = get_logger("test")
        assert isinstance(logger, logging.Logger)

    def test_correct_name(self) -> None:
        logger = get_logger("my.module")
        assert logger.name == "my.module"


class TestAuditLogger:

    def test_audit_logger_exists(self) -> None:
        from src.logging import get_audit_logger
        audit = get_audit_logger()
        assert audit.name == "shuyuancore.audit"

    def test_audit_writes_to_file(self) -> None:
        from src.logging import get_audit_logger

        with tempfile.TemporaryDirectory() as tmpdir:
            setup_logging(log_dir=tmpdir)
            audit = get_audit_logger()
            audit.info("audit event")

            audit_file = Path(tmpdir) / "audit.log"
            assert audit_file.exists()
            content = audit_file.read_text()
            assert "audit event" in content


class TestStructuredOutput:

    def test_json_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            setup_logging(log_dir=tmpdir, log_level="INFO", environment="prod")
            logger = get_logger("json_test")
            logger.info("hello structured world")

            log_file = Path(tmpdir) / "app.log"
            content = log_file.read_text().strip()
            lines = [line for line in content.split("\n") if line.strip()]

            found_valid = False
            for line in lines:
                try:
                    obj = json.loads(line)
                    if obj.get("event") == "hello structured world":
                        found_valid = True
                        assert "level" in obj
                        assert "timestamp" in obj
                    break
                except json.JSONDecodeError:
                    continue
            assert found_valid, f"No JSON log line found with expected event. Content: {lines[:3]}"

    def test_correlation_id_in_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            setup_logging(log_dir=tmpdir, log_level="INFO", environment="prod")
            set_correlation_id("req-999")
            logger = get_logger("cid_test")
            logger.info("check correlation")

            log_file = Path(tmpdir) / "app.log"
            content = log_file.read_text().strip()
            for line in content.split("\n"):
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    if obj.get("event") == "check correlation":
                        assert obj.get("correlation_id") == "req-999"
                        return
                except json.JSONDecodeError:
                    continue
            pytest.fail("No JSON log line with correlation_id found")

    def test_sensitive_data_redacted(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            setup_logging(log_dir=tmpdir, log_level="INFO", environment="prod")
            logger = get_logger("sens_test")
            logger.info("API Key: sk-abcdef1234567890abcdef1234567890")

            log_file = Path(tmpdir) / "app.log"
            content = log_file.read_text()
            assert "sk-***REDACTED***" in content
            assert "sk-abcdef1234567890abcdef1234567890" not in content


class TestResetLogging:

    def test_reset_clears_handlers(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            setup_logging(log_dir=tmpdir)
            assert len(logging.getLogger().handlers) > 0
            reset_logging()
            assert len(logging.getLogger().handlers) == 0
