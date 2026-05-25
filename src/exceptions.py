from __future__ import annotations

from typing import Any


class ShuyuanCoreError(Exception):
    code: int = 0
    http_status: int = 500
    default_message: str = "内部错误 / Internal error"

    def __init__(self, message: str | None = None, detail: Any = None) -> None:
        self.message: str = message or self.default_message
        self.detail: Any = detail
        super().__init__(self.message)

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "code": self.code,
            "message": self.message,
            "http_status": self.http_status,
        }
        if self.detail is not None:
            result["detail"] = self.detail
        return result


class ValidationError(ShuyuanCoreError):
    code: int = 1000
    http_status: int = 400
    default_message: str = "参数校验失败 / Validation error"


class MissingParameterError(ValidationError):
    code: int = 1001
    http_status: int = 400
    default_message: str = "缺少必填参数 / Missing required parameter"


class InvalidParameterError(ValidationError):
    code: int = 1002
    http_status: int = 400
    default_message: str = "参数格式错误 / Invalid parameter format"


class ResourceNotFoundError(ShuyuanCoreError):
    code: int = 1003
    http_status: int = 404
    default_message: str = "资源不存在 / Resource not found"


class PermissionDeniedError(ShuyuanCoreError):
    code: int = 1004
    http_status: int = 403
    default_message: str = "权限不足 / Permission denied"


class ConflictError(ShuyuanCoreError):
    code: int = 1005
    http_status: int = 409
    default_message: str = "幂等键重复 / Idempotency key conflict"


class ModelError(ShuyuanCoreError):
    code: int = 2000
    http_status: int = 502
    default_message: str = "模型操作失败 / Model operation failed"


class ModelCallError(ModelError):
    code: int = 2001
    http_status: int = 502
    default_message: str = (
        "LLM API 调用失败（超时或服务端错误）"
        " / LLM API call failed (timeout or server error)"
    )


class ModelSwitchError(ModelError):
    code: int = 2002
    http_status: int = 400
    default_message: str = (
        "模型切换失败（目标模型不存在或未配置）"
        " / Model switch failed (target not found or not configured)"
    )


class MemoryOperationError(ShuyuanCoreError):
    code: int = 3001
    http_status: int = 500
    default_message: str = (
        "记忆操作失败（SQLite 或 ChromaDB 写入失败）"
        " / Memory operation failed (SQLite or ChromaDB write failure)"
    )


class SkillError(ShuyuanCoreError):
    code: int = 4000
    http_status: int = 404
    default_message: str = "技能操作失败 / Skill operation failed"


class SkillNotFoundError(SkillError):
    code: int = 4001
    http_status: int = 404
    default_message: str = "技能不存在 / Skill not found"


class SkillMarketError(SkillError):
    code: int = 4002
    http_status: int = 502
    default_message: str = "技能市场连接失败 / Skill marketplace connection failed"


class PersonaError(ShuyuanCoreError):
    code: int = 5000
    http_status: int = 500
    default_message: str = "人格操作失败 / Persona operation failed"


class PersonaCompileError(PersonaError):
    code: int = 5001
    http_status: int = 500
    default_message: str = (
        "人格编译失败（输入材料不足或格式错误）"
        " / Persona compilation failed (insufficient input or invalid format)"
    )


class ToolError(ShuyuanCoreError):
    code: int = 6000
    http_status: int = 500
    default_message: str = "工具执行失败 / Tool execution failed"


class ToolExecutionError(ToolError):
    code: int = 6001
    http_status: int = 500
    default_message: str = (
        "工具执行失败（命令返回非零退出码）"
        " / Tool execution failed (non-zero exit code)"
    )


class ToolApprovalTimeoutError(ToolError):
    code: int = 6002
    http_status: int = 408
    default_message: str = (
        "工具审批超时（15 分钟内未审批）"
        " / Tool approval timeout (not approved within 15 minutes)"
    )


class ToolOperationDeniedError(ToolError):
    code: int = 6003
    http_status: int = 403
    default_message: str = "工具危险操作被拒绝 / Dangerous tool operation denied"


