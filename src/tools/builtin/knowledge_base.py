from __future__ import annotations

import asyncio
import json
import os
import re
from pathlib import Path
from typing import Any

import httpx

from src.tools.interfaces import ITool, ToolParameter, ToolResult, ToolSpec

VALID_PROVIDERS = frozenset({"local", "notion", "yuque", "obsidian"})

VALID_ACTIONS = frozenset({"list", "read", "write", "search"})


class KnowledgeBaseTool(ITool):
    """Knowledge base tool for accessing documents from Notion, Yuque,
    Obsidian, and local markdown files.

    Supports listing, reading, writing, and searching across multiple
    knowledge base providers. API keys are read from environment
    variables only.
    """

    def __init__(self) -> None:
        self._spec = ToolSpec(
            name="knowledge_base",
            description=(
                "Access knowledge bases from Notion, Yuque, Obsidian, "
                "or local markdown files"
            ),
            category="office",
            dangerous=False,
            parameters=[
                ToolParameter(
                    name="provider",
                    type="string",
                    description=(
                        "Knowledge base provider: "
                        "notion/yuque/obsidian/local"
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="action",
                    type="string",
                    description=(
                        "Action to perform: list/read/write/search"
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="path",
                    type="string",
                    description=(
                        "File path or resource identifier "
                        "(e.g. repo_id/doc_slug)"
                    ),
                    required=False,
                ),
                ToolParameter(
                    name="query",
                    type="string",
                    description="Search query string",
                    required=False,
                ),
                ToolParameter(
                    name="content",
                    type="object",
                    description=(
                        "Content payload for write action "
                        "(dict with keys like title, body)"
                    ),
                    required=False,
                ),
                ToolParameter(
                    name="page_id",
                    type="string",
                    description="Page or document identifier",
                    required=False,
                ),
                ToolParameter(
                    name="timeout",
                    type="integer",
                    description="Request timeout in seconds",
                    required=False,
                    default=30,
                ),
            ],
        )

    def get_spec(self) -> ToolSpec:
        """Return the tool specification.

        Returns:
            ToolSpec describing this tool's capabilities.
        """
        return self._spec

    async def validate(self, params: dict[str, Any]) -> list[str]:
        """Validate parameters before execution.

        Args:
            params: Dictionary of tool parameters.

        Returns:
            List of validation error messages. Empty list means valid.
        """
        errors: list[str] = []

        provider = params.get("provider", "")
        if provider not in VALID_PROVIDERS:
            errors.append(
                f"Invalid provider: {provider}. "
                f"Must be one of: {', '.join(sorted(VALID_PROVIDERS))}"
            )

        action = params.get("action", "")
        if action not in VALID_ACTIONS:
            errors.append(
                f"Invalid action: {action}. "
                f"Must be one of: {', '.join(sorted(VALID_ACTIONS))}"
            )

        if action == "search" and not params.get("query"):
            errors.append("search action requires a 'query' parameter")

        if action == "write" and not params.get("content"):
            errors.append("write action requires a 'content' parameter")

        if provider == "notion":
            if not os.environ.get("NOTION_TOKEN"):
                errors.append(
                    "NOTION_TOKEN environment variable is not set"
                )
            if action in ("list", "write"):
                if not os.environ.get("NOTION_DATABASE_ID"):
                    errors.append(
                        "NOTION_DATABASE_ID environment "
                        "variable is not set"
                    )
            if action == "read" and not params.get("page_id"):
                errors.append(
                    "read action for notion requires a 'page_id' parameter"
                )
            if action == "write" and not params.get("page_id"):
                errors.append(
                    "write action for notion requires a 'page_id' parameter"
                )

        if provider == "yuque":
            if not os.environ.get("YUQUE_TOKEN"):
                errors.append(
                    "YUQUE_TOKEN environment variable is not set"
                )

        if provider == "obsidian":
            if not os.environ.get("OBSIDIAN_VAULT_PATH"):
                errors.append(
                    "OBSIDIAN_VAULT_PATH environment "
                    "variable is not set"
                )

        return errors

    async def execute(
        self,
        params: dict[str, Any],
        user_id: str = "default",
    ) -> ToolResult:
        """Execute the requested knowledge base operation.

        Args:
            params: Dictionary of tool parameters.
            user_id: Identifier of the user making the request.

        Returns:
            ToolResult with operation outcome.
        """
        provider = params.get("provider", "")
        action = params.get("action", "")
        timeout = params.get("timeout", 30)

        if provider == "local":
            return await self._execute_local(action, params, timeout)
        elif provider == "notion":
            return await self._execute_notion(action, params, timeout)
        elif provider == "yuque":
            return await self._execute_yuque(action, params, timeout)
        elif provider == "obsidian":
            return await self._execute_obsidian(action, params, timeout)
        else:
            return ToolResult(
                success=False,
                error=f"Unknown provider: {provider}",
            )

    def _get_dangerous(self, action: str) -> bool:
        """Determine if an action is dangerous.

        Args:
            action: The action name.

        Returns:
            True if the action requires approval.
        """
        return action == "write"

    def _local_base_path(self) -> Path:
        """Return the local knowledge base directory path.

        Returns:
            Path to data/knowledge/ directory.
        """
        return Path.cwd().resolve() / "data" / "knowledge"

    def _ensure_local_dir(self, base: Path) -> ToolResult | None:
        """Ensure the local knowledge base directory exists.

        Args:
            base: The base directory path.

        Returns:
            ToolResult with error if directory creation fails, else None.
        """
        if not base.exists():
            try:
                base.mkdir(parents=True, exist_ok=True)
            except OSError as e:
                return ToolResult(
                    success=False,
                    error=f"Failed to create directory {base}: {e}",
                )
        return None

    async def _execute_local(
        self,
        action: str,
        params: dict[str, Any],
        timeout: int,
    ) -> ToolResult:
        """Execute a local knowledge base operation.

        Args:
            action: The action to perform.
            params: Dictionary of tool parameters.
            timeout: Request timeout in seconds.

        Returns:
            ToolResult with operation outcome.
        """
        base = self._local_base_path()
        err = self._ensure_local_dir(base)
        if err is not None:
            return err

        if action == "list":
            return await self._local_list(base)
        elif action == "read":
            return await self._local_read(base, params)
        elif action == "search":
            return await self._local_search(base, params)
        elif action == "write":
            return await self._local_write(base, params)
        else:
            return ToolResult(
                success=False,
                error=f"Unsupported action for local: {action}",
            )

    async def _local_list(self, base: Path) -> ToolResult:
        """List markdown files in the local knowledge directory.

        Args:
            base: The base knowledge directory path.

        Returns:
            ToolResult with list of markdown files.
        """
        try:
            files: list[dict[str, Any]] = []
            for entry in sorted(base.iterdir()):
                if entry.is_file() and entry.suffix == ".md":
                    stat = entry.stat()
                    files.append({
                        "name": entry.name,
                        "size": stat.st_size,
                        "modified": int(stat.st_mtime),
                    })
            return ToolResult(
                success=True,
                data={
                    "directory": str(base),
                    "files": files,
                    "count": len(files),
                },
            )
        except Exception as e:
            return ToolResult(
                success=False,
                error=f"Failed to list local knowledge base: {e}",
            )

    async def _local_read(
        self,
        base: Path,
        params: dict[str, Any],
    ) -> ToolResult:
        """Read a markdown file from the local knowledge directory.

        Args:
            base: The base knowledge directory path.
            params: Dictionary of tool parameters.

        Returns:
            ToolResult with file content.
        """
        path_str = params.get("path", "")
        if not path_str:
            return ToolResult(
                success=False,
                error="path parameter is required for read action",
            )
        target = (base / path_str).resolve()
        if not str(target).startswith(str(base.resolve())):
            return ToolResult(
                success=False,
                error="Path traversal is not allowed",
            )
        if not target.exists():
            return ToolResult(
                success=False,
                error=f"File not found: {path_str}",
            )
        if not target.is_file():
            return ToolResult(
                success=False,
                error=f"Path is not a file: {path_str}",
            )
        try:
            content = await asyncio.to_thread(target.read_text, encoding="utf-8")
            return ToolResult(
                success=True,
                data={
                    "path": path_str,
                    "content": content,
                },
            )
        except Exception as e:
            return ToolResult(
                success=False,
                error=f"Failed to read file: {e}",
            )

    async def _local_search(
        self,
        base: Path,
        params: dict[str, Any],
    ) -> ToolResult:
        """Search for a query in local markdown files.

        Args:
            base: The base knowledge directory path.
            params: Dictionary of tool parameters.

        Returns:
            ToolResult with search matches.
        """
        query = params.get("query", "")
        if not query:
            return ToolResult(
                success=False,
                error="query parameter is required for search action",
            )
        try:
            matches: list[dict[str, Any]] = []
            pattern = re.compile(re.escape(query), re.IGNORECASE)
            for file_path in sorted(base.rglob("*.md")):
                if not file_path.is_file():
                    continue
                try:
                    content = await asyncio.to_thread(
                        file_path.read_text, errors="replace"
                    )
                except Exception:
                    continue
                line_matches: list[dict[str, Any]] = []
                for line_num, line in enumerate(content.splitlines(), 1):
                    if pattern.search(line):
                        line_matches.append({
                            "line": line_num,
                            "content": line.strip()[:200],
                        })
                if line_matches:
                    rel_path = str(file_path.relative_to(base))
                    matches.append({
                        "file": rel_path,
                        "matches": line_matches,
                        "count": len(line_matches),
                    })
            return ToolResult(
                success=True,
                data={
                    "query": query,
                    "results": matches,
                    "total_matches": sum(m["count"] for m in matches),
                },
            )
        except Exception as e:
            return ToolResult(
                success=False,
                error=f"Failed to search local knowledge base: {e}",
            )

    async def _local_write(
        self,
        base: Path,
        params: dict[str, Any],
    ) -> ToolResult:
        """Write content to a markdown file in the local knowledge directory.

        Args:
            base: The base knowledge directory path.
            params: Dictionary of tool parameters.

        Returns:
            ToolResult with write status.
        """
        path_str = params.get("path", "")
        content = params.get("content", {})
        if not path_str:
            return ToolResult(
                success=False,
                error="path parameter is required for write action",
            )
        if not isinstance(content, dict):
            return ToolResult(
                success=False,
                error="content must be a dict for write action",
            )
        target = (base / path_str).resolve()
        if not str(target).startswith(str(base.resolve())):
            return ToolResult(
                success=False,
                error="Path traversal is not allowed",
            )
        body = content.get("body", "")
        if not body:
            body = json.dumps(content, ensure_ascii=False, indent=2)
        try:
            parent = target.parent
            if not parent.exists():
                await asyncio.to_thread(
                    parent.mkdir, parents=True, exist_ok=True
                )
            await asyncio.to_thread(
                target.write_text, body, encoding="utf-8"
            )
            return ToolResult(
                success=True,
                data={
                    "path": path_str,
                    "size": len(body),
                },
            )
        except Exception as e:
            return ToolResult(
                success=False,
                error=f"Failed to write file: {e}",
            )

    async def _execute_notion(
        self,
        action: str,
        params: dict[str, Any],
        timeout: int,
    ) -> ToolResult:
        """Execute a Notion API operation.

        Args:
            action: The action to perform.
            params: Dictionary of tool parameters.
            timeout: Request timeout in seconds.

        Returns:
            ToolResult with operation outcome.
        """
        token = os.environ.get("NOTION_TOKEN", "")
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Notion-Version": "2022-06-28",
        }

        if action == "list":
            return await self._notion_list(headers, params, timeout)
        elif action == "read":
            return await self._notion_read(headers, params, timeout)
        elif action == "write":
            return await self._notion_write(headers, params, timeout)
        else:
            return ToolResult(
                success=False,
                error=f"Unsupported action for notion: {action}",
            )

    async def _notion_list(
        self,
        headers: dict[str, str],
        params: dict[str, Any],
        timeout: int,
    ) -> ToolResult:
        """List pages in a Notion database.

        Args:
            headers: HTTP headers for Notion API.
            params: Dictionary of tool parameters.
            timeout: Request timeout in seconds.

        Returns:
            ToolResult with list of database pages.
        """
        database_id = os.environ.get("NOTION_DATABASE_ID", "")
        url = f"https://api.notion.com/v1/databases/{database_id}/query"
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(url, headers=headers, json={})
                resp.raise_for_status()
                data = resp.json()
            results = data.get("results", [])
            pages: list[dict[str, Any]] = []
            for page in results:
                props = page.get("properties", {})
                title_prop = None
                for prop in props.values():
                    if prop.get("type") == "title":
                        titles = prop.get("title", [])
                        title_prop = "".join(
                            t.get("plain_text", "") for t in titles
                        )
                        break
                pages.append({
                    "id": page.get("id"),
                    "title": title_prop or "",
                    "created_time": page.get("created_time"),
                    "last_edited_time": page.get("last_edited_time"),
                })
            return ToolResult(
                success=True,
                data={
                    "provider": "notion",
                    "pages": pages,
                    "count": len(pages),
                },
            )
        except httpx.HTTPStatusError as e:
            return ToolResult(
                success=False,
                error=f"Notion API error: {e.response.status_code} {e.response.text}",
            )
        except httpx.RequestError as e:
            return ToolResult(
                success=False,
                error=f"Notion API request failed: {e}",
            )

    async def _notion_read(
        self,
        headers: dict[str, str],
        params: dict[str, Any],
        timeout: int,
    ) -> ToolResult:
        """Read a Notion page by page_id.

        Args:
            headers: HTTP headers for Notion API.
            params: Dictionary of tool parameters.
            timeout: Request timeout in seconds.

        Returns:
            ToolResult with page content.
        """
        page_id = params.get("page_id", "")
        url = f"https://api.notion.com/v1/pages/{page_id}"
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.get(url, headers=headers)
                resp.raise_for_status()
                data = resp.json()
            return ToolResult(
                success=True,
                data={
                    "provider": "notion",
                    "page": data,
                },
            )
        except httpx.HTTPStatusError as e:
            return ToolResult(
                success=False,
                error=f"Notion API error: {e.response.status_code} {e.response.text}",
            )
        except httpx.RequestError as e:
            return ToolResult(
                success=False,
                error=f"Notion API request failed: {e}",
            )

    async def _notion_write(
        self,
        headers: dict[str, str],
        params: dict[str, Any],
        timeout: int,
    ) -> ToolResult:
        """Create a page in a Notion database.

        Args:
            headers: HTTP headers for Notion API.
            params: Dictionary of tool parameters.
            timeout: Request timeout in seconds.

        Returns:
            ToolResult with creation status.
        """
        database_id = os.environ.get("NOTION_DATABASE_ID", "")
        content = params.get("content", {})
        page_id = params.get("page_id", "")

        properties: dict[str, Any] = {}
        title_text = content.get("title", "") if isinstance(content, dict) else ""
        if title_text:
            properties["Title"] = {
                "title": [{"text": {"content": title_text}}]
            }

        body: dict[str, Any] = {
            "parent": {"database_id": database_id},
            "properties": properties,
        }

        children: list[dict[str, Any]] = []
        body_text = content.get("body", "") if isinstance(content, dict) else ""
        if body_text:
            children.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"type": "text", "text": {"content": body_text}}]
                },
            })
        if children:
            body["children"] = children

        url = f"https://api.notion.com/v1/pages?page_id={page_id}"
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(url, headers=headers, json=body)
                resp.raise_for_status()
                data = resp.json()
            return ToolResult(
                success=True,
                data={
                    "provider": "notion",
                    "page_id": data.get("id"),
                    "url": data.get("url"),
                },
            )
        except httpx.HTTPStatusError as e:
            return ToolResult(
                success=False,
                error=f"Notion API error: {e.response.status_code} {e.response.text}",
            )
        except httpx.RequestError as e:
            return ToolResult(
                success=False,
                error=f"Notion API request failed: {e}",
            )

    async def _execute_yuque(
        self,
        action: str,
        params: dict[str, Any],
        timeout: int,
    ) -> ToolResult:
        """Execute a Yuque API operation.

        Args:
            action: The action to perform.
            params: Dictionary of tool parameters.
            timeout: Request timeout in seconds.

        Returns:
            ToolResult with operation outcome.
        """
        token = os.environ.get("YUQUE_TOKEN", "")
        headers = {
            "X-Auth-Token": token,
            "Content-Type": "application/json",
            "User-Agent": "ShuyuanCore/1.0",
        }

        if action == "list":
            return await self._yuque_list(headers, params, timeout)
        elif action == "read":
            return await self._yuque_read(headers, params, timeout)
        else:
            return ToolResult(
                success=False,
                error=f"Unsupported action for yuque: {action}",
            )

    async def _yuque_get_user(
        self,
        headers: dict[str, str],
        timeout: int,
    ) -> str | None:
        """Get the current Yuque user login from the API.

        Args:
            headers: HTTP headers for Yuque API.
            timeout: Request timeout in seconds.

        Returns:
            User login string, or None on failure.
        """
        url = "https://www.yuque.com/api/v2/user"
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.get(url, headers=headers)
                resp.raise_for_status()
                data = resp.json()
            return data.get("data", {}).get("login")
        except Exception:
            return None

    async def _yuque_list(
        self,
        headers: dict[str, str],
        params: dict[str, Any],
        timeout: int,
    ) -> ToolResult:
        """List Yuque repos or docs.

        Without a path, lists the user's repos. With a path (repo_id),
        lists docs within that repo.

        Args:
            headers: HTTP headers for Yuque API.
            params: Dictionary of tool parameters.
            timeout: Request timeout in seconds.

        Returns:
            ToolResult with list of repos or docs.
        """
        path = params.get("path", "")

        if path:
            url = f"https://www.yuque.com/api/v2/repos/{path}/docs"
            try:
                async with httpx.AsyncClient(timeout=timeout) as client:
                    resp = await client.get(url, headers=headers)
                    resp.raise_for_status()
                    data = resp.json()
                docs_list = data.get("data", [])
                docs: list[dict[str, Any]] = []
                for doc in docs_list:
                    docs.append({
                        "id": doc.get("id"),
                        "title": doc.get("title"),
                        "slug": doc.get("slug"),
                        "updated_at": doc.get("updated_at"),
                    })
                return ToolResult(
                    success=True,
                    data={
                        "provider": "yuque",
                        "type": "docs",
                        "repo_id": path,
                        "docs": docs,
                        "count": len(docs),
                    },
                )
            except httpx.HTTPStatusError as e:
                return ToolResult(
                    success=False,
                    error=f"Yuque API error: {e.response.status_code} {e.response.text}",
                )
            except httpx.RequestError as e:
                return ToolResult(
                    success=False,
                    error=f"Yuque API request failed: {e}",
                )
        else:
            user = await self._yuque_get_user(headers, timeout)
            if not user:
                return ToolResult(
                    success=False,
                    error="Failed to get Yuque user info",
                )
            url = f"https://www.yuque.com/api/v2/users/{user}/repos"
            try:
                async with httpx.AsyncClient(timeout=timeout) as client:
                    resp = await client.get(url, headers=headers)
                    resp.raise_for_status()
                    data = resp.json()
                repos_list = data.get("data", [])
                repos: list[dict[str, Any]] = []
                for repo in repos_list:
                    repos.append({
                        "id": repo.get("id"),
                        "name": repo.get("name"),
                        "slug": repo.get("slug"),
                        "namespace": repo.get("namespace"),
                        "description": repo.get("description"),
                        "updated_at": repo.get("updated_at"),
                    })
                return ToolResult(
                    success=True,
                    data={
                        "provider": "yuque",
                        "type": "repos",
                        "repos": repos,
                        "count": len(repos),
                    },
                )
            except httpx.HTTPStatusError as e:
                return ToolResult(
                    success=False,
                    error=f"Yuque API error: {e.response.status_code} {e.response.text}",
                )
            except httpx.RequestError as e:
                return ToolResult(
                    success=False,
                    error=f"Yuque API request failed: {e}",
                )

    async def _yuque_read(
        self,
        headers: dict[str, str],
        params: dict[str, Any],
        timeout: int,
    ) -> ToolResult:
        """Read a Yuque document.

        The path parameter should be in the format "repo_id/doc_slug".

        Args:
            headers: HTTP headers for Yuque API.
            params: Dictionary of tool parameters.
            timeout: Request timeout in seconds.

        Returns:
            ToolResult with document content.
        """
        path = params.get("path", "")
        if not path:
            return ToolResult(
                success=False,
                error=(
                    "path parameter is required for yuque read. "
                    "Format: repo_id/doc_slug"
                ),
            )

        url = f"https://www.yuque.com/api/v2/repos/{path}"
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.get(url, headers=headers)
                resp.raise_for_status()
                data = resp.json()
            doc_data = data.get("data", {})
            return ToolResult(
                success=True,
                data={
                    "provider": "yuque",
                    "id": doc_data.get("id"),
                    "title": doc_data.get("title"),
                    "slug": doc_data.get("slug"),
                    "body": doc_data.get("body"),
                    "body_html": doc_data.get("body_html"),
                    "updated_at": doc_data.get("updated_at"),
                },
            )
        except httpx.HTTPStatusError as e:
            return ToolResult(
                success=False,
                error=f"Yuque API error: {e.response.status_code} {e.response.text}",
            )
        except httpx.RequestError as e:
            return ToolResult(
                success=False,
                error=f"Yuque API request failed: {e}",
            )

    async def _execute_obsidian(
        self,
        action: str,
        params: dict[str, Any],
        timeout: int,
    ) -> ToolResult:
        """Execute an Obsidian vault operation.

        Args:
            action: The action to perform.
            params: Dictionary of tool parameters.
            timeout: Request timeout in seconds.

        Returns:
            ToolResult with operation outcome.
        """
        vault_path_str = os.environ.get("OBSIDIAN_VAULT_PATH", "")
        vault = Path(vault_path_str).resolve()

        if not vault.exists():
            return ToolResult(
                success=False,
                error=f"Obsidian vault path does not exist: {vault_path_str}",
            )
        if not vault.is_dir():
            return ToolResult(
                success=False,
                error=f"Obsidian vault path is not a directory: {vault_path_str}",
            )

        if action == "list":
            return await self._obsidian_list(vault)
        elif action == "read":
            return await self._obsidian_read(vault, params)
        elif action == "search":
            return await self._obsidian_search(vault, params)
        else:
            return ToolResult(
                success=False,
                error=f"Unsupported action for obsidian: {action}",
            )

    async def _obsidian_list(self, vault: Path) -> ToolResult:
        """List markdown files in the Obsidian vault.

        Args:
            vault: The Obsidian vault directory path.

        Returns:
            ToolResult with list of markdown files.
        """
        try:
            files: list[dict[str, Any]] = []
            for f in sorted(vault.rglob("*.md")):
                if not f.is_file():
                    continue
                rel = f.relative_to(vault)
                stat = f.stat()
                files.append({
                    "path": str(rel.as_posix()),
                    "size": stat.st_size,
                    "modified": int(stat.st_mtime),
                })
            return ToolResult(
                success=True,
                data={
                    "vault": str(vault),
                    "files": files,
                    "count": len(files),
                },
            )
        except Exception as e:
            return ToolResult(
                success=False,
                error=f"Failed to list Obsidian vault: {e}",
            )

    async def _obsidian_read(
        self,
        vault: Path,
        params: dict[str, Any],
    ) -> ToolResult:
        """Read a markdown file from the Obsidian vault.

        Args:
            vault: The Obsidian vault directory path.
            params: Dictionary of tool parameters.

        Returns:
            ToolResult with file content.
        """
        path_str = params.get("path", "")
        if not path_str:
            return ToolResult(
                success=False,
                error="path parameter is required for obsidian read",
            )
        target = (vault / path_str).resolve()
        if not str(target).startswith(str(vault)):
            return ToolResult(
                success=False,
                error="Path traversal is not allowed",
            )
        if not target.exists():
            return ToolResult(
                success=False,
                error=f"File not found in vault: {path_str}",
            )
        if not target.is_file():
            return ToolResult(
                success=False,
                error=f"Path is not a file: {path_str}",
            )
        try:
            content = await asyncio.to_thread(target.read_text, encoding="utf-8")
            return ToolResult(
                success=True,
                data={
                    "path": path_str,
                    "content": content,
                },
            )
        except Exception as e:
            return ToolResult(
                success=False,
                error=f"Failed to read file: {e}",
            )

    async def _obsidian_search(
        self,
        vault: Path,
        params: dict[str, Any],
    ) -> ToolResult:
        """Search for a query in Obsidian vault markdown files.

        Args:
            vault: The Obsidian vault directory path.
            params: Dictionary of tool parameters.

        Returns:
            ToolResult with search matches.
        """
        query = params.get("query", "")
        if not query:
            return ToolResult(
                success=False,
                error="query parameter is required for obsidian search",
            )
        try:
            matches: list[dict[str, Any]] = []
            pattern = re.compile(re.escape(query), re.IGNORECASE)
            for file_path in sorted(vault.rglob("*.md")):
                if not file_path.is_file():
                    continue
                try:
                    content = await asyncio.to_thread(
                        file_path.read_text, errors="replace"
                    )
                except Exception:
                    continue
                line_matches: list[dict[str, Any]] = []
                for line_num, line in enumerate(content.splitlines(), 1):
                    if pattern.search(line):
                        line_matches.append({
                            "line": line_num,
                            "content": line.strip()[:200],
                        })
                if line_matches:
                    rel_path = str(file_path.relative_to(vault).as_posix())
                    matches.append({
                        "file": rel_path,
                        "matches": line_matches,
                        "count": len(line_matches),
                    })
            return ToolResult(
                success=True,
                data={
                    "query": query,
                    "results": matches,
                    "total_matches": sum(m["count"] for m in matches),
                },
            )
        except Exception as e:
            return ToolResult(
                success=False,
                error=f"Failed to search Obsidian vault: {e}",
            )
