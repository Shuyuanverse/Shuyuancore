from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    conversation_id: str | None = None
    mode: str = "balanced"


class StreamChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    conversation_id: str | None = None
    mode: str = "balanced"


class ChatResponse(BaseModel):
    content: str
    conversation_id: str
    message_id: str
    approval_required: bool = False
    approval_id: str | None = None


class ConversationItem(BaseModel):
    id: str
    title: str | None = None
    message_count: int
    last_message_at: int
    created_at: int


class MessageItem(BaseModel):
    id: str
    role: str
    content: str
    created_at: int


class PaginatedResponse(BaseModel):
    items: list[Any]
    next_cursor: str | None = None
    has_more: bool = False


class HealthResponse(BaseModel):
    status: str
    version: str


class ApprovalAction(BaseModel):
    approved: bool
    reason: str = ""


class ApprovalCreateRequest(BaseModel):
    tool_name: str
    command: str
    user_id: str = "default"


class ApprovalCreateResponse(BaseModel):
    approval_id: str
    status: str


class ApprovalResolveResponse(BaseModel):
    approval_id: str
    status: str
    reason: str
