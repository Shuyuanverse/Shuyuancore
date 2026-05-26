from __future__ import annotations

import pytest

from src.exceptions import (
    ApprovalError,
    ApprovalNotFoundError,
    ApprovalRequiredError,
    ConfigMissingError,
    ConfigPersistenceError,
    ConfigUpdateError,
    ConfigurationError,
    ConflictError,
    CronError,
    InvalidParameterError,
    MCPCommandNotFoundError,
    MCPConnectionError,
    MCPError,
    MCPToolNotFoundError,
    MemoryOperationError,
    MessageNotFoundError,
    MissingParameterError,
    ModelCallError,
    ModelError,
    ModelSwitchError,
    PermissionDeniedError,
    PersonaCompileError,
    PersonaError,
    ResourceNotFoundError,
    SessionArchivedError,
    SessionDeletedError,
    SessionError,
    SessionNotFoundError,
    ShuyuanCoreError,
    SkillError,
    SkillMarketError,
    SkillNotFoundError,
    ToolApprovalTimeoutError,
    ToolError,
    ToolExecutionError,
    ToolOperationDeniedError,
    ValidationError,
)


class TestShuyuanCoreError:
    def test_default_code_and_status(self) -> None:
        exc = ShuyuanCoreError()
        assert exc.code == 0
        assert exc.http_status == 500

    def test_default_message_bilingual(self) -> None:
        exc = ShuyuanCoreError()
        assert "内部错误" in exc.message
        assert "Internal" in exc.message

    def test_custom_message(self) -> None:
        exc = ShuyuanCoreError("自定义消息 / Custom message")
        assert exc.message == "自定义消息 / Custom message"

    def test_detail_field(self) -> None:
        exc = ShuyuanCoreError(detail={"field": "value"})
        assert exc.detail == {"field": "value"}

    def test_detail_defaults_to_none(self) -> None:
        exc = ShuyuanCoreError()
        assert exc.detail is None

    def test_to_dict_minimal(self) -> None:
        exc = ShuyuanCoreError()
        result = exc.to_dict()
        assert result["code"] == 0
        assert result["http_status"] == 500
        assert "message" in result
        assert "detail" not in result

    def test_to_dict_with_detail(self) -> None:
        exc = ShuyuanCoreError(detail="extra info")
        result = exc.to_dict()
        assert result["detail"] == "extra info"

    def test_str_returns_message(self) -> None:
        exc = ShuyuanCoreError("测试 / Test")
        assert str(exc) == "测试 / Test"

    def test_is_exception_instance(self) -> None:
        exc = ShuyuanCoreError()
        assert isinstance(exc, Exception)


ALL_EXCEPTIONS: list[tuple[type[ShuyuanCoreError], int, int]] = [
    (ShuyuanCoreError, 0, 500),
    (ValidationError, 1000, 400),
    (MissingParameterError, 1001, 400),
    (InvalidParameterError, 1002, 400),
    (ResourceNotFoundError, 1003, 404),
    (PermissionDeniedError, 1004, 403),
    (ConflictError, 1005, 409),
    (ModelError, 2000, 502),
    (ModelCallError, 2001, 502),
    (ModelSwitchError, 2002, 400),
    (MemoryOperationError, 3001, 500),
    (SkillError, 4000, 404),
    (SkillNotFoundError, 4001, 404),
    (SkillMarketError, 4002, 502),
    (PersonaError, 5000, 500),
    (PersonaCompileError, 5001, 500),
    (ToolError, 6000, 500),
    (ToolExecutionError, 6001, 500),
    (ToolApprovalTimeoutError, 6002, 408),
    (ToolOperationDeniedError, 6003, 403),
    (MCPError, 7000, 502),
    (MCPConnectionError, 7001, 502),
    (MCPToolNotFoundError, 7002, 404),
    (CronError, 8001, 400),
    (ApprovalError, 9000, 400),
    (ApprovalNotFoundError, 9001, 404),
    (ApprovalRequiredError, 9002, 202),
    (MCPCommandNotFoundError, 9003, 502),
    (SessionError, 10000, 404),
    (SessionNotFoundError, 10001, 404),
    (MessageNotFoundError, 10002, 404),
    (SessionArchivedError, 10003, 409),
    (SessionDeletedError, 10004, 409),
    (ConfigurationError, 11000, 500),
    (ConfigMissingError, 11000, 500),
    (ConfigUpdateError, 11001, 400),
    (ConfigPersistenceError, 11002, 500),
]


