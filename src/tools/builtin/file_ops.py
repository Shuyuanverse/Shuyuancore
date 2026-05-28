from __future__ import annotations

import asyncio
import fnmatch
import os
from pathlib import Path
from typing import Any

from src.config import get_settings
from src.security.approval import get_approval_manager
from src.tools.interfaces import ITool, ToolParameter, ToolResult, ToolSpec

VALID_OPERATIONS = frozenset({
    "read", "write", "edit", "search", "delete", "list",
})

BLOCKED_PATTERNS = frozenset({
    ".env",
    "config/default.yaml",
    "*.pem",
    "*.key",
    "id_rsa",
    "id_ed25519",
})


class FileOpsTool(ITool):
    """File operations tool for reading, writing, editing, searching,
    deleting, and listing files and directories.

    Supports both relative paths (resolved against project root) and
    absolute paths. Enforces path safety by blocking sensitive files
    and requiring approval for dangerous operations.
    """

    def __init__(self) -> None:
        self._project_root = Path.cwd().resolve()
        self._spec = ToolSpec(
            name="file_ops",
            description="File operations: read, write, edit, search, delete, list",
            category="system",
            dangerous=False,
            parameters=[
                ToolParameter(
                    name="operation",
                    type="string",
                    description="Operation to perform: read/write/edit/search/delete/list",
                    required=True,
                ),
                ToolParameter(
                    name="path",
                    type="string",
                    description="File or directory path",
                    required=True,
                ),
                ToolParameter(
                    name="content",
                    type="string",
                    description="File content for write/edit operations",
                    required=False,
                ),
                ToolParameter(
                    name="pattern",
                    type="string",
                    description="Search pattern for search operation",
                    required=False,
                ),
                ToolParameter(
                    name="encoding",
                    type="string",
                    description="File encoding (default: utf-8)",
                    required=False,
                    default="utf-8",
                ),
            ],
        )

    def get_spec(self) -> ToolSpec:
        """Return the tool specification."""

        return self._spec

    async def validate(self, params: dict[str, Any]) -> list[str]:
        """Validate parameters before execution.

        Args:
            params: Dictionary of tool parameters.

        Returns:
            List of validation error messages. Empty list means valid.
        """

        errors: list[str] = []
        operation = params.get("operation", "")
        if operation not in VALID_OPERATIONS:
            errors.append(
                f"Invalid operation: {operation}. "
                f"Must be one of: {', '.join(VALID_OPERATIONS)}"
            )

        path_str = params.get("path", "")
        if not path_str:
            errors.append("path is required and must not be empty")
        else:
            resolved = self._resolve_path(path_str)
            if self._is_path_blocked(resolved):
                errors.append(
                    f"Access denied: path matches a blocked pattern: {resolved}"
                )

        if operation == "edit":
            if "old_str" not in params or "new_str" not in params:
                errors.append(
                    "edit operation requires 'old_str' and 'new_str' parameters"
                )

        if operation == "search":
            if not params.get("pattern"):
                errors.append("search operation requires a 'pattern' parameter")

        return errors

    async def execute(
        self,
        params: dict[str, Any],
        user_id: str = "default",
    ) -> ToolResult:
        """Execute the requested file operation.

        Args:
            params: Dictionary of tool parameters.
            user_id: Identifier of the user making the request.

        Returns:
            ToolResult with operation outcome.

        Raises:
            Exception: Propagated from underlying file operations.
        """

        operation = params.get("operation", "")
        path_str = params.get("path", "")
        encoding = params.get("encoding", "utf-8")

        resolved = self._resolve_path(path_str)

        if self._is_dangerous(operation, resolved):
            config = get_settings().tools
            approval_mgr = await get_approval_manager()
            req = await approval_mgr.request(
                tool_name="file_ops",
                params=params,
                user_id=user_id,
                timeout=config.approval_timeout,
            )
            approved = await approval_mgr.wait(
                req.approval_id, timeout=config.approval_timeout
            )
            if not approved:
                return ToolResult(
                    success=False,
                    error=(
                        f"Operation '{operation}' on '{path_str}' "
                        f"was not approved ({req.approval_id})"
                    ),
                    approval_id=req.approval_id,
                )

        if operation == "read":
            return await self._read(resolved, encoding)
        elif operation == "write":
            return await self._write(
                resolved, params.get("content", ""), encoding
            )
        elif operation == "edit":
            return await self._edit(
                resolved,
                params.get("old_str", ""),
                params.get("new_str", ""),
                encoding,
            )
        elif operation == "search":
            return await self._search(resolved, params.get("pattern", ""))
        elif operation == "delete":
            return await self._delete(resolved)
        elif operation == "list":
            return await self._list_dir(resolved)
        else:
            return ToolResult(
                success=False,
                error=f"Unknown operation: {operation}",
            )

    def _resolve_path(self, path_str: str) -> Path:
        """Resolve a path string to an absolute Path.

        Relative paths are resolved against the project root directory.
        Absolute paths are used as-is after resolution.

        Args:
            path_str: File or directory path string.

        Returns:
            Resolved absolute Path object.
        """

        p = Path(path_str)
        if p.is_absolute():
            return p.resolve()
        return (self._project_root / p).resolve()

    def _is_path_blocked(self, path: Path) -> bool:
        """Check if a path matches any blocked pattern.

        Patterns are checked against both the filename and the
        relative path from the project root.

        Args:
            path: Absolute Path to check.

        Returns:
            True if the path matches a blocked pattern.
        """

        name = path.name
        rel_str: str | None = None
        try:
            rel_str = str(path.relative_to(self._project_root).as_posix())
        except ValueError:
            pass

        for pattern in BLOCKED_PATTERNS:
            if fnmatch.fnmatch(name, pattern):
                return True
            if rel_str is not None and fnmatch.fnmatch(rel_str, pattern):
                return True

        return False

    def _is_dangerous(self, operation: str, resolved: Path) -> bool:
        """Determine if an operation is dangerous and requires approval.

        Delete is always dangerous. Write and edit are dangerous
        when targeting paths outside the project root directory.

        Args:
            operation: The operation name.
            resolved: The resolved absolute Path.

        Returns:
            True if the operation requires approval.
        """

        if operation == "delete":
            return True
        if operation in ("write", "edit"):
            try:
                resolved.relative_to(self._project_root)
                return False
            except ValueError:
                return True
        return False

    async def _read(self, path: Path, encoding: str) -> ToolResult:
        """Read and return the contents of a file.

        Args:
            path: Absolute path to the file.
            encoding: File encoding.

        Returns:
            ToolResult with file content in data.
        """

        if not path.exists():
            return ToolResult(
                success=False,
                error=f"File not found: {path}",
            )
        if not path.is_file():
            return ToolResult(
                success=False,
                error=f"Path is not a file: {path}",
            )
        try:
            content = await asyncio.to_thread(
                path.read_text, encoding=encoding
            )
            return ToolResult(success=True, data=content)
        except Exception as e:
            return ToolResult(
                success=False,
                error=f"Failed to read file: {e}",
            )

    async def _write(
        self, path: Path, content: str, encoding: str
    ) -> ToolResult:
        """Write content to a file, creating parent directories if needed.

        Args:
            path: Absolute path to the file.
            content: Text content to write.
            encoding: File encoding.

        Returns:
            ToolResult with success status and file path.
        """

        try:
            parent = path.parent
            if not parent.exists():
                await asyncio.to_thread(parent.mkdir, parents=True, exist_ok=True)
            await asyncio.to_thread(
                path.write_text, content, encoding=encoding
            )
            return ToolResult(
                success=True,
                data=f"Written {len(content)} bytes to {path}",
            )
        except Exception as e:
            return ToolResult(
                success=False,
                error=f"Failed to write file: {e}",
            )

    async def _edit(
        self, path: Path, old_str: str, new_str: str, encoding: str
    ) -> ToolResult:
        """Search and replace text in a file.

        Reads the file, replaces all occurrences of old_str with
        new_str, and writes the result back.

        Args:
            path: Absolute path to the file.
            old_str: String to search for.
            new_str: Replacement string.
            encoding: File encoding.

        Returns:
            ToolResult with replacement count.
        """

        if not path.exists():
            return ToolResult(
                success=False,
                error=f"File not found: {path}",
            )
        if not path.is_file():
            return ToolResult(
                success=False,
                error=f"Path is not a file: {path}",
            )
        try:
            content = await asyncio.to_thread(
                path.read_text, encoding=encoding
            )
            count = content.count(old_str)
            if count == 0:
                return ToolResult(
                    success=False,
                    error=f"Pattern not found in {path}",
                )
            new_content = content.replace(old_str, new_str)
            await asyncio.to_thread(
                path.write_text, new_content, encoding=encoding
            )
            return ToolResult(
                success=True,
                data=f"Replaced {count} occurrence(s) in {path}",
            )
        except Exception as e:
            return ToolResult(
                success=False,
                error=f"Failed to edit file: {e}",
            )

    async def _search(self, path: Path, pattern: str) -> ToolResult:
        """Search for a pattern recursively in a directory.

        Returns matching file paths and the lines that matched.
        Only searches regular text files.

        Args:
            path: Directory path to search in.
            pattern: Text pattern to search for.

        Returns:
            ToolResult with list of matches (file:line_number:content).
        """

        if not path.exists():
            return ToolResult(
                success=False,
                error=f"Path not found: {path}",
            )
        if not path.is_dir():
            return ToolResult(
                success=False,
                error=f"Path is not a directory: {path}",
            )
        try:
            matches: list[str] = []
            for file_path in sorted(path.rglob("*")):
                if not file_path.is_file():
                    continue
                try:
                    content = await asyncio.to_thread(
                        file_path.read_text, errors="replace"
                    )
                except Exception:
                    continue
                for line_num, line in enumerate(content.splitlines(), 1):
                    if pattern in line:
                        matches.append(
                            f"{file_path}:{line_num}:{line.strip()[:200]}"
                        )
            return ToolResult(
                success=True,
                data={
                    "pattern": pattern,
                    "directory": str(path),
                    "matches": matches,
                    "count": len(matches),
                },
            )
        except Exception as e:
            return ToolResult(
                success=False,
                error=f"Failed to search: {e}",
            )

    async def _delete(self, path: Path) -> ToolResult:
        """Delete a file or empty directory.

        Only deletes files and empty directories. Non-empty
        directories will fail with an error message.

        Args:
            path: Absolute path to the file or directory.

        Returns:
            ToolResult with deletion status.
        """

        if not path.exists():
            return ToolResult(
                success=False,
                error=f"Path not found: {path}",
            )
        try:
            if path.is_file() or path.is_symlink():
                await asyncio.to_thread(os.remove, str(path))
                return ToolResult(
                    success=True,
                    data=f"Deleted file: {path}",
                )
            elif path.is_dir():
                await asyncio.to_thread(os.rmdir, str(path))
                return ToolResult(
                    success=True,
                    data=f"Deleted empty directory: {path}",
                )
            else:
                return ToolResult(
                    success=False,
                    error=f"Unsupported path type: {path}",
                )
        except OSError as e:
            return ToolResult(
                success=False,
                error=f"Failed to delete: {e}",
            )

    async def _list_dir(self, path: Path) -> ToolResult:
        """List the contents of a directory.

        Returns entries with name, type (file/dir), and size.

        Args:
            path: Directory path to list.

        Returns:
            ToolResult with list of directory entries.
        """

        if not path.exists():
            return ToolResult(
                success=False,
                error=f"Path not found: {path}",
            )
        if not path.is_dir():
            return ToolResult(
                success=False,
                error=f"Path is not a directory: {path}",
            )
        try:
            entries: list[dict[str, Any]] = []
            for entry in sorted(path.iterdir()):
                stat = entry.stat() if entry.exists() else None
                entries.append({
                    "name": entry.name,
                    "type": "dir" if entry.is_dir() else "file",
                    "size": stat.st_size if stat else 0,
                    "modified": int(stat.st_mtime) if stat else 0,
                })
            return ToolResult(
                success=True,
                data={
                    "directory": str(path),
                    "entries": entries,
                    "count": len(entries),
                },
            )
        except PermissionError as e:
            return ToolResult(
                success=False,
                error=f"Permission denied: {e}",
            )
        except Exception as e:
            return ToolResult(
                success=False,
                error=f"Failed to list directory: {e}",
            )
