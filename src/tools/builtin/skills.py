from __future__ import annotations

import time
from typing import Any

from src.security.audit import get_audit_logger
from src.skills.interfaces import ISkillStore
from src.tools.interfaces import ITool, ToolParameter, ToolResult, ToolSpec


class SkillsTool(ITool):

    def __init__(self, store: ISkillStore | None = None) -> None:
        self._store = store

    def get_spec(self) -> ToolSpec:
        return ToolSpec(
            name="skills",
            description="技能管理工具，支持列出、获取、创建、更新、删除和执行技能。",
            category="skills",
            dangerous=False,
            parameters=[
                ToolParameter(
                    name="operation",
                    type="string",
                    description="操作类型：list/get/create/update/delete/execute",
                    required=True,
                ),
                ToolParameter(
                    name="name",
                    type="string",
                    description="技能名称，get/delete/execute 操作必填",
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="content",
                    type="string",
                    description="技能内容，create/update 操作使用",
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="conversation_id",
                    type="string",
                    description="对话 ID，create 操作必填",
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="params",
                    type="object",
                    description="额外参数，execute 操作时传递",
                    required=False,
                    default=None,
                ),
            ],
        )

    async def validate(self, params: dict[str, Any]) -> list[str]:
        errors: list[str] = []
        operation: str = params.get("operation", "")
        valid_operations = {"list", "get", "create", "update", "delete", "execute"}
        if operation not in valid_operations:
            errors.append(f"operation 必须是 {', '.join(sorted(valid_operations))}")
            return errors
        if operation in ("get", "delete", "execute"):
            name = params.get("name")
            if not name:
                errors.append(f"{operation} 操作必须提供 name 参数")
        if operation == "create":
            if not params.get("name"):
                errors.append("create 操作必须提供 name 参数")
            if not params.get("content"):
                errors.append("create 操作必须提供 content 参数")
            if not params.get("conversation_id"):
                errors.append("create 操作必须提供 conversation_id 参数")
        if operation == "update":
            if not params.get("name"):
                errors.append("update 操作必须提供 name 参数")
        if self._store is None:
            errors.append("技能存储（ISkillStore）未注入，技能功能不可用")
        return errors

    async def execute(
        self,
        params: dict[str, Any],
        user_id: str = "default",
    ) -> ToolResult:
        if self._store is None:
            return ToolResult(
                success=False,
                error="技能存储（ISkillStore）未注入，无法执行操作",
            )
        operation: str = params["operation"]
        start = time.time()
        audit = get_audit_logger()

        if operation == "list":
            return await self._list_skills(params, user_id, start, audit)
        elif operation == "get":
            return await self._get_skill(params, user_id, start, audit)
        elif operation == "create":
            return await self._create_skill(params, user_id, start, audit)
        elif operation == "update":
            return await self._update_skill(params, user_id, start, audit)
        elif operation == "delete":
            return await self._delete_skill(params, user_id, start, audit)
        elif operation == "execute":
            return await self._execute_skill(params, user_id, start, audit)
        else:
            return ToolResult(
                success=False,
                error=f"不支持的操作: {operation}",
                duration_ms=(time.time() - start) * 1000,
            )

    async def _list_skills(
        self,
        params: dict[str, Any],
        user_id: str,
        start: float,
        audit: Any,
    ) -> ToolResult:
        try:
            status: str = params.get("status", "active")
            skills: list[dict[str, Any]] = await self._store.list_skills(status=status)
            duration_ms = (time.time() - start) * 1000
            audit.log(
                user_id=user_id,
                action="skills.list",
                resource="skills",
                params=params,
                result="success",
                duration_ms=duration_ms,
            )
            return ToolResult(
                success=True,
                data={"skills": skills, "count": len(skills)},
                duration_ms=duration_ms,
            )
        except Exception as e:
            duration_ms = (time.time() - start) * 1000
            audit.log(
                user_id=user_id,
                action="skills.list",
                resource="skills",
                params=params,
                result="error",
                error=str(e),
                duration_ms=duration_ms,
            )
            return ToolResult(
                success=False,
                error=f"列出技能失败: {e}",
                duration_ms=duration_ms,
            )

    async def _get_skill(
        self,
        params: dict[str, Any],
        user_id: str,
        start: float,
        audit: Any,
    ) -> ToolResult:
        name: str = params["name"]
        try:
            skill: dict[str, Any] | None = await self._store.get_skill(name)
            duration_ms = (time.time() - start) * 1000
            if skill is None:
                audit.log(
                    user_id=user_id,
                    action="skills.get",
                    resource=f"skill:{name}",
                    params=params,
                    result="error",
                    error=f"技能 {name} 不存在",
                    duration_ms=duration_ms,
                )
                return ToolResult(
                    success=False,
                    error=f"技能 '{name}' 不存在",
                    duration_ms=duration_ms,
                )
            audit.log(
                user_id=user_id,
                action="skills.get",
                resource=f"skill:{name}",
                params=params,
                result="success",
                duration_ms=duration_ms,
            )
            return ToolResult(
                success=True,
                data=skill,
                duration_ms=duration_ms,
            )
        except Exception as e:
            duration_ms = (time.time() - start) * 1000
            audit.log(
                user_id=user_id,
                action="skills.get",
                resource=f"skill:{name}",
                params=params,
                result="error",
                error=str(e),
                duration_ms=duration_ms,
            )
            return ToolResult(
                success=False,
                error=f"获取技能 '{name}' 失败: {e}",
                duration_ms=duration_ms,
            )

    async def _create_skill(
        self,
        params: dict[str, Any],
        user_id: str,
        start: float,
        audit: Any,
    ) -> ToolResult:
        name: str = params["name"]
        content: str = params["content"]
        conversation_id: str = params["conversation_id"]
        try:
            existing: dict[str, Any] | None = await self._store.get_skill(name)
            if existing is not None:
                duration_ms = (time.time() - start) * 1000
                audit.log(
                    user_id=user_id,
                    action="skills.create",
                    resource=f"skill:{name}",
                    params=params,
                    result="error",
                    error=f"技能 {name} 已存在",
                    duration_ms=duration_ms,
                )
                return ToolResult(
                    success=False,
                    error=f"技能 '{name}' 已存在",
                    duration_ms=duration_ms,
                )
            skill_id: str = await self._store.create_skill(
                node={"name": name, "content": content},
                conversation_id=conversation_id,
            )
            duration_ms = (time.time() - start) * 1000
            audit.log(
                user_id=user_id,
                action="skills.create",
                resource=f"skill:{name}",
                params=params,
                result="success",
                duration_ms=duration_ms,
            )
            return ToolResult(
                success=True,
                data={"id": skill_id, "name": name},
                duration_ms=duration_ms,
            )
        except Exception as e:
            duration_ms = (time.time() - start) * 1000
            audit.log(
                user_id=user_id,
                action="skills.create",
                resource=f"skill:{name}",
                params=params,
                result="error",
                error=str(e),
                duration_ms=duration_ms,
            )
            return ToolResult(
                success=False,
                error=f"创建技能 '{name}' 失败: {e}",
                duration_ms=duration_ms,
            )

    async def _update_skill(
        self,
        params: dict[str, Any],
        user_id: str,
        start: float,
        audit: Any,
    ) -> ToolResult:
        name: str = params["name"]
        content: str | None = params.get("content")
        try:
            existing: dict[str, Any] | None = await self._store.get_skill(name)
            if existing is None:
                duration_ms = (time.time() - start) * 1000
                audit.log(
                    user_id=user_id,
                    action="skills.update",
                    resource=f"skill:{name}",
                    params=params,
                    result="error",
                    error=f"技能 {name} 不存在",
                    duration_ms=duration_ms,
                )
                return ToolResult(
                    success=False,
                    error=f"技能 '{name}' 不存在",
                    duration_ms=duration_ms,
                )
            node: dict[str, Any] = {"name": name}
            if content is not None:
                node["content"] = content
            await self._store.update_skill(node=node)
            duration_ms = (time.time() - start) * 1000
            audit.log(
                user_id=user_id,
                action="skills.update",
                resource=f"skill:{name}",
                params=params,
                result="success",
                duration_ms=duration_ms,
            )
            return ToolResult(
                success=True,
                data={"name": name},
                duration_ms=duration_ms,
            )
        except Exception as e:
            duration_ms = (time.time() - start) * 1000
            audit.log(
                user_id=user_id,
                action="skills.update",
                resource=f"skill:{name}",
                params=params,
                result="error",
                error=str(e),
                duration_ms=duration_ms,
            )
            return ToolResult(
                success=False,
                error=f"更新技能 '{name}' 失败: {e}",
                duration_ms=duration_ms,
            )

    async def _delete_skill(
        self,
        params: dict[str, Any],
        user_id: str,
        start: float,
        audit: Any,
    ) -> ToolResult:
        name: str = params["name"]
        try:
            existing: dict[str, Any] | None = await self._store.get_skill(name)
            if existing is None:
                duration_ms = (time.time() - start) * 1000
                audit.log(
                    user_id=user_id,
                    action="skills.delete",
                    resource=f"skill:{name}",
                    params=params,
                    result="error",
                    error=f"技能 {name} 不存在",
                    duration_ms=duration_ms,
                )
                return ToolResult(
                    success=False,
                    error=f"技能 '{name}' 不存在",
                    duration_ms=duration_ms,
                )
            await self._store.delete_skill(name)
            duration_ms = (time.time() - start) * 1000
            audit.log(
                user_id=user_id,
                action="skills.delete",
                resource=f"skill:{name}",
                params=params,
                result="success",
                duration_ms=duration_ms,
            )
            return ToolResult(
                success=True,
                data={"name": name, "deleted": True},
                duration_ms=duration_ms,
            )
        except Exception as e:
            duration_ms = (time.time() - start) * 1000
            audit.log(
                user_id=user_id,
                action="skills.delete",
                resource=f"skill:{name}",
                params=params,
                result="error",
                error=str(e),
                duration_ms=duration_ms,
            )
            return ToolResult(
                success=False,
                error=f"删除技能 '{name}' 失败: {e}",
                duration_ms=duration_ms,
            )

    async def _execute_skill(
        self,
        params: dict[str, Any],
        user_id: str,
        start: float,
        audit: Any,
    ) -> ToolResult:
        name: str = params["name"]
        extra_params: dict[str, Any] | None = params.get("params")
        try:
            skill: dict[str, Any] | None = await self._store.get_skill(name)
            if skill is None:
                duration_ms = (time.time() - start) * 1000
                audit.log(
                    user_id=user_id,
                    action="skills.execute",
                    resource=f"skill:{name}",
                    params=params,
                    result="error",
                    error=f"技能 {name} 不存在",
                    duration_ms=duration_ms,
                )
                return ToolResult(
                    success=False,
                    error=f"技能 '{name}' 不存在",
                    duration_ms=duration_ms,
                )
            content: str = skill.get("content", "")
            if not content:
                duration_ms = (time.time() - start) * 1000
                audit.log(
                    user_id=user_id,
                    action="skills.execute",
                    resource=f"skill:{name}",
                    params=params,
                    result="error",
                    error=f"技能 {name} 内容为空",
                    duration_ms=duration_ms,
                )
                return ToolResult(
                    success=False,
                    error=f"技能 '{name}' 内容为空",
                    duration_ms=duration_ms,
                )
            duration_ms = (time.time() - start) * 1000
            audit.log(
                user_id=user_id,
                action="skills.execute",
                resource=f"skill:{name}",
                params=params,
                result="success",
                duration_ms=duration_ms,
            )
            return ToolResult(
                success=True,
                data={
                    "name": name,
                    "content": content,
                    "params": extra_params,
                },
                duration_ms=duration_ms,
            )
        except Exception as e:
            duration_ms = (time.time() - start) * 1000
            audit.log(
                user_id=user_id,
                action="skills.execute",
                resource=f"skill:{name}",
                params=params,
                result="error",
                error=str(e),
                duration_ms=duration_ms,
            )
            return ToolResult(
                success=False,
                error=f"执行技能 '{name}' 失败: {e}",
                duration_ms=duration_ms,
            )