from __future__ import annotations

import asyncio
import logging
import time
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
from src.gateway.utils import error_response, format_sse_event, set_cursor_secret
from src.memory.belief_store import PersistentBeliefStore
from src.models.interfaces import IModelProvider

logger = logging.getLogger(__name__)

_WHITELIST_PATHS: frozenset[str] = frozenset(
    {"/health", "/docs", "/openapi.json", "/redoc", "/favicon.ico"}
)
_rate_limit_buckets: dict[str, tuple[float, float]] = {}
_rate_limit_lock = asyncio.Lock()

_agent_instance: Agent | None = None
_belief_store_instance: PersistentBeliefStore | None = None
_active_streams: dict[str, asyncio.Event] = {}
_stream_lock = asyncio.Lock()


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


def _extract_user_id(request: Request) -> str:
    x_user_id = request.headers.get("X-User-ID")
    if x_user_id:
        return x_user_id

    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        token = auth[7:]
        settings = get_settings()
        api_keys = getattr(settings.security, "api_keys", [])
        for entry in api_keys:
            if entry.get("key") == token:
                return entry.get("user_id", "default")
        return f"token:{token[:8]}"

    return "anonymous"


def _check_rate_limit(user_id: str, rpm: int) -> bool:
    now = time.monotonic()
    key = user_id
    if key not in _rate_limit_buckets:
        _rate_limit_buckets[key] = (float(rpm) - 1.0, now)
        return True
    tokens, last_refill = _rate_limit_buckets[key]
    elapsed = now - last_refill
    tokens = min(float(rpm), tokens + elapsed * (rpm / 60.0))
    if tokens >= 1.0:
        _rate_limit_buckets[key] = (tokens - 1.0, now)
        return True
    _rate_limit_buckets[key] = (tokens, now)
    return False


def create_app(
    agent: Agent | None = None,
    belief_store: PersistentBeliefStore | None = None,
) -> FastAPI:
    if agent is not None:
        set_agent(agent)
    if belief_store is not None:
        set_belief_store(belief_store)

    app = FastAPI(title="ShuyuanCore", version="1.0.0")

    @app.on_event("startup")
    async def _notify_systemd():
        try:
            from systemd import daemon as sd_daemon  # type: ignore[import-untyped]
            sd_daemon.notify("READY=1")
            logger.info("systemd notification sent: READY=1")
        except ImportError:
            logger.debug("systemd-python not available, skipping sd_notify")
        except Exception:
            logger.exception("systemd notification failed")

    settings = get_settings()
    if settings.security.cursor_secret:
        set_cursor_secret(settings.security.cursor_secret)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.security.allowed_origins or ["http://localhost:3000"],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "X-User-ID"],
    )

    @app.middleware("http")
    async def _guard(request: Request, call_next: Any) -> Any:
        path = request.url.path
        if (
            path in _WHITELIST_PATHS
            or path.startswith("/docs")
            or path.startswith("/openapi")
        ):
            return await call_next(request)

        user_id = _extract_user_id(request)
        request.state.user_id = user_id

        settings = get_settings()
        rpm = settings.security.rate_limit_per_minute
        if rpm > 0:
            async with _rate_limit_lock:
                if not _check_rate_limit(user_id, rpm):
                    return JSONResponse(
                        status_code=429,
                        content={
                            "error": {"code": 429, "message": "Rate limit exceeded"}
                        },
                        headers={"Retry-After": "60", "X-User-ID": user_id},
                    )

        return await call_next(request)

    @app.middleware("http")
    async def _inject_context(request: Request, call_next: Any) -> Any:
        request_id = str(uuid.uuid4())
        user_id = getattr(request.state, "user_id", None) or _extract_user_id(request)
        request.state.request_id = request_id
        request.state.user_id = user_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-User-ID"] = user_id
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
        db_status = "disconnected"
        try:
            store = _get_belief_store()
            store._db  # access to check if initialized
            db_status = "connected"
        except Exception:
            pass
        return {
            "status": "healthy",
            "version": "1.0.0",
            "database": db_status,
        }

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
            if isinstance(token, str):
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
    async def chat_stream(
        request: StreamChatRequest, req: Request
    ) -> StreamingResponse:
        agent = _agent_instance
        if agent is None:
            agent = _build_agent_from_config()
            if agent is None:
                raise HTTPException(status_code=503, detail="Agent not available")

        conversation_id = request.conversation_id or str(uuid.uuid4())
        user_id = getattr(req.state, "user_id", "anonymous")
        stream_id = f"{user_id}_{uuid.uuid4().hex[:8]}"

        resume_event = asyncio.Event()
        async with _stream_lock:
            _active_streams[stream_id] = resume_event

        async def _event_generator() -> AsyncIterator[str]:
            try:
                message_id = str(uuid.uuid4())
                async for chunk in agent.chat_stream(
                    request.message, conversation_id, resume_event=resume_event
                ):
                    if isinstance(chunk, dict) and chunk.get("type") == "approval":
                        approval_id = chunk.get("approval_id", stream_id)
                        approval_data = {
                            "type": "approval",
                            "approval_id": approval_id,
                            "stream_id": stream_id,
                            "tool_name": chunk.get("tool_name", ""),
                            "message": chunk.get("message", "需要审批"),
                        }
                        yield format_sse_event("approval", approval_data)
                        await resume_event.wait()
                        resume_event.clear()
                    elif isinstance(chunk, dict):
                        yield format_sse_event("message", chunk)
                    else:
                        yield format_sse_event("message", {"content": chunk})
                yield format_sse_event(
                    "done",
                    {
                        "conversation_id": conversation_id,
                        "message_id": message_id,
                    },
                )
            except Exception:
                logger.exception("sse_stream_error stream_id=%s", stream_id)
                yield format_sse_event("error", {"detail": "stream error"})
            finally:
                async with _stream_lock:
                    _active_streams.pop(stream_id, None)

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
        req: Request,
        cursor: str | None = Query(default=None),
        limit: int = Query(default=20, ge=1, le=100),
    ) -> dict[str, Any]:
        user_id = getattr(req.state, "user_id", "anonymous")
        store = _get_belief_store()
        items_raw, next_cursor, has_more = await store.get_conversation_list(
            user_id=user_id, cursor=cursor, limit=limit
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
        req: Request,
        cursor: str | None = Query(default=None),
        limit: int = Query(default=50, ge=1, le=200),
    ) -> dict[str, Any]:
        user_id = getattr(req.state, "user_id", "anonymous")
        store = _get_belief_store()
        items_raw, next_cursor, has_more = await store.get_conversation_messages(
            conversation_id=conversation_id,
            user_id=user_id,
            cursor=cursor,
            limit=limit,
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
        req: Request,
    ) -> dict[str, Any]:
        user_id = getattr(req.state, "user_id", request.user_id)
        result = await create_approval(
            tool_name=request.tool_name,
            command=request.command,
            user_id=user_id,
        )
        return {
            "approval_id": result.approval_id,
            "status": result.status,
        }

    @app.post(
        "/api/v1/approvals/{approval_id}/approve",
        response_model=ApprovalResolveResponse,
    )
    async def approve_endpoint(
        approval_id: str,
        action: ApprovalAction,
    ) -> dict[str, Any]:
        existing = await get_approval(approval_id)
        if existing is None:
            raise HTTPException(status_code=404, detail="Approval not found")
        resolved = await resolve_approval(
            approval_id=approval_id,
            approved=True,
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
        existing = await get_approval(approval_id)
        if existing is None:
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

    async def _resume_stream_if_pending(stream_id: str, approved: bool) -> bool:
        async with _stream_lock:
            event = _active_streams.get(stream_id)
        if event is not None and not event.is_set():
            if _agent_instance is not None:
                _agent_instance._approval_approved = approved
            event.set()
            return True
        return False

    @app.post("/api/v1/approvals/{approval_id}/resume")
    async def resume_approval_stream(approval_id: str, req: Request) -> dict[str, Any]:
        stream_id = req.query_params.get("stream_id", approval_id)
        approved = req.query_params.get("approved", "true").lower() == "true"

        resumed = await _resume_stream_if_pending(stream_id, approved)

        if not resumed:
            raise HTTPException(status_code=404, detail="No pending stream found for this ID")

        return {
            "approval_id": approval_id,
            "stream_id": stream_id,
            "resumed": True,
            "approved": approved,
        }

    return app
