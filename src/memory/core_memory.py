from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Awaitable, Callable, Literal

from src.config import MemoryConfig, get_settings

logger = logging.getLogger(__name__)

_INJECTION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"<script", re.IGNORECASE),
    re.compile(r"\bSELECT\b", re.IGNORECASE),
    re.compile(r"\bDROP\b", re.IGNORECASE),
    re.compile(r"--"),
]

_MEMORY_DIR = Path("data/memories")


class CoreMemory:

    def __init__(self, config: MemoryConfig | None = None) -> None:
        self._config: MemoryConfig = config or get_settings().memory

    @property
    def config(self) -> MemoryConfig:
        return self._config

    def _user_dir(self, user_id: str) -> Path:
        return _MEMORY_DIR / user_id

    def _memory_file(self, user_id: str) -> Path:
        return self._user_dir(user_id) / "MEMORY.md"

    def _user_file(self, user_id: str) -> Path:
        return self._user_dir(user_id) / "USER.md"

    @staticmethod
    def _check_injection(content: str) -> bool:
        for pattern in _INJECTION_PATTERNS:
            if pattern.search(content):
                return True
        return False

    async def load(self, user_id: str) -> dict[str, str]:
        user_dir = self._user_dir(user_id)
        user_dir.mkdir(parents=True, exist_ok=True)

        memory_path = self._memory_file(user_id)
        if not memory_path.exists():
            memory_path.write_text("", encoding="utf-8")
            logger.info("Created empty MEMORY.md for user %s", user_id)

        user_path = self._user_file(user_id)
        if not user_path.exists():
            user_path.write_text("", encoding="utf-8")
            logger.info("Created empty USER.md for user %s", user_id)

        return {
            "memory_md": memory_path.read_text(encoding="utf-8"),
            "user_md": user_path.read_text(encoding="utf-8"),
        }

    async def save(
        self,
        user_id: str,
        content: str,
        mem_type: Literal["memory", "user"],
    ) -> None:
        if self._check_injection(content):
            logger.warning(
                "Injection pattern detected in %s save for user %s, content rejected",
                mem_type,
                user_id,
            )
            return

        if mem_type == "memory":
            file_path = self._memory_file(user_id)
        else:
            file_path = self._user_file(user_id)

        file_path.parent.mkdir(parents=True, exist_ok=True)

        with file_path.open("a", encoding="utf-8") as f:
            f.write(content)
            if not content.endswith("\n"):
                f.write("\n")

        logger.debug("Appended to %s for user %s (%d chars)", mem_type, user_id, len(content))

    async def get_system_prompt(self, user_id: str) -> str:
        data = await self.load(user_id)
        parts: list[str] = []

        if data["memory_md"].strip():
            parts.append("--- Core Memory ---")
            parts.append(data["memory_md"].strip())

        if data["user_md"].strip():
            parts.append("--- User Model ---")
            parts.append(data["user_md"].strip())

        return "\n\n".join(parts)

    async def auto_compress(
        self,
        user_id: str,
        llm_compress: Callable[[str], Awaitable[str]],
    ) -> bool:
        data = await self.load(user_id)
        compressed = False

        memory_path = self._memory_file(user_id)
        user_path = self._user_file(user_id)

        memory_limit = self._config.core_memory_limit
        user_limit = self._config.user_model_limit
        threshold = self._config.consolidation_threshold

        memory_threshold = int(memory_limit * threshold)
        user_threshold = int(user_limit * threshold)

        if data["memory_md"] and len(data["memory_md"]) > memory_threshold:
            original = data["memory_md"]
            compressed_text = await llm_compress(original)
            memory_path.write_text(compressed_text, encoding="utf-8")
            logger.info(
                "Compressed MEMORY.md for user %s: %d -> %d chars",
                user_id,
                len(original),
                len(compressed_text),
            )
            compressed = True

        if data["user_md"] and len(data["user_md"]) > user_threshold:
            original = data["user_md"]
            compressed_text = await llm_compress(original)
            user_path.write_text(compressed_text, encoding="utf-8")
            logger.info(
                "Compressed USER.md for user %s: %d -> %d chars",
                user_id,
                len(original),
                len(compressed_text),
            )
            compressed = True

        return compressed