class TestAllExceptionCodes:
    @pytest.mark.parametrize("cls,expected_code,expected_status", ALL_EXCEPTIONS)
    def test_code_and_http_status(
        self,
        cls: type[ShuyuanCoreError],
        expected_code: int,
        expected_status: int,
    ) -> None:
        exc = cls()
        assert exc.code == expected_code, f"{cls.__name__}: code mismatch"
        assert exc.http_status == expected_status, f"{cls.__name__}: http_status mismatch"

    @pytest.mark.parametrize("cls,_,__", ALL_EXCEPTIONS)
    def test_message_is_bilingual(
        self, cls: type[ShuyuanCoreError], _: int, __: int
    ) -> None:
        exc = cls()
        has_chinese = any("\u4e00" <= c <= "\u9fff" for c in exc.message)
        has_ascii = any(c.isascii() and c.isalpha() for c in exc.message)
        assert has_chinese, f"{cls.__name__}: message should contain Chinese"
        assert has_ascii, f"{cls.__name__}: message should contain English"


class TestInheritance:
    def test_model_call_is_model_error(self) -> None:
        exc = ModelCallError()
        assert isinstance(exc, ModelError)
        assert isinstance(exc, ShuyuanCoreError)

    def test_missing_parameter_is_validation(self) -> None:
        exc = MissingParameterError()
        assert isinstance(exc, ValidationError)

    def test_skill_not_found_is_skill_error(self) -> None:
        exc = SkillNotFoundError()
        assert isinstance(exc, SkillError)

    def test_persona_compile_is_persona_error(self) -> None:
        exc = PersonaCompileError()
        assert isinstance(exc, PersonaError)

    def test_tool_execution_is_tool_error(self) -> None:
        exc = ToolExecutionError()
        assert isinstance(exc, ToolError)

    def test_tool_approval_timeout_is_tool_error(self) -> None:
        exc = ToolApprovalTimeoutError()
        assert isinstance(exc, ToolError)

    def test_tool_operation_denied_is_tool_error(self) -> None:
        exc = ToolOperationDeniedError()
        assert isinstance(exc, ToolError)

    def test_mcp_connection_is_mcp_error(self) -> None:
        exc = MCPConnectionError()
        assert isinstance(exc, MCPError)

    def test_approval_not_found_is_approval_error(self) -> None:
        exc = ApprovalNotFoundError()
        assert isinstance(exc, ApprovalError)

    def test_session_not_found_is_session_error(self) -> None:
        exc = SessionNotFoundError()
        assert isinstance(exc, SessionError)

    def test_config_missing_is_configuration_error(self) -> None:
        exc = ConfigMissingError()
        assert isinstance(exc, ConfigurationError)


class TestCatchByParent:
    def test_catch_model_call_by_model_error(self) -> None:
        try:
            raise ModelCallError()
        except ModelError:
            pass

    def test_catch_tool_execution_by_shuyuancore(self) -> None:
        try:
            raise ToolExecutionError()
        except ShuyuanCoreError:
            pass

    def test_catch_session_not_found_by_shuyuancore(self) -> None:
        try:
            raise SessionNotFoundError("会话 abc 不存在 / Session abc not found")
        except ShuyuanCoreError as e:
            assert e.code == 10001
            assert e.http_status == 404
            assert "abc" in e.message


class TestToDictAll:
    @pytest.mark.parametrize("cls,expected_code,expected_status", ALL_EXCEPTIONS)
    def test_to_dict_format(
        self,
        cls: type[ShuyuanCoreError],
        expected_code: int,
        expected_status: int,
    ) -> None:
        exc = cls()
        result = exc.to_dict()
        assert result["code"] == expected_code
        assert result["http_status"] == expected_status
        assert isinstance(result["message"], str)
        assert len(result["message"]) > 0


class TestCustomMessagePreservesCode:
    def test_custom_message_does_not_change_code(self) -> None:
        exc = SessionNotFoundError("自定义 / Custom")
        assert exc.code == 10001
        assert exc.http_status == 404
        assert exc.message == "自定义 / Custom"
