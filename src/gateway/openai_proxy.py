from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from collections.abc import AsyncIterator
from typing import Any

logger = logging.getLogger(__name__)


class OpenAIProxyHandler:
    """OpenAI 兼容代理处理器。

    将 OpenAI API 格式的请求转换为 ShuyuanCore Agent 的内部调用，
    并提供 /v1/chat/completions、/v1/embeddings、/v1/models 等
    OpenAI 兼容端点。
    """

    def __init__(self, agent: Any) -> None:
        """初始化代理处理器。

        Args:
            agent: Agent 实例，用于处理聊天请求
        """
        self._agent = agent
        logger.info("OpenAIProxyHandler 初始化完成")

    async def handle_chat_completion(
        self, request: dict[str, Any]
    ) -> dict[str, Any] | AsyncIterator[str]:
        """处理 /v1/chat/completions 请求。

        支持流式（stream=True）和非流式两种模式。

        Args:
            request: OpenAI 格式的聊天补全请求

        Returns:
            dict | AsyncIterator: 非流式返回响应字典，流式返回 SSE 事件生成器

        Raises:
            ValueError: 请求格式无效时抛出
        """
        stream = request.get("stream", False)
        if stream:
            return self._handle_streaming_chat(request)

        messages = request.get("messages", [])
        if not messages:
            raise ValueError("请求中缺少 messages 字段")

        prompt = self._convert_messages(messages)
        conversation_id = request.get("conversation_id", str(uuid.uuid4()))

        full_response = ""
        async for token in self._agent.chat_stream(prompt, conversation_id):
            if isinstance(token, str):
                full_response += token

        response_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
        return {
            "id": response_id,
            "object": "chat.completion",
            "created": int(time.time()),
            "model": request.get("model", "shuyuancore"),
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": full_response,
                    },
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": len(prompt),
                "completion_tokens": len(full_response),
                "total_tokens": len(prompt) + len(full_response),
            },
        }

    async def _handle_streaming_chat(
        self, request: dict[str, Any]
    ) -> AsyncIterator[str]:
        """处理流式聊天补全请求（SSE 格式）。

        Args:
            request: OpenAI 格式的聊天补全请求

        Yields:
            str: SSE 格式的流式响应片段
        """
        messages = request.get("messages", [])
        prompt = self._convert_messages(messages)
        conversation_id = request.get("conversation_id", str(uuid.uuid4()))
        response_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"

        async for token in self._agent.chat_stream(prompt, conversation_id):
            if isinstance(token, str):
                chunk = {
                    "id": response_id,
                    "object": "chat.completion.chunk",
                    "created": int(time.time()),
                    "model": request.get("model", "shuyuancore"),
                    "choices": [
                        {
                            "index": 0,
                            "delta": {"content": token},
                            "finish_reason": None,
                        }
                    ],
                }
                yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"

        done_chunk = {
            "id": response_id,
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": request.get("model", "shuyuancore"),
            "choices": [
                {
                    "index": 0,
                    "delta": {},
                    "finish_reason": "stop",
                }
            ],
        }
        yield f"data: {json.dumps(done_chunk, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    async def handle_embeddings(self, request: dict[str, Any]) -> dict[str, Any]:
        """处理 /v1/embeddings 请求。

        Args:
            request: OpenAI 格式的嵌入请求

        Returns:
            dict: OpenAI 兼容的嵌入响应

        Raises:
            ValueError: 请求格式无效时抛出
        """
        input_data = request.get("input", "")
        if not input_data:
            raise ValueError("请求中缺少 input 字段")

        texts = input_data if isinstance(input_data, list) else [input_data]
        model = request.get("model", "shuyuancore-embedding")

        data_entries = []
        total_tokens = 0

        for idx, text in enumerate(texts):
            try:
                embedding = await self._agent._model_provider.embed(text)
                tokens_used = len(text)
                total_tokens += tokens_used
                data_entries.append(
                    {
                        "object": "embedding",
                        "index": idx,
                        "embedding": embedding,
                    }
                )
            except Exception:
                logger.exception("embedding 生成失败 index=%d", idx)
                data_entries.append(
                    {
                        "object": "embedding",
                        "index": idx,
                        "embedding": [0.0] * 768,
                    }
                )

        return {
            "object": "list",
            "data": data_entries,
            "model": model,
            "usage": {
                "prompt_tokens": total_tokens,
                "total_tokens": total_tokens,
            },
        }

    async def handle_models(self) -> dict[str, Any]:
        """处理 /v1/models 请求，返回可用模型列表。

        Returns:
            dict: OpenAI 兼容的模型列表响应
        """
        model_name = "shuyuancore"
        try:
            provider_model = getattr(self._agent._model_provider, "model", None)
            if provider_model:
                model_name = provider_model
        except Exception:
            pass

        return {
            "object": "list",
            "data": [
                {
                    "id": model_name,
                    "object": "model",
                    "created": int(time.time()),
                    "owned_by": "shuyuancore",
                }
            ],
        }

    def _convert_messages(self, openai_messages: list[dict[str, Any]]) -> str:
        """将 OpenAI 格式的消息列表转换为 ShuyuanCore 的纯文本 prompt。

        支持 system、user、assistant 三种角色，按照对话顺序拼接。

        Args:
            openai_messages: OpenAI 格式的消息列表

        Returns:
            str: 拼接后的纯文本 prompt
        """
        parts: list[str] = []
        for msg in openai_messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")

            if isinstance(content, list):
                text_parts: list[str] = []
                for item in content:
                    if isinstance(item, dict):
                        if item.get("type") == "text":
                            text_parts.append(item.get("text", ""))
                        elif item.get("type") == "image_url":
                            text_parts.append("[图片]")
                    else:
                        text_parts.append(str(item))
                content = " ".join(text_parts)

            if role == "system":
                parts.append(f"系统指令: {content}")
            elif role == "user":
                parts.append(f"用户: {content}")
            elif role == "assistant":
                parts.append(f"助手: {content}")
            else:
                parts.append(f"{role}: {content}")

        return "\n".join(parts)