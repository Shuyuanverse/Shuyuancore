# Copyright 2026 ShuyuanCore contributors
# SPDX-License-Identifier: Apache-2.0

"""自演化模块管理器 — 生/融/灭生命周期管理。

功能：
- 生（Birth）：从成功执行轨迹创建新模块
- 融（Fusion）：合并两个协作为频繁的模块
- 灭（Death）：归档长期未使用的模块
"""

from __future__ import annotations

import logging
import sqlite3
import time
import uuid
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from src.config import EvolutionConfig
    from src.core.interfaces import IBeliefStore
    from src.persona.dialogue.agents import ReviewAgent

from src.config import get_settings
from src.models.provider import get_model_provider

logger = logging.getLogger(__name__)


class ModuleManager:
    """模块生命周期管理器。

    职责：
    - 从任务执行轨迹生成模块 prompt
    - 融合协作频繁的模块
    - 归档长期未使用的模块
    - 质量门控（通过 ReviewAgent）
    """

    def __init__(
        self,
        db_path: str,
        belief_store: "IBeliefStore",
        review_agent: "ReviewAgent",
        config: Optional["EvolutionConfig"] = None,
        llm: Any | None = None,
    ) -> None:
        """初始化模块管理器。

        Args:
            db_path: SQLite 数据库路径
            belief_store: 信念存储后端
            review_agent: 审查 Agent 用于质量门控
            config: 演化配置
            llm: 可选 LLM 提供者；未传入时从配置加载
        """
        self.db_path = db_path
        self.belief_store = belief_store
        self.review_agent = review_agent
        self.config = config or get_settings().evolution
        self.llm = llm if llm is not None else get_model_provider()

    async def create_module(
        self,
        name: str,
        task_type: str,
        execution_trajectory: str,
    ) -> str:
        """生：从成功执行轨迹创建新模块。

        Args:
            name: 模块名称
            task_type: 任务类型
            execution_trajectory: 执行轨迹（包含多轮对话和工具调用）

        Returns:
            str: 新创建的模块 ID

        Raises:
            ValueError: 当生成的 prompt 质量不达标时
        """
        logger.info("Creating module: %s (type=%s)", name, task_type)

        # 1. 生成 prompt 文本
        prompt = await self._generate_prompt(execution_trajectory)

        # 2. 质量门控
        quality = await self.review_agent.review_prompt(prompt)
        logger.debug("Module %s initial quality score: %.2f", name, quality)

        if quality < 0.7:
            # 重试一次
            logger.info("Retrying module generation for %s", name)
            prompt = await self._generate_prompt(execution_trajectory, regenerate=True)
            quality = await self.review_agent.review_prompt(prompt)
            logger.debug("Module %s retry quality score: %.2f", name, quality)

            if quality < 0.7:
                raise ValueError(
                    f"Failed to generate acceptable prompt for module {name} "
                    f"(quality={quality:.2f}, threshold=0.7)"
                )

        # 3. 分配 memory_partition
        memory_partition = f"module_{uuid.uuid4().hex[:8]}"
        module_id = uuid.uuid4().hex
        now_ms = int(time.time() * 1000)

        # 4. 插入数据库
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO evolution_modules
                (id, name, prompt_text, memory_partition, task_type, trigger_count, status, created_at)
            VALUES (?, ?, ?, ?, ?, 0, 'active', ?)
            """,
            (module_id, name, prompt, memory_partition, task_type, now_ms),
        )
        conn.commit()
        conn.close()

        logger.info(
            "Created module: %s (id=%s, partition=%s, quality=%.2f)",
            name,
            module_id,
            memory_partition,
            quality,
        )
        return module_id

    async def _generate_prompt(self, trajectory: str, regenerate: bool = False) -> str:
        """调用 LLM 生成模块 prompt。

        Args:
            trajectory: 执行轨迹
            regenerate: 是否为重试生成

        Returns:
            str: 生成的模块 prompt
        """
        if regenerate:
            system = (
                "你是一个模块生成器。根据以下任务执行轨迹，生成一个可复用的提示词，"
                "用于指导未来的类似任务。这是重试生成，请改进之前的版本。"
            )
        else:
            system = (
                "你是一个模块生成器。根据以下任务执行轨迹，生成一个可复用的提示词，"
                "用于指导未来的类似任务。"
            )

        user = f"执行轨迹：\n{trajectory}"

        # 调用 LLM 生成
        response = await self.llm.chat(
            history=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.7,
        )
        return response.content.strip()

    async def fuse_modules(self, module_a_id: str, module_b_id: str) -> str:
        """融：合并两个模块为复合模块。

        Args:
            module_a_id: 模块 A ID
            module_b_id: 模块 B ID

        Returns:
            str: 新创建的融合模块 ID

        Raises:
            ValueError: 当模块不存在或融合质量不达标时
        """
        logger.info("Fusing modules: %s + %s", module_a_id, module_b_id)

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # 1. 读取两个模块的 prompt
        cursor.execute(
            "SELECT name, prompt_text FROM evolution_modules WHERE id = ?", (module_a_id,)
        )
        a = cursor.fetchone()
        cursor.execute(
            "SELECT name, prompt_text FROM evolution_modules WHERE id = ?", (module_b_id,)
        )
        b = cursor.fetchone()

        if not a or not b:
            conn.close()
            raise ValueError("Module not found")

        a_name, a_prompt = a
        b_name, b_prompt = b

        # 2. 合并 prompt
        system = (
            "你是一个模块融合器。请将下面两个模块的提示词合并成一个更强大的提示词，"
            "保留两者优点，消除冗余，形成有机的整体。"
        )
        user = f"模块 A（{a_name}）：\n{a_prompt}\n\n模块 B（{b_name}）：\n{b_prompt}"

        merged_prompt_response = await self.llm.chat(
            history=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.5,
        )
        merged_prompt = merged_prompt_response.content.strip()

        # 3. 质量门控
        quality = await self.review_agent.review_prompt(merged_prompt)
        logger.debug("Fused module quality score: %.2f", quality)

        if quality < 0.7:
            conn.close()
            raise ValueError(
                f"Fused module quality insufficient (quality={quality:.2f}, threshold=0.7)"
            )

        # 4. 创建新模块
        new_name = f"{a_name}_{b_name}_fused"
        module_id = uuid.uuid4().hex
        memory_partition = f"module_{uuid.uuid4().hex[:8]}"
        now_ms = int(time.time() * 1000)

        cursor.execute(
            """
            INSERT INTO evolution_modules
                (id, name, prompt_text, memory_partition, trigger_count, status, created_at)
            VALUES (?, ?, ?, ?, 0, 'active', ?)
            """,
            (module_id, new_name, merged_prompt, memory_partition, now_ms),
        )

        # 5. 归档旧模块
        cursor.execute(
            "UPDATE evolution_modules SET status = 'archived', archived_at = ? WHERE id IN (?, ?)",
            (now_ms, module_a_id, module_b_id),
        )

        conn.commit()
        conn.close()

        logger.info(
            "Fused modules: %s + %s -> %s (id=%s, quality=%.2f)",
            a_name,
            b_name,
            new_name,
            module_id,
            quality,
        )
        return module_id

    async def archive_module(self, module_id: str) -> None:
        """灭：归档模块。

        Args:
            module_id: 模块 ID
        """
        logger.info("Archiving module: %s", module_id)

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        now_ms = int(time.time() * 1000)

        cursor.execute(
            "UPDATE evolution_modules SET status = 'archived', archived_at = ? WHERE id = ?",
            (now_ms, module_id),
        )

        conn.commit()
        conn.close()

        logger.info("Archived module: %s", module_id)

    async def get_active_modules(self) -> List[Dict[str, Any]]:
        """获取所有活跃模块。

        Returns:
            list[dict]: 活跃模块列表
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute(
            "SELECT * FROM evolution_modules WHERE status = 'active' ORDER BY created_at DESC"
        )
        rows = cursor.fetchall()

        conn.close()
        return [dict(row) for row in rows]

    async def get_module_by_id(self, module_id: str) -> Optional[Dict[str, Any]]:
        """根据 ID 获取模块。

        Args:
            module_id: 模块 ID

        Returns:
            dict or None: 模块信息
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM evolution_modules WHERE id = ?", (module_id,))
        row = cursor.fetchone()

        conn.close()
        return dict(row) if row else None

    async def record_collaboration(self, from_module: str, to_module: str) -> None:
        """记录模块间协作。

        Args:
            from_module: 源模块 ID
            to_module: 目标模块 ID
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        now_ms = int(time.time() * 1000)

        cursor.execute(
            """
            INSERT INTO evolution_collaborations
                (id, from_module, to_module, timestamp)
            VALUES (?, ?, ?, ?)
            """,
            (uuid.uuid4().hex, from_module, to_module, now_ms),
        )

        conn.commit()
        conn.close()

        logger.debug("Recorded collaboration: %s -> %s", from_module, to_module)

    async def get_collaboration_count(
        self,
        module_a_id: str,
        module_b_id: str,
        days: int = 3,
    ) -> int:
        """获取两个模块在指定天数内的协作次数。

        Args:
            module_a_id: 模块 A ID
            module_b_id: 模块 B ID
            days: 天数窗口

        Returns:
            int: 协作次数
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cutoff_ms = int((time.time() - days * 24 * 60 * 60) * 1000)

        cursor.execute(
            """
            SELECT COUNT(*) FROM evolution_collaborations
            WHERE ((from_module = ? AND to_module = ?) OR (from_module = ? AND to_module = ?))
              AND timestamp > ?
            """,
            (module_a_id, module_b_id, module_b_id, module_a_id, cutoff_ms),
        )

        count = cursor.fetchone()[0]
        conn.close()

        return count

    async def archive_inactive_modules(self, inactive_days: Optional[int] = None) -> int:
        """归档长期未活跃的模块。

        Args:
            inactive_days: 不活跃天数阈值（默认使用配置）

        Returns:
            int: 归档的模块数量
        """
        days = inactive_days or self.config.death_inactive_days
        logger.info("Archiving modules inactive for %d days", days)

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cutoff_ms = int((time.time() - days * 24 * 60 * 60) * 1000)

        cursor.execute(
            """
            UPDATE evolution_modules
            SET status = 'archived', archived_at = ?
            WHERE status = 'active'
              AND (last_trigger_at IS NULL OR last_trigger_at < ?)
            """,
            (int(time.time() * 1000), cutoff_ms),
        )

        archived_count = cursor.rowcount
        conn.commit()
        conn.close()

        if archived_count > 0:
            logger.info("Archived %d inactive modules", archived_count)

        return archived_count

    async def increment_trigger_count(self, module_id: str) -> None:
        """增加模块触发计数。

        Args:
            module_id: 模块 ID
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        now_ms = int(time.time() * 1000)

        cursor.execute(
            """
            UPDATE evolution_modules
            SET trigger_count = trigger_count + 1, last_trigger_at = ?
            WHERE id = ?
            """,
            (now_ms, module_id),
        )

        conn.commit()
        conn.close()
