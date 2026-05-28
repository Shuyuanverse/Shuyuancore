from __future__ import annotations

import logging
import logging.config
import logging.handlers
import re
import sys
from contextvars import ContextVar
from pathlib import Path
from typing import Any, MutableMapping

import structlog

try:
    import colorlog
    HAS_COLORLOG = True
except ImportError:
    HAS_COLORLOG = False

from src.config import get_settings

_SIZE_UNITS: dict[str, int] = {"GB": 1024**3, "MB": 1024**2, "KB": 1024, "B": 1}
_PLAIN_FORMAT: str = "%(asctime)s [%(levelname)s] %(name)s [%(correlation_id)s] %(message)s"

_correlation_id_ctx: ContextVar[str | None] = ContextVar("correlation_id", default=None)

_SENSITIVE_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"sk-[a-zA-Z0-9]{32,}"), "sk-***REDACTED***"),
    (re.compile(r"Bearer [a-zA-Z0-9._\-]{20,}"), "Bearer ***REDACTED***"),
    (re.compile(r"api_key[=:]\s*\S+", re.IGNORECASE), "api_key=***REDACTED***"),
    (re.compile(r"password[=:]\s*\S+", re.IGNORECASE), "password=***REDACTED***"),
    (re.compile(r"token[=:]\s*\S+", re.IGNORECASE), "token=***REDACTED***"),
    (re.compile(r"DASHSCOPE_API_KEY[=:]\s*\S+", re.IGNORECASE), "DASHSCOPE_API_KEY=***REDACTED***"),
    (re.compile(r"DEEPSEEK_API_KEY[=:]\s*\S+", re.IGNORECASE), "DEEPSEEK_API_KEY=***REDACTED***"),
    (re.compile(r"OPENAI_API_KEY[=:]\s*\S+", re.IGNORECASE), "OPENAI_API_KEY=***REDACTED***"),
]

_SETUP_DONE: bool = False


def _parse_size(size_str: str) -> int:
    size_str = size_str.strip().upper()
    for unit, multiplier in _SIZE_UNITS.items():
        if size_str.endswith(unit):
            num_part = size_str[: -len(unit)].strip()
            try:
                return int(float(num_part) * multiplier)
            except ValueError:
                break
    return int(size_str) if size_str.isdigit() else 10 * 1024 * 1024


class CorrelationIdFilter(logging.Filter):

    def filter(self, record: logging.LogRecord) -> bool:
        cid = _correlation_id_ctx.get()
        record.correlation_id = cid or "-"
        return True


class SensitiveDataFilter(logging.Filter):

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        for pattern, replacement in _SENSITIVE_PATTERNS:
            msg = pattern.sub(replacement, msg)
        record.msg = msg
        record.args = ()
        return True


def _extra_processors() -> list[structlog.typing.Processor]:
    return [
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer() if _is_dev() else structlog.processors.JSONRenderer(),
    ]


def _is_dev() -> bool:
    return True


def _timestamper_processor(
    logger: Any,
    method_name: str,
    event_dict: MutableMapping[str, Any],
) -> MutableMapping[str, Any]:
    from datetime import datetime, timezone
    event_dict["timestamp"] = datetime.now(timezone.utc).isoformat()
    return event_dict


def _add_correlation_id(
    logger: Any,
    method_name: str,
    event_dict: MutableMapping[str, Any],
) -> MutableMapping[str, Any]:
    cid = _correlation_id_ctx.get()
    if cid:
        event_dict["correlation_id"] = cid
    return event_dict


def _drop_empty_frames(
    logger: Any,
    method_name: str,
    event_dict: MutableMapping[str, Any],
) -> MutableMapping[str, Any]:
    event_dict.pop("stack_info", None)
    event_dict.pop("exc_info", None)
    return event_dict


