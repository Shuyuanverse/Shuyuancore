from __future__ import annotations

import logging
import threading
from typing import Any

from src.tools.interfaces import ToolResult
from src.tools.registry import get_tool_registry

logger = logging.getLogger(__name__)


class MCPServer:
    """MCP 服务器（Model Context Protocol）。

    Hosts tools and exposes them via HTTP for remote MCP clients.
    Uses FastAPI + uvicorn for the HTTP layer.
    All tool executions go through ToolRegistry for validation,
    approval gating, and audit logging.
    """

    def __init__(self) -> None:
        self._tools: dict[str, object] = {}
        self._app: Any = None
        self._server: Any = None
        self._thread: threading.Thread | None = None

    def register_tool(self, tool: object) -> None:
        """注册工具。

        Registers an ITool-compatible tool with the MCP server,
        making it available for remote invocation.

        Args:
            tool: An instance of ITool to register.

        Raises:
            ValueError: If a tool with the same name already exists.
        """
        spec = tool.get_spec()
        if spec.name in self._tools:
            raise ValueError(
                f"Tool '{spec.name}' is already registered / "
                f"工具 '{spec.name}' 已注册"
            )
        self._tools[spec.name] = tool
        registry = get_tool_registry()
        registry.register(tool)
        logger.info(
            "MCP tool registered: %s (category: %s)",
            spec.name,
            spec.category,
        )

    def list_tools(self) -> list[dict[str, Any]]:
        """列出已注册工具。

        Returns a list of tool specifications as serializable
        dictionaries for the MCP protocol.

        Returns:
            List of tool definition dictionaries.
        """
        return [
            {
                "name": spec.name,
                "description": spec.description,
                "category": spec.category,
                "dangerous": spec.dangerous,
                "require_approval": spec.require_approval,
                "parameters": [
                    {
                        "name": p.name,
                        "type": p.type,
                        "description": p.description,
                        "required": p.required,
                        "default": p.default,
                    }
                    for p in spec.parameters
                ],
            }
            for spec in get_tool_registry().list_tools()
        ]

    async def handle_request(
        self,
        request: dict[str, Any],
        user_id: str = "mcp-client",
    ) -> ToolResult:
        """处理工具调用请求。

        Routes an incoming MCP request through the ToolRegistry
        for validation, approval gating, and audit logging.

        Args:
            request: A dictionary containing 'tool' (the tool name)
                     and optionally 'arguments' (dict of parameters).
            user_id: The user ID for approval and audit context.

        Returns:
            ToolResult from the executed tool.

        Raises:
            ValueError: If the requested tool is not registered.
        """
        tool_name = request.get("tool", "")
        arguments = request.get("arguments", {})

        registry = get_tool_registry()
        if registry.get_tool(tool_name) is None:
            raise ValueError(
                f"Tool '{tool_name}' not found / 工具 '{tool_name}' 未注册"
            )

        logger.info(
            "MCP handling request for tool: %s with args: %s",
            tool_name,
            arguments,
        )
        return await registry.execute_tool(tool_name, arguments, user_id)

    async def start(self, host: str = "127.0.0.1", port: int = 8000) -> None:
        """启动 HTTP 服务器。

        Starts the FastAPI + uvicorn HTTP server in a background
        thread to serve MCP requests.

        Args:
            host: The host interface to bind to (default: 127.0.0.1).
            port: The port to listen on (default: 8000).
        """
        try:
            from fastapi import FastAPI, HTTPException
            from fastapi.responses import JSONResponse
        except ImportError:
            raise ImportError(
                "FastAPI is required to start the MCP server. "
                "Install it with: pip install fastapi uvicorn"
            )

        app = FastAPI(title="MCP Server", version="1.0.0")
        self._app = app

        @app.get("/health")
        async def health_check():
            return {"status": "ok", "tools_count": len(self._tools)}

        @app.get("/tools")
        async def list_tools_endpoint():
            return {"tools": self.list_tools()}

        @app.post("/tools/call")
        async def call_tool_endpoint(request: dict[str, Any]):
            try:
                result = await self.handle_request(request)
                return JSONResponse(
                    content={
                        "success": result.success,
                        "output": result.data if result.success else result.error,
                        "error": result.error,
                    }
                )
            except ValueError as e:
                raise HTTPException(status_code=404, detail=str(e))
            except Exception as e:
                logger.exception("MCP tool call failed")
                raise HTTPException(status_code=500, detail=str(e))

        self._run_server(app, host, port)

    def _run_server(
        self,
        app: Any,
        host: str,
        port: int,
    ) -> None:
        """Run the uvicorn server in a background thread.

        Args:
            app: The FastAPI application instance.
            host: The host interface to bind to.
            port: The port to listen on.
        """
        import uvicorn

        config = uvicorn.Config(
            app=app,
            host=host,
            port=port,
            log_level="info",
        )
        self._server = uvicorn.Server(config)

        self._thread = threading.Thread(
            target=self._server.run,
            daemon=True,
        )
        self._thread.start()
        logger.info("MCP server started on http://%s:%d", host, port)

    async def stop(self) -> None:
        """停止服务器。

        Gracefully stops the uvicorn server and cleans up
        resources.
        """
        if self._server:
            self._server.should_exit = True
            self._server = None
        self._app = None
        if self._thread:
            self._thread.join(timeout=5.0)
            self._thread = None
        logger.info("MCP server stopped")


_server_instance: MCPServer | None = None


def get_mcp_server() -> MCPServer:
    """获取 MCP 服务器单例。

    Factory function that returns a shared MCPServer singleton.
    Tools must be registered before starting the server.

    Returns:
        The shared MCPServer instance.
    """
    global _server_instance
    if _server_instance is None:
        _server_instance = MCPServer()
    return _server_instance
