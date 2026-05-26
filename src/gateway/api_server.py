from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncIterator
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

from src.config import get_settings
from src.core.agent import Agent
from src.core.noop_implementations import (
    MockToolRegistry,
    NoOpMemoryStore,
    NoOpPersonaGuard,
    NoOpSkillEngine,
)
from src.core.reader import Reader
from src.gateway.api_models import (
    ApprovalAction,
    ApprovalCreateRequest,
    ApprovalCreateResponse,
    ApprovalResolveResponse,
    ChatRequest,
    ChatResponse,
    ConversationItem,
    HealthResponse,
    MessageItem,
    PaginatedResponse,
    StreamChatRequest,
)
from src.gateway.approval_helper import (
    create_approval,
    get_approval,
    resolve_approval,
)
from src.gateway.utils import error_response, format_sse_event
from src.memory.belief_store import PersistentBeliefStore
from src.models.interfaces import IModelProvider

logger = logging.getLogger(__name__)

_agent_instance: Agent | None = None
_belief_store_instance: PersistentBeliefStore | None = None


def _get_belief_store() -> PersistentBeliefStore:
    global _belief_store_instance
    if _belief_store_instance is None:
        _belief_store_instance = PersistentBeliefStore()
    return _belief_store_instance


def _build_agent_from_config() -> Agent | None:
    try:
        settings = get_settings()
        providers_cfg = settings.models.providers
        if not providers_cfg:
            logger.warning("No model providers configured, agent not available")
            return None

        for provider_name, cfg in providers_cfg.items():
            if not cfg.api_key and provider_name not in ("ollama",):
                continue
            if not cfg.model and not cfg.api_key:
                continue
            if provider_name == "dashscope":
                from src.models.dashscope import DashScopeProvider

                provider: IModelProvider = DashScopeProvider(
                    api_key=cfg.api_key,
                    base_url=cfg.base_url,
                    model=cfg.model,
                    embedding_model=cfg.embedding_model,
                )
            elif provider_name == "deepseek":
                from src.models.deepseek import DeepSeekProvider

                provider = DeepSeekProvider(
                    api_key=cfg.api_key,
                    base_url=cfg.base_url,
                    model=cfg.model,
                )
            elif provider_name == "ollama":
                from src.models.openai_compat import OllamaProvider

                provider = OllamaProvider(
                    base_url=cfg.base_url,
                    model=cfg.model,
                )
            else:
                from src.models.openai_compat import OpenAICompatProvider

                provider = OpenAICompatProvider(
                    api_key=cfg.api_key,
                    base_url=cfg.base_url,
                    model=cfg.model,
                )

            belief_store = _get_belief_store()
            reader = Reader(belief_store)

            return Agent(
                model_provider=provider,
                belief_store=belief_store,
                reader=reader,
                tool_registry=MockToolRegistry(),
                memory_store=NoOpMemoryStore(),
                persona_guard=NoOpPersonaGuard(),
                skill_engine=NoOpSkillEngine(),
            )

        logger.warning("No usable model provider found")
        return None
    except Exception:
        logger.exception("Failed to build agent from config")
        return None


def set_agent(agent: Agent) -> None:
    global _agent_instance
    _agent_instance = agent


def set_belief_store(store: PersistentBeliefStore) -> None:
    global _belief_store_instance
    _belief_store_instance = store


def _build_error_response(status_code: int, code: int, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=error_response(code, message),
    )


