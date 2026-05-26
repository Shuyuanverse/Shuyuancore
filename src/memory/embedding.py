from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class EmbeddingService:

    def __init__(self, model_provider: Any | None = None) -> None:
        self._provider = model_provider

    async def embed(self, text: str) -> list[float] | None:
        if self._provider is None:
            return None

        for attempt in range(2):
            try:
                result = await self._provider.embed([text])
                if result.vectors and len(result.vectors) > 0:
                    return result.vectors[0]
            except Exception:
                if attempt == 0:
                    continue
                logger.warning(
                    "embedding_failed_after_retry text_preview=%s",
                    text[:60],
                )
        return None
