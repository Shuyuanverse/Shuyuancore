from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class MCPClient:
    """MCP 客户端（Model Context Protocol）。

    Connects to an MCP server to discover and invoke tools
    remotely. Uses httpx for HTTP communication.
    """

    def __init__(self, server_url: str = "") -> None:
        self._server_url: str = server_url
        self._client: httpx.AsyncClient | None = None
        self._connected: bool = False

    async def connect(self, server_url: str) -> None:
        """连接到 MCP 服务器。

        Establishes an HTTP connection to the specified MCP
        server URL. Must be called before list_tools or call_tool.

        Args:
            server_url: The base URL of the MCP server
                        (e.g., 'http://localhost:8000').

        Raises:
            ValueError: If server_url is empty.
            httpx.ConnectError: If the server cannot be reached.
        """
        if not server_url or not server_url.strip():
            raise ValueError("server_url must not be empty / server_url 不能为空")

        self._server_url = server_url.rstrip("/")
        self._client = httpx.AsyncClient(
            base_url=self._server_url,
            timeout=httpx.Timeout(30.0),
        )

        try:
            health = await self._client.get("/health")
            health.raise_for_status()
            self._connected = True
            logger.info("MCP client connected to %s", self._server_url)
        except httpx.RequestError:
            self._connected = False
            raise

    async def list_tools(self) -> list[dict[str, Any]]:
        """列出 MCP 工具。

        Retrieves the list of available tools from the connected
        MCP server.

        Returns:
            List of tool definitions as dictionaries, each containing
            name, description, and parameter schema.

        Raises:
            RuntimeError: If not connected to a server.
            httpx.RequestError: If the request fails.
        """
        self._ensure_connected()

        response = await self._client.get("/tools")
        response.raise_for_status()
        data: dict[str, Any] = response.json()
        return data.get("tools", [])

    async def call_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
    ) -> str:
        """调用 MCP 工具。

        Invokes a tool on the MCP server with the given arguments.

        Args:
            tool_name: The name of the tool to invoke.
            arguments: Optional dictionary of arguments to pass
                       to the tool.

        Returns:
            The tool's output as a string.

        Raises:
            RuntimeError: If not connected to a server.
            ValueError: If tool_name is empty.
            httpx.RequestError: If the request fails.
        """
        self._ensure_connected()

        if not tool_name or not tool_name.strip():
            raise ValueError("tool_name must not be empty / tool_name 不能为空")

        payload: dict[str, Any] = {"tool": tool_name}
        if arguments:
            payload["arguments"] = arguments

        response = await self._client.post("/tools/call", json=payload)
        response.raise_for_status()
        data: dict[str, Any] = response.json()
        return str(data.get("output", ""))

    async def disconnect(self) -> None:
        """断开连接。

        Closes the HTTP connection to the MCP server and resets
        the client state.
        """
        if self._client:
            await self._client.aclose()
        self._client = None
        self._connected = False
        logger.info("MCP client disconnected from %s", self._server_url)

    def _ensure_connected(self) -> None:
        """Ensure the client is connected, raising an error if not."""
        if not self._connected or self._client is None:
            raise RuntimeError(
                "MCP client is not connected. Call connect() first. / "
                "MCP 客户端未连接，请先调用 connect()。"
            )


_client_instance: MCPClient | None = None


def get_mcp_client() -> MCPClient:
    """获取 MCP 客户端单例。

    Factory function that returns a shared MCPClient singleton.
    The client must be connected via connect() before use.

    Returns:
        The shared MCPClient instance.
    """
    global _client_instance
    if _client_instance is None:
        _client_instance = MCPClient()
    return _client_instance