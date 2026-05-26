from __future__ import annotations

from pathlib import Path

import pytest

from src.memory.core_memory import CoreMemory


class TestCoreMemory:

    @pytest.mark.asyncio
    async def test_load_creates_empty_files(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
    ) -> None:
        monkeypatch.setattr("src.memory.core_memory._MEMORY_DIR", tmp_path)
        cm = CoreMemory()

        result = await cm.load("test_user")

        assert result["memory_md"] == ""
        assert result["user_md"] == ""

        memory_file = tmp_path / "test_user" / "MEMORY.md"
        user_file = tmp_path / "test_user" / "USER.md"
        assert memory_file.exists()
        assert user_file.exists()

    @pytest.mark.asyncio
    async def test_read_write_roundtrip(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
    ) -> None:
        monkeypatch.setattr("src.memory.core_memory._MEMORY_DIR", tmp_path)
        cm = CoreMemory()

        await cm.save("user_a", "Some core memory content", "memory")
        await cm.save("user_a", "Some user model content", "user")

        result = await cm.load("user_a")
        assert result["memory_md"] == "Some core memory content\n"
        assert result["user_md"] == "Some user model content\n"

    @pytest.mark.asyncio
    async def test_save_appends_to_existing(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
    ) -> None:
        monkeypatch.setattr("src.memory.core_memory._MEMORY_DIR", tmp_path)
        cm = CoreMemory()

        await cm.save("user_b", "line1\n", "memory")
        await cm.save("user_b", "line2\n", "memory")

        result = await cm.load("user_b")
        assert result["memory_md"] == "line1\nline2\n"

    @pytest.mark.asyncio
    async def test_injection_script_tag_rejected(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
    ) -> None:
        monkeypatch.setattr("src.memory.core_memory._MEMORY_DIR", tmp_path)
        cm = CoreMemory()

        await cm.save("victim", "normal content", "memory")
        await cm.save("victim", '<script>alert("xss")</script>', "memory")

        result = await cm.load("victim")
        assert '<script>' not in result["memory_md"]
        assert result["memory_md"] == "normal content\n"

    @pytest.mark.asyncio
    async def test_injection_select_rejected(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
    ) -> None:
        monkeypatch.setattr("src.memory.core_memory._MEMORY_DIR", tmp_path)
        cm = CoreMemory()

        await cm.save("victim2", "safe content", "user")
        await cm.save("victim2", "SELECT * FROM users", "user")

        result = await cm.load("victim2")
        assert "SELECT" not in result["user_md"]
        assert result["user_md"] == "safe content\n"

    @pytest.mark.asyncio
    async def test_injection_drop_rejected(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
    ) -> None:
        monkeypatch.setattr("src.memory.core_memory._MEMORY_DIR", tmp_path)
        cm = CoreMemory()

        await cm.save("victim3", "safe", "memory")
        await cm.save("victim3", "DROP TABLE beliefs;", "memory")

        result = await cm.load("victim3")
        assert "DROP" not in result["memory_md"]
        assert result["memory_md"] == "safe\n"

    @pytest.mark.asyncio
    async def test_injection_sql_comment_rejected(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
    ) -> None:
        monkeypatch.setattr("src.memory.core_memory._MEMORY_DIR", tmp_path)
        cm = CoreMemory()

        await cm.save("victim4", "normal", "user")
        await cm.save("victim4", "admin' --", "user")

        result = await cm.load("victim4")
        assert result["user_md"] == "normal\n"

    @pytest.mark.asyncio
    async def test_system_prompt_both_present(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
    ) -> None:
        monkeypatch.setattr("src.memory.core_memory._MEMORY_DIR", tmp_path)
        cm = CoreMemory()

        await cm.save("sp_user", "Agent name is ShuyuanCore", "memory")
        await cm.save("sp_user", "User prefers concise answers", "user")

        prompt = await cm.get_system_prompt("sp_user")
        assert "--- Core Memory ---" in prompt
        assert "Agent name is ShuyuanCore" in prompt
        assert "--- User Model ---" in prompt
        assert "User prefers concise answers" in prompt

    @pytest.mark.asyncio
    async def test_system_prompt_empty(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
    ) -> None:
        monkeypatch.setattr("src.memory.core_memory._MEMORY_DIR", tmp_path)
        cm = CoreMemory()

        prompt = await cm.get_system_prompt("empty_user")
        assert prompt == ""

    @pytest.mark.asyncio
    async def test_system_prompt_only_memory(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
    ) -> None:
        monkeypatch.setattr("src.memory.core_memory._MEMORY_DIR", tmp_path)
        cm = CoreMemory()

        await cm.save("mem_only", "Just some memory", "memory")

        prompt = await cm.get_system_prompt("mem_only")
        assert "--- Core Memory ---" in prompt
        assert "Just some memory" in prompt
        assert "--- User Model ---" not in prompt

    @pytest.mark.asyncio
    async def test_auto_compress_memory_exceeds_threshold(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
    ) -> None:
        monkeypatch.setattr("src.memory.core_memory._MEMORY_DIR", tmp_path)
        cm = CoreMemory()
        assert cm.config.core_memory_limit == 2200
        assert cm.config.consolidation_threshold == 0.8
        threshold = int(2200 * 0.8)

        long_content = "A" * (threshold + 100)
        await cm.save("compress_me", long_content, "memory")

        async def mock_llm(text: str) -> str:
            return "Compressed summary of core memory."

        compressed = await cm.auto_compress("compress_me", mock_llm)
        assert compressed is True

        result = await cm.load("compress_me")
        assert result["memory_md"] == "Compressed summary of core memory."

    @pytest.mark.asyncio
    async def test_auto_compress_below_threshold(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
    ) -> None:
        monkeypatch.setattr("src.memory.core_memory._MEMORY_DIR", tmp_path)
        cm = CoreMemory()
        threshold = int(2200 * 0.8)

        short_content = "B" * (threshold - 50)
        await cm.save("no_compress", short_content, "memory")

        async def mock_llm(text: str) -> str:
            return "Should not be called"

        compressed = await cm.auto_compress("no_compress", mock_llm)
        assert compressed is False

        result = await cm.load("no_compress")
        assert result["memory_md"] == short_content + "\n"

    @pytest.mark.asyncio
    async def test_auto_compress_user_exceeds_threshold(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
    ) -> None:
        monkeypatch.setattr("src.memory.core_memory._MEMORY_DIR", tmp_path)
        cm = CoreMemory()
        assert cm.config.user_model_limit == 1375
        threshold = int(1375 * 0.8)

        long_content = "C" * (threshold + 50)
        await cm.save("user_compress", long_content, "user")

        async def mock_llm(text: str) -> str:
            return "Compressed user model."

        compressed = await cm.auto_compress("user_compress", mock_llm)
        assert compressed is True

        result = await cm.load("user_compress")
        assert result["user_md"] == "Compressed user model."

    @pytest.mark.asyncio
    async def test_auto_compress_no_files_returns_false(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
    ) -> None:
        monkeypatch.setattr("src.memory.core_memory._MEMORY_DIR", tmp_path)
        cm = CoreMemory()

        async def mock_llm(text: str) -> str:
            return ""

        compressed = await cm.auto_compress("ghost", mock_llm)
        assert compressed is False

    @pytest.mark.asyncio
    async def test_load_preserves_existing_content(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
    ) -> None:
        monkeypatch.setattr("src.memory.core_memory._MEMORY_DIR", tmp_path)

        user_dir = tmp_path / "existing_user"
        user_dir.mkdir(parents=True)
        (user_dir / "MEMORY.md").write_text("Existing memory content", encoding="utf-8")
        (user_dir / "USER.md").write_text("Existing user content", encoding="utf-8")

        cm = CoreMemory()
        result = await cm.load("existing_user")
        assert result["memory_md"] == "Existing memory content"
        assert result["user_md"] == "Existing user content"

    @pytest.mark.asyncio
    async def test_isolation_between_users(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
    ) -> None:
        monkeypatch.setattr("src.memory.core_memory._MEMORY_DIR", tmp_path)
        cm = CoreMemory()

        await cm.save("alice", "Alice memory", "memory")
        await cm.save("bob", "Bob memory", "memory")

        alice_data = await cm.load("alice")
        bob_data = await cm.load("bob")
        assert alice_data["memory_md"] == "Alice memory\n"
        assert bob_data["memory_md"] == "Bob memory\n"
