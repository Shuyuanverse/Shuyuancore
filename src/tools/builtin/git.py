from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any

from src.security.approval import get_approval_manager
from src.security.audit import get_audit_logger
from src.tools.interfaces import ITool, ToolParameter, ToolResult, ToolSpec

logger = logging.getLogger(__name__)


class _SubprocessResult:
    """Lightweight result holder for async subprocess execution."""

    def __init__(
        self,
        returncode: int,
        stdout: str,
        stderr: str,
    ) -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


async def _run_subprocess(
    cmd: list[str],
    *,
    cwd: str = ".",
    timeout: int = 60,
    env: dict[str, str] | None = None,
) -> _SubprocessResult:
    """Execute a subprocess asynchronously.

    Args:
        cmd: Command and arguments as a list of strings.
        cwd: Working directory for the command.
        timeout: Maximum execution time in seconds.
        env: Optional environment variables (defaults to current env).

    Returns:
        A _SubprocessResult with returncode, stdout, and stderr.

    Raises:
        asyncio.TimeoutError: If execution exceeds the timeout.
        FileNotFoundError: If the command executable is not found.
    """
    process = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=cwd,
        env=env or os.environ.copy(),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    try:
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            process.communicate(), timeout=timeout
        )
    except asyncio.TimeoutError:
        process.kill()
        await process.wait()
        raise

    return _SubprocessResult(
        returncode=process.returncode or 0,
        stdout=stdout_bytes.decode("utf-8", errors="replace"),
        stderr=stderr_bytes.decode("utf-8", errors="replace"),
    )