def create_app(
    agent: Agent | None = None,
    belief_store: PersistentBeliefStore | None = None,
) -> FastAPI:
    if agent is not None:
        set_agent(agent)
    if belief_store is not None:
        set_belief_store(belief_store)

    app = FastAPI(title="ShuyuanCore", version="1.0.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def _inject_request_id(request: Request, call_next: Any) -> Any:
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

    @app.exception_handler(Exception)
    async def _global_exception_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        req_id = getattr(request.state, "request_id", "unknown")
        logger.exception("Unhandled exception request_id=%s", req_id)
        return _build_error_response(500, 0, str(exc))

    @app.get("/health", response_model=HealthResponse)
    async def health() -> dict[str, str]:
        return {"status": "healthy", "version": "1.0.0"}

    @app.post("/api/v1/chat", response_model=ChatResponse)
    async def chat(request: ChatRequest) -> dict[str, Any]:
        agent = _agent_instance
        if agent is None:
            agent = _build_agent_from_config()
            if agent is None:
                raise HTTPException(status_code=503, detail="Agent not available")

        conversation_id = request.conversation_id or str(uuid.uuid4())

        full_response = ""
        async for token in agent.chat_stream(request.message, conversation_id):
            full_response += token

        user_belief_id = str(uuid.uuid4())
        return {
            "content": full_response,
            "conversation_id": conversation_id,
            "message_id": user_belief_id,
            "approval_required": False,
            "approval_id": None,
        }

    @app.post("/api/v1/chat/stream")
    async def chat_stream(request: StreamChatRequest) -> StreamingResponse:
        agent = _agent_instance
        if agent is None:
            agent = _build_agent_from_config()
            if agent is None:
                raise HTTPException(status_code=503, detail="Agent not available")

        conversation_id = request.conversation_id or str(uuid.uuid4())

        async def _event_generator() -> AsyncIterator[str]:
            message_id = str(uuid.uuid4())
            full_content_parts: list[str] = []
            async for token in agent.chat_stream(request.message, conversation_id):
                full_content_parts.append(token)
                yield format_sse_event("message", {"content": token})
            yield format_sse_event(
                "done",
                {
                    "conversation_id": conversation_id,
                    "message_id": message_id,
                },
            )

        return StreamingResponse(
            _event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    @app.get("/api/v1/conversations", response_model=PaginatedResponse)
    async def list_conversations(
        cursor: str | None = Query(default=None),
        limit: int = Query(default=20, ge=1, le=100),
    ) -> dict[str, Any]:
        store = _get_belief_store()
        items_raw, next_cursor, has_more = await store.get_conversation_list(
            cursor=cursor, limit=limit
        )
        items = [
            ConversationItem(
                id=item["id"],
                message_count=item["message_count"],
                last_message_at=item["last_message_at"],
                created_at=item["created_at"],
            ).model_dump()
            for item in items_raw
        ]
        return {"items": items, "next_cursor": next_cursor, "has_more": has_more}

    @app.get(
        "/api/v1/conversations/{conversation_id}/messages",
        response_model=PaginatedResponse,
    )
    async def list_messages(
        conversation_id: str,
        cursor: str | None = Query(default=None),
        limit: int = Query(default=50, ge=1, le=200),
    ) -> dict[str, Any]:
        store = _get_belief_store()
        items_raw, next_cursor, has_more = await store.get_conversation_messages(
            conversation_id=conversation_id, cursor=cursor, limit=limit
        )
        items = [
            MessageItem(
                id=item["id"],
                role=item["role"],
                content=item["content"],
                created_at=item["created_at"],
            ).model_dump()
            for item in items_raw
        ]
        return {"items": items, "next_cursor": next_cursor, "has_more": has_more}

    @app.post("/api/v1/approvals", response_model=ApprovalCreateResponse)
    async def create_approval_endpoint(
        request: ApprovalCreateRequest,
    ) -> dict[str, Any]:
        req = await create_approval(
            tool_name=request.tool_name,
            command=request.command,
            user_id=request.user_id,
        )
        return {
            "approval_id": req.approval_id,
            "status": req.status,
        }

    @app.post(
        "/api/v1/approvals/{approval_id}/approve",
        response_model=ApprovalResolveResponse,
    )
    async def approve_endpoint(
        approval_id: str,
        action: ApprovalAction,
    ) -> dict[str, Any]:
        req = get_approval(approval_id)
        if req is None:
            raise HTTPException(status_code=404, detail="Approval not found")
        resolved = await resolve_approval(
            approval_id=approval_id,
            approved=action.approved,
            reason=action.reason,
        )
        return {
            "approval_id": resolved.approval_id,
            "status": resolved.status,
            "reason": resolved.reason,
        }

    @app.post(
        "/api/v1/approvals/{approval_id}/deny",
        response_model=ApprovalResolveResponse,
    )
    async def deny_endpoint(
        approval_id: str,
        action: ApprovalAction,
    ) -> dict[str, Any]:
        req = get_approval(approval_id)
        if req is None:
            raise HTTPException(status_code=404, detail="Approval not found")
        resolved = await resolve_approval(
            approval_id=approval_id,
            approved=False,
            reason=action.reason,
        )
        return {
            "approval_id": resolved.approval_id,
            "status": resolved.status,
            "reason": resolved.reason,
        }

    return app