def setup_logging(
    settings: Any | None = None,
    log_dir: str | None = None,
    log_level: str | None = None,
    environment: str | None = None,
) -> None:
    global _SETUP_DONE
    if _SETUP_DONE:
        return
    _SETUP_DONE = True

    if settings is None:
        try:
            settings = get_settings()
        except Exception:
            settings = None

    cfg = settings.deploy if settings else None
    env = environment or "dev"
    level = log_level or (cfg.log_level.upper() if cfg else "DEBUG")
    log_path = log_dir or "data/logs"
    max_size = (
        _parse_size(cfg.log_rotation.max_size)
        if cfg and hasattr(cfg, "log_rotation")
        else 10 * 1024 * 1024
    )
    backup_count = (
        cfg.log_rotation.backup_count
        if cfg and hasattr(cfg, "log_rotation")
        else 5
    )

    log_dir_path = Path(log_path)
    log_dir_path.mkdir(parents=True, exist_ok=True)

    shared_processors: list[structlog.typing.Processor] = [
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        _timestamper_processor,
        _add_correlation_id,
        structlog.processors.UnicodeDecoder(),
    ]

    structlog.configure(
        processors=shared_processors
        + [
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    foreign_pre_chain: list[structlog.typing.Processor] = [
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        _timestamper_processor,
        _add_correlation_id,
    ]

    if env == "dev":
        json_formatter = structlog.stdlib.ProcessorFormatter(
            foreign_pre_chain=foreign_pre_chain,
            processors=[
                _drop_empty_frames,
                structlog.processors.JSONRenderer(),
            ],
        )
    else:
        json_formatter = structlog.stdlib.ProcessorFormatter(
            foreign_pre_chain=foreign_pre_chain,
            processors=[
                _drop_empty_frames,
                structlog.processors.JSONRenderer(),
            ],
        )

    file_handler = logging.handlers.RotatingFileHandler(
        filename=str(log_dir_path / "app.log"),
        maxBytes=max_size,
        backupCount=backup_count,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(json_formatter)
    file_handler.addFilter(CorrelationIdFilter())
    file_handler.addFilter(SensitiveDataFilter())

    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    root_logger.handlers.clear()
    root_logger.addHandler(file_handler)

    if env == "dev" and HAS_COLORLOG:
        console_formatter = colorlog.ColoredFormatter(
            "%(asctime)s %(log_color)s[%(levelname)-7s]%(reset)s "
            "%(name)-25s [%(correlation_id)s] "
            "%(log_color)s%(message)s%(reset)s",
            datefmt="%H:%M:%S",
            log_colors={
                "DEBUG": "cyan",
                "INFO": "green",
                "WARNING": "yellow",
                "ERROR": "red",
                "CRITICAL": "red,bg_white",
            },
        )
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.DEBUG)
        console_handler.setFormatter(console_formatter)
        console_handler.addFilter(CorrelationIdFilter())
        console_handler.addFilter(SensitiveDataFilter())
        root_logger.addHandler(console_handler)
    elif env == "dev":
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.DEBUG)
        console_handler.setFormatter(json_formatter)
        console_handler.addFilter(CorrelationIdFilter())
        console_handler.addFilter(SensitiveDataFilter())
        root_logger.addHandler(console_handler)
    else:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.WARNING)
        console_handler.setFormatter(json_formatter)
        console_handler.addFilter(CorrelationIdFilter())
        console_handler.addFilter(SensitiveDataFilter())
        root_logger.addHandler(console_handler)

    _setup_audit_logger(str(log_dir_path), max_size, backup_count)


def _setup_audit_logger(
    log_dir: str,
    max_bytes: int,
    backup_count: int,
) -> None:
    audit_logger = logging.getLogger("shuyuancore.audit")
    audit_logger.setLevel(logging.INFO)
    audit_logger.propagate = False
    audit_handler = logging.handlers.RotatingFileHandler(
        filename=f"{log_dir}/audit.log",
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    audit_handler.setLevel(logging.INFO)
    audit_handler.setFormatter(logging.Formatter("%(asctime)s [AUDIT] %(message)s"))
    audit_logger.handlers.clear()
    audit_logger.addHandler(audit_handler)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def get_audit_logger() -> logging.Logger:
    return logging.getLogger("shuyuancore.audit")


def set_correlation_id(cid: str | None) -> None:
    _correlation_id_ctx.set(cid)


def get_correlation_id() -> str | None:
    return _correlation_id_ctx.get()


def _reset_correlation_id() -> None:
    _correlation_id_ctx.set(None)


def reset_logging() -> None:
    global _SETUP_DONE
    _SETUP_DONE = False
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(logging.DEBUG)
    audit_logger = logging.getLogger("shuyuancore.audit")
    audit_logger.handlers.clear()
    audit_logger.propagate = True
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
