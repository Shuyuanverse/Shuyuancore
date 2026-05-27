from __future__ import annotations

from typing import Any

import pytest

from src.skills.extractor import _extraction_lock, extract_skill


class TestExtractionLock:

    @pytest.mark.asyncio
    async def test_lock_skips_when_another_extraction_running(self) -> None:
        await _extraction_lock.acquire()
        try:
            result = await extract_skill(
                "test", "msg", "rsp", MockStore(), MockStore(), MockStore(),
            )
            assert result is None
        finally:
            _extraction_lock.release()

    @pytest.mark.asyncio
    async def test_lock_idle_when_no_extraction(self) -> None:
        assert not _extraction_lock.locked()

    @pytest.mark.asyncio
    async def test_extraction_releases_lock(self) -> None:
        assert not _extraction_lock.locked()


class MockStore:
    async def get(self, conv: str, limit: int = 50) -> list[Any]:
        return []
    async def list_skills(self, *args: Any, **kwargs: Any) -> list[Any]:
        return []