class MCPError(ShuyuanCoreError):
    code: int = 7000
    http_status: int = 502
    default_message: str = "MCP 操作失败 / MCP operation failed"


class MCPConnectionError(MCPError):
    code: int = 7001
    http_status: int = 502
    default_message: str = "MCP 服务器连接失败 / MCP server connection failed"


class MCPToolNotFoundError(MCPError):
    code: int = 7002
    http_status: int = 404
    default_message: str = "MCP 工具未注册 / MCP tool not registered"


class CronError(ShuyuanCoreError):
    code: int = 8001
    http_status: int = 400
    default_message: str = (
        "定时任务创建失败（cron 表达式无效）"
        " / Cron job creation failed (invalid cron expression)"
    )


class ApprovalError(ShuyuanCoreError):
    code: int = 9000
    http_status: int = 400
    default_message: str = "审批操作失败 / Approval operation failed"


class ApprovalNotFoundError(ApprovalError):
    code: int = 9001
    http_status: int = 404
    default_message: str = "审批不存在 / Approval not found"


class ApprovalRequiredError(ApprovalError):
    code: int = 9002
    http_status: int = 202
    default_message: str = "危险操作需审批 / Dangerous operation requires approval"


class MCPCommandNotFoundError(ApprovalError):
    code: int = 9003
    http_status: int = 502
    default_message: str = (
        "MCP 服务器 stdio 命令不存在 / MCP server stdio command not found"
    )


class SessionError(ShuyuanCoreError):
    code: int = 10000
    http_status: int = 404
    default_message: str = "会话操作失败 / Session operation failed"


class SessionNotFoundError(SessionError):
    code: int = 10001
    http_status: int = 404
    default_message: str = "会话不存在 / Session not found"


class MessageNotFoundError(SessionError):
    code: int = 10002
    http_status: int = 404
    default_message: str = "消息不存在 / Message not found"


class SessionArchivedError(SessionError):
    code: int = 10003
    http_status: int = 409
    default_message: str = (
        "会话已归档（无法发送消息） / Session archived (cannot send messages)"
    )


class SessionDeletedError(SessionError):
    code: int = 10004
    http_status: int = 409
    default_message: str = "会话已删除（无法操作） / Session deleted (cannot operate)"


class ConfigurationError(ShuyuanCoreError):
    code: int = 11000
    http_status: int = 500
    default_message: str = "配置错误 / Configuration error"


class ConfigMissingError(ConfigurationError):
    code: int = 11000
    http_status: int = 500
    default_message: str = (
        "配置文件不存在或解析失败 / Config file missing or parse failure"
    )


class ConfigUpdateError(ConfigurationError):
    code: int = 11001
    http_status: int = 400
    default_message: str = (
        "配置更新失败（运行时配置验证失败）"
        " / Config update failed (runtime validation failure)"
    )


class ConfigPersistenceError(ConfigurationError):
    code: int = 11002
    http_status: int = 500
    default_message: str = (
        "配置持久化失败（写入 default.yaml 失败）"
        " / Config persistence failed (write to default.yaml failed)"
    )


__all__ = [
    "ShuyuanCoreError",
    "ValidationError",
    "MissingParameterError",
    "InvalidParameterError",
    "ResourceNotFoundError",
    "PermissionDeniedError",
    "ConflictError",
    "ModelError",
    "ModelCallError",
    "ModelSwitchError",
    "MemoryOperationError",
    "SkillError",
    "SkillNotFoundError",
    "SkillMarketError",
    "PersonaError",
    "PersonaCompileError",
    "ToolError",
    "ToolExecutionError",
    "ToolApprovalTimeoutError",
    "ToolOperationDeniedError",
    "MCPError",
    "MCPConnectionError",
    "MCPToolNotFoundError",
    "CronError",
    "ApprovalError",
    "ApprovalNotFoundError",
    "ApprovalRequiredError",
    "MCPCommandNotFoundError",
    "SessionError",
    "SessionNotFoundError",
    "MessageNotFoundError",
    "SessionArchivedError",
    "SessionDeletedError",
    "ConfigurationError",
    "ConfigMissingError",
    "ConfigUpdateError",
    "ConfigPersistenceError",
]