class GitTool(ITool):
    def get_spec(self) -> ToolSpec:
        return ToolSpec(
            name="git",
            description="Git operations tool. Supports clone, commit, push, "
            "status, diff, log, and create_pr.",
            category="office",
            dangerous=False,
            parameters=[
                ToolParameter(
                    name="action",
                    type="string",
                    description="Operation: clone/commit/push/status/diff/log/create_pr",
                    required=True,
                ),
                ToolParameter(
                    name="repo_path",
                    type="string",
                    description="Path to the git repository",
                    required=False,
                    default=".",
                ),
                ToolParameter(
                    name="message",
                    type="string",
                    description="Commit message, required for commit",
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="branch",
                    type="string",
                    description="Branch name",
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="url",
                    type="string",
                    description="Remote URL, required for clone",
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="pr_title",
                    type="string",
                    description="Pull request title, required for create_pr",
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="pr_body",
                    type="string",
                    description="Pull request body",
                    required=False,
                    default=None,
                ),
            ],
        )

    async def validate(self, params: dict[str, Any]) -> list[str]:
        errors: list[str] = []
        action: str = params.get("action", "")
        valid_actions = {
            "clone",
            "commit",
            "push",
            "status",
            "diff",
            "log",
            "create_pr",
        }
        if action not in valid_actions:
            errors.append(f"action must be one of: {', '.join(sorted(valid_actions))}")
            return errors
        if action == "commit" and not params.get("message"):
            errors.append("commit operation requires message parameter")
        if action == "clone" and not params.get("url"):
            errors.append("clone operation requires url parameter")
        if action == "create_pr":
            if not params.get("pr_title"):
                errors.append("create_pr operation requires pr_title parameter")
        return errors

    async def execute(
        self,
        params: dict[str, Any],
        user_id: str = "default",
    ) -> ToolResult:
        action: str = params["action"]
        start = time.time()
        audit = get_audit_logger()

        repo_path: str = params.get("repo_path", ".")

        if action == "clone":
            return await self._clone(
                params,
                repo_path,
                user_id,
                start,
                audit,
            )
        elif action == "commit":
            return await self._commit(
                params,
                repo_path,
                user_id,
                start,
                audit,
            )
        elif action == "push":
            return await self._push(
                params,
                repo_path,
                user_id,
                start,
                audit,
            )
        elif action == "status":
            return await self._run_git(
                ["status"],
                repo_path,
                "git.status",
                user_id,
                start,
                audit,
            )
        elif action == "diff":
            return await self._run_git(
                ["diff"],
                repo_path,
                "git.diff",
                user_id,
                start,
                audit,
            )
        elif action == "log":
            return await self._run_git(
                ["log", "--oneline", "-n", "20"],
                repo_path,
                "git.log",
                user_id,
                start,
                audit,
            )
        else:
            return await self._create_pr(
                params,
                repo_path,
                user_id,
                start,
                audit,
            )

    async def _run_git(
        self,
        args: list[str],
        repo_path: str,
        action_name: str,
        user_id: str,
        start: float,
        audit: Any,
    ) -> ToolResult:
        try:
            cmd = ["git"] + args
            result = await _run_subprocess(
                cmd,
                cwd=repo_path,
                timeout=60,
            )
            duration_ms = (time.time() - start) * 1000
            if result.returncode == 0:
                audit.log(
                    user_id=user_id,
                    action=action_name,
                    resource=repo_path,
                    params={"args": args},
                    result="success",
                    duration_ms=duration_ms,
                )
                return ToolResult(
                    success=True,
                    data={
                        "stdout": result.stdout,
                        "returncode": 0,
                    },
                    duration_ms=duration_ms,
                )
            else:
                audit.log(
                    user_id=user_id,
                    action=action_name,
                    resource=repo_path,
                    params={"args": args},
                    result="error",
                    error=result.stderr,
                    duration_ms=duration_ms,
                )
                return ToolResult(
                    success=False,
                    error=result.stderr,
                    duration_ms=duration_ms,
                )
        except asyncio.TimeoutError:
            return ToolResult(
                success=False,
                error="Git command timed out after 60 seconds",
                duration_ms=(time.time() - start) * 1000,
            )
        except FileNotFoundError:
            return ToolResult(
                success=False,
                error="git command not found. Please install git.",
                duration_ms=(time.time() - start) * 1000,
            )
        except OSError as e:
            return ToolResult(
                success=False,
                error=str(e),
                duration_ms=(time.time() - start) * 1000,
            )

    async def _clone(
        self,
        params: dict[str, Any],
        repo_path: str,
        user_id: str,
        start: float,
        audit: Any,
    ) -> ToolResult:
        url: str = params["url"]
        target_dir: str = params.get("branch", "")

        cmd = ["git", "clone", url]
        if target_dir:
            cmd.append(target_dir)

        try:
            result = await _run_subprocess(
                cmd,
                cwd=repo_path,
                timeout=300,
            )
            duration_ms = (time.time() - start) * 1000
            if result.returncode == 0:
                audit.log(
                    user_id=user_id,
                    action="git.clone",
                    resource=url,
                    params={"target_dir": target_dir or repo_path},
                    result="success",
                    duration_ms=duration_ms,
                )
                return ToolResult(
                    success=True,
                    data={
                        "stdout": result.stdout,
                        "url": url,
                    },
                    duration_ms=duration_ms,
                )
            else:
                audit.log(
                    user_id=user_id,
                    action="git.clone",
                    resource=url,
                    params={},
                    result="error",
                    error=result.stderr,
                    duration_ms=duration_ms,
                )
                return ToolResult(
                    success=False,
                    error=result.stderr,
                    duration_ms=duration_ms,
                )
        except asyncio.TimeoutError:
            return ToolResult(
                success=False,
                error="Git clone timed out after 300 seconds",
                duration_ms=(time.time() - start) * 1000,
            )
        except (FileNotFoundError, OSError) as e:
            return ToolResult(
                success=False,
                error=str(e),
                duration_ms=(time.time() - start) * 1000,
            )

    async def _commit(
        self,
        params: dict[str, Any],
        repo_path: str,
        user_id: str,
        start: float,
        audit: Any,
    ) -> ToolResult:
        message: str = params["message"]

        try:
            add_result = await _run_subprocess(
                ["git", "add", "."],
                cwd=repo_path,
                timeout=60,
            )
            if add_result.returncode != 0:
                return ToolResult(
                    success=False,
                    error=f"git add failed: {add_result.stderr}",
                    duration_ms=(time.time() - start) * 1000,
                )

            commit_result = await _run_subprocess(
                ["git", "commit", "-m", message],
                cwd=repo_path,
                timeout=60,
            )
            duration_ms = (time.time() - start) * 1000
            if commit_result.returncode == 0:
                audit.log(
                    user_id=user_id,
                    action="git.commit",
                    resource=repo_path,
                    params={"message": message[:100]},
                    result="success",
                    duration_ms=duration_ms,
                )
                return ToolResult(
                    success=True,
                    data={
                        "stdout": commit_result.stdout,
                        "message": message,
                    },
                    duration_ms=duration_ms,
                )
            else:
                audit.log(
                    user_id=user_id,
                    action="git.commit",
                    resource=repo_path,
                    params={"message": message[:100]},
                    result="error",
                    error=commit_result.stderr,
                    duration_ms=duration_ms,
                )
                return ToolResult(
                    success=False,
                    error=commit_result.stderr,
                    duration_ms=duration_ms,
                )
        except asyncio.TimeoutError:
            return ToolResult(
                success=False,
                error="Git commit timed out after 60 seconds",
                duration_ms=(time.time() - start) * 1000,
            )
        except (FileNotFoundError, OSError) as e:
            return ToolResult(
                success=False,
                error=str(e),
                duration_ms=(time.time() - start) * 1000,
            )

    async def _push(
        self,
        params: dict[str, Any],
        repo_path: str,
        user_id: str,
        start: float,
        audit: Any,
    ) -> ToolResult:
        approval_mgr = await get_approval_manager()
        req = await approval_mgr.request(
            tool_name="git",
            params=params,
            user_id=user_id,
            timeout=300,
        )
        approved = await approval_mgr.wait(req.approval_id, timeout=300)
        if not approved:
            audit.log(
                user_id=user_id,
                action="git.push",
                resource=repo_path,
                params={"action": "push"},
                result="rejected",
                duration_ms=(time.time() - start) * 1000,
            )
            return ToolResult(
                success=False,
                error="Git push was not approved",
                duration_ms=(time.time() - start) * 1000,
                approval_id=req.approval_id,
            )

        branch: str | None = params.get("branch")
        cmd = ["git", "push"]
        if branch:
            cmd.extend(["origin", branch])

        try:
            result = await _run_subprocess(
                cmd,
                cwd=repo_path,
                timeout=120,
            )
            duration_ms = (time.time() - start) * 1000
            if result.returncode == 0:
                audit.log(
                    user_id=user_id,
                    action="git.push",
                    resource=repo_path,
                    params={"branch": branch or "current"},
                    result="success",
                    duration_ms=duration_ms,
                )
                return ToolResult(
                    success=True,
                    data={"stdout": result.stdout},
                    duration_ms=duration_ms,
                )
            else:
                audit.log(
                    user_id=user_id,
                    action="git.push",
                    resource=repo_path,
                    params={"branch": branch or "current"},
                    result="error",
                    error=result.stderr,
                    duration_ms=duration_ms,
                )
                return ToolResult(
                    success=False,
                    error=result.stderr,
                    duration_ms=duration_ms,
                )
        except asyncio.TimeoutError:
            return ToolResult(
                success=False,
                error="Git push timed out after 120 seconds",
                duration_ms=(time.time() - start) * 1000,
            )
        except (FileNotFoundError, OSError) as e:
            return ToolResult(
                success=False,
                error=str(e),
                duration_ms=(time.time() - start) * 1000,
            )

    async def _create_pr(
        self,
        params: dict[str, Any],
        repo_path: str,
        user_id: str,
        start: float,
        audit: Any,
    ) -> ToolResult:
        approval_mgr = await get_approval_manager()
        req = await approval_mgr.request(
            tool_name="git",
            params=params,
            user_id=user_id,
            timeout=300,
        )
        approved = await approval_mgr.wait(req.approval_id, timeout=300)
        if not approved:
            audit.log(
                user_id=user_id,
                action="git.create_pr",
                resource=repo_path,
                params={"pr_title": params.get("pr_title")},
                result="rejected",
                duration_ms=(time.time() - start) * 1000,
            )
            return ToolResult(
                success=False,
                error="PR creation was not approved",
                duration_ms=(time.time() - start) * 1000,
                approval_id=req.approval_id,
            )

        pr_title: str = params["pr_title"]
        pr_body: str = params.get("pr_body", "")

        token = os.environ.get("GITHUB_TOKEN", "")
        env = os.environ.copy()
        if token:
            env["GH_TOKEN"] = token

        try:
            if await self._has_gh_cli():
                cmd = [
                    "gh",
                    "pr",
                    "create",
                    "--title",
                    pr_title,
                    "--body",
                    pr_body,
                ]
                branch: str | None = params.get("branch")
                if branch:
                    cmd.extend(["--base", branch])
                result = await _run_subprocess(
                    cmd,
                    cwd=repo_path,
                    timeout=120,
                    env=env,
                )
            else:
                remote_url = await self._get_remote_url(repo_path)

                pr_data = (
                    f"PR: {pr_title}\n\n{pr_body}\n\n"
                    f"Remote: {remote_url}\n"
                    f"To create this PR manually, push your branch and "
                    f"visit the repository on GitHub."
                )
                duration_ms = (time.time() - start) * 1000
                audit.log(
                    user_id=user_id,
                    action="git.create_pr",
                    resource=repo_path,
                    params={"pr_title": pr_title},
                    result="partial",
                    duration_ms=duration_ms,
                )
                return ToolResult(
                    success=True,
                    data={
                        "message": pr_data,
                        "note": "gh CLI not available. PR info returned as text.",
                    },
                    duration_ms=duration_ms,
                )

            duration_ms = (time.time() - start) * 1000
            if result.returncode == 0:
                audit.log(
                    user_id=user_id,
                    action="git.create_pr",
                    resource=repo_path,
                    params={"pr_title": pr_title},
                    result="success",
                    duration_ms=duration_ms,
                )
                return ToolResult(
                    success=True,
                    data={
                        "stdout": result.stdout,
                        "pr_url": result.stdout.strip(),
                    },
                    duration_ms=duration_ms,
                )
            else:
                audit.log(
                    user_id=user_id,
                    action="git.create_pr",
                    resource=repo_path,
                    params={"pr_title": pr_title},
                    result="error",
                    error=result.stderr,
                    duration_ms=duration_ms,
                )
                return ToolResult(
                    success=False,
                    error=result.stderr,
                    duration_ms=duration_ms,
                )
        except asyncio.TimeoutError:
            return ToolResult(
                success=False,
                error="PR creation timed out after 120 seconds",
                duration_ms=(time.time() - start) * 1000,
            )
        except (FileNotFoundError, OSError) as e:
            return ToolResult(
                success=False,
                error=str(e),
                duration_ms=(time.time() - start) * 1000,
            )

    @staticmethod
    async def _has_gh_cli() -> bool:
        try:
            result = await _run_subprocess(
                ["gh", "--version"],
                timeout=10,
            )
            return result.returncode == 0
        except (FileNotFoundError, asyncio.TimeoutError, OSError):
            return False

    @staticmethod
    async def _get_remote_url(repo_path: str) -> str:
        try:
            result = await _run_subprocess(
                ["git", "remote", "get-url", "origin"],
                cwd=repo_path,
                timeout=30,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except (asyncio.TimeoutError, OSError):
            logger.warning("Failed to get remote url for repo: %s", repo_path)
        return "unknown"
