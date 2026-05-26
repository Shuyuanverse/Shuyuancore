from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path
from typing import Any

import aiosqlite

from src.config import get_settings
from src.core.interfaces import Belief, IBeliefStore
from src.exceptions import SkillNotFoundError
from src.memory.decay import current_time_ms
from src.skills.interfaces import ISkillGraph, ISkillStore
from src.skills.models import SkillNode
from src.skills.utils import (
    generate_edge_id,
    generate_node_id,
    node_to_markdown,
)

logger = logging.getLogger(__name__)

_SKILLS_DIR = Path("data/skills")


class PersistentSkillStore(ISkillStore):

    def __init__(
        self,
        belief_store: IBeliefStore | None = None,
        db_path: str = "data/state.db",
    ) -> None:
        self._belief_store = belief_store
        self._db_path = db_path
        self._conn: aiosqlite.Connection | None = None

    async def _get_conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            self._conn = await aiosqlite.connect(self._db_path)
            self._conn.row_factory = aiosqlite.Row
            await self._conn.execute("PRAGMA journal_mode = WAL;")
            await self._conn.execute("PRAGMA foreign_keys = ON;")
            await self._conn.execute("PRAGMA busy_timeout = 5000;")
        return self._conn

    async def list_skills(
        self, status: str = "active"
    ) -> list[dict[str, Any]]:
        conn = await self._get_conn()
        cursor = await conn.execute(
            """
            SELECT sn.*, b.confidence, b.last_accessed
            FROM skill_nodes sn
            LEFT JOIN beliefs b ON sn.belief_id = b.id
            WHERE sn.status = ?
            ORDER BY sn.created_at DESC
            """,
            (status,),
        )
        rows = await cursor.fetchall()
        return [self._row_to_dict(r) for r in rows]

    async def get_skill(self, name: str) -> dict[str, Any] | None:
        conn = await self._get_conn()
        cursor = await conn.execute(
            """
            SELECT sn.*, b.confidence, b.last_accessed
            FROM skill_nodes sn
            LEFT JOIN beliefs b ON sn.belief_id = b.id
            WHERE sn.name = ?
            """,
            (name,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return self._row_to_dict(row)

    async def create_skill(
        self,
        node: dict[str, Any],
        conversation_id: str,
    ) -> str:
        conn = await self._get_conn()
        now_ms = current_time_ms()

        skill_node = SkillNode(
            node_id=node.get("node_id", generate_node_id()),
            name=node.get("name", ""),
            node_type=node.get("node_type", "skill"),
            belief_id="",
            description=node.get("description", ""),
            tags=node.get("tags", []),
            preconditions=node.get("preconditions", []),
            causality_level0=node.get("causality_level0", ""),
            causality_level1=node.get("causality_level1", ""),
            causality_level2=node.get("causality_level2", ""),
            boundaries=node.get("boundaries", []),
            failure_modes=node.get("failure_modes", []),
            dependencies=node.get("dependencies", []),
            version_history=node.get(
                "version_history",
                [
                    {
                        "version": "1.0",
                        "date": now_ms,
                        "change": "initial creation",
                    }
                ],
            ),
            status=node.get("status", "active"),
            is_pinned=node.get("is_pinned", False),
            created_at=now_ms,
            updated_at=now_ms,
        )

        explicit_save = node.get("explicit_save", False)
        initial_confidence = 0.9 if explicit_save else 0.6

        if self._belief_store:
            belief = Belief(
                id=str(uuid.uuid4()),
                content=skill_node.description or skill_node.name,
                source="skill",
                confidence=initial_confidence,
                base_confidence=initial_confidence,
                last_accessed=now_ms,
                memory_type="skill",
                layer=4,
                timestamp=now_ms,
                status="active",
            )
            belief_id = await self._belief_store.add(
                conversation_id, belief
            )
            skill_node.belief_id = belief_id

        await conn.execute(
            """
            INSERT INTO skill_nodes (
                node_id, name, node_type, belief_id,
                description, tags, preconditions,
                causality_level0, causality_level1, causality_level2,
                boundaries, failure_modes, dependencies,
                version_history, status, is_pinned,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                skill_node.node_id,
                skill_node.name,
                skill_node.node_type,
                skill_node.belief_id,
                skill_node.description,
                json.dumps(skill_node.tags, ensure_ascii=False),
                json.dumps(skill_node.preconditions, ensure_ascii=False),
                skill_node.causality_level0,
                skill_node.causality_level1,
                skill_node.causality_level2,
                json.dumps(skill_node.boundaries, ensure_ascii=False),
                json.dumps(skill_node.failure_modes, ensure_ascii=False),
                json.dumps(skill_node.dependencies, ensure_ascii=False),
                json.dumps(skill_node.version_history, ensure_ascii=False),
                skill_node.status,
                1 if skill_node.is_pinned else 0,
                skill_node.created_at,
                skill_node.updated_at,
            ),
        )
        await conn.commit()

        _SKILLS_DIR.mkdir(parents=True, exist_ok=True)
        md_path = _SKILLS_DIR / f"{skill_node.name}.md"
        md_content = node_to_markdown(skill_node)
        md_path.write_text(md_content, encoding="utf-8")

        logger.info(
            "skill_created name=%s belief_id=%s",
            skill_node.name,
            skill_node.belief_id,
        )
        return skill_node.node_id

    async def update_skill(self, node: dict[str, Any]) -> None:
        conn = await self._get_conn()
        now_ms = current_time_ms()
        name = node.get("name", "")

        existing = await self.get_skill(name)
        if existing is None:
            raise SkillNotFoundError(f"Skill '{name}' not found")

        await conn.execute(
            """
            UPDATE skill_nodes SET
                description = ?,
                tags = ?,
                preconditions = ?,
                causality_level0 = ?,
                causality_level1 = ?,
                causality_level2 = ?,
                boundaries = ?,
                failure_modes = ?,
                dependencies = ?,
                version_history = ?,
                status = ?,
                is_pinned = ?,
                updated_at = ?
            WHERE name = ?
            """,
            (
                node.get("description", existing["description"]),
                json.dumps(
                    node.get("tags", existing.get("tags", [])),
                    ensure_ascii=False,
                ),
                json.dumps(
                    node.get("preconditions", existing.get("preconditions", [])),
                    ensure_ascii=False,
                ),
                node.get("causality_level0", existing.get("causality_level0", "")),
                node.get("causality_level1", existing.get("causality_level1", "")),
                node.get("causality_level2", existing.get("causality_level2", "")),
                json.dumps(
                    node.get("boundaries", existing.get("boundaries", [])),
                    ensure_ascii=False,
                ),
                json.dumps(
                    node.get("failure_modes", existing.get("failure_modes", [])),
                    ensure_ascii=False,
                ),
                json.dumps(
                    node.get("dependencies", existing.get("dependencies", [])),
                    ensure_ascii=False,
                ),
                json.dumps(
                    node.get(
                        "version_history", existing.get("version_history", [])
                    ),
                    ensure_ascii=False,
                ),
                node.get("status", existing.get("status", "active")),
                1 if node.get("is_pinned", existing.get("is_pinned", False)) else 0,
                now_ms,
                name,
            ),
        )
        await conn.commit()

        snode = SkillNode(
            node_id=existing.get("node_id", ""),
            name=name,
            node_type=node.get("node_type", existing.get("node_type", "skill")),
            belief_id=existing.get("belief_id", ""),
            description=node.get("description", existing.get("description", "")),
            tags=node.get("tags", existing.get("tags", [])),
            preconditions=node.get(
                "preconditions", existing.get("preconditions", [])
            ),
            causality_level0=node.get(
                "causality_level0", existing.get("causality_level0", "")
            ),
            causality_level1=node.get(
                "causality_level1", existing.get("causality_level1", "")
            ),
            causality_level2=node.get(
                "causality_level2", existing.get("causality_level2", "")
            ),
            boundaries=node.get("boundaries", existing.get("boundaries", [])),
            failure_modes=node.get(
                "failure_modes", existing.get("failure_modes", [])
            ),
            dependencies=node.get(
                "dependencies", existing.get("dependencies", [])
            ),
            version_history=node.get(
                "version_history", existing.get("version_history", [])
            ),
            status=node.get("status", existing.get("status", "active")),
            is_pinned=node.get("is_pinned", existing.get("is_pinned", False)),
            created_at=existing.get("created_at", now_ms),
            updated_at=now_ms,
        )
        _SKILLS_DIR.mkdir(parents=True, exist_ok=True)
        md_path = _SKILLS_DIR / f"{name}.md"
        md_content = node_to_markdown(snode)
        md_path.write_text(md_content, encoding="utf-8")

        logger.info("skill_updated name=%s", name)

    async def delete_skill(self, name: str) -> None:
        conn = await self._get_conn()
        existing = await self.get_skill(name)
        if existing is None:
            raise SkillNotFoundError(f"Skill '{name}' not found")

        belief_id = existing.get("belief_id", "")
        if belief_id and self._belief_store:
            try:
                await self._belief_store.remove("", belief_id)
            except Exception:
                logger.warning(
                    "failed_to_remove_belief belief_id=%s", belief_id
                )

        await conn.execute(
            "DELETE FROM skill_nodes WHERE name = ?",
            (name,),
        )
        await conn.commit()

        md_path = _SKILLS_DIR / f"{name}.md"
        if md_path.exists():
            md_path.unlink()

        logger.info("skill_deleted name=%s", name)

    def _row_to_dict(self, row: aiosqlite.Row) -> dict[str, Any]:
        result: dict[str, Any] = dict(row)
        for key in (
            "tags",
            "preconditions",
            "boundaries",
            "failure_modes",
            "dependencies",
            "version_history",
        ):
            val = result.get(key)
            if isinstance(val, str):
                try:
                    result[key] = json.loads(val)
                except (json.JSONDecodeError, TypeError):
                    result[key] = val if val else []
        return result


class PersistentSkillGraph(ISkillGraph):

    def __init__(self, db_path: str = "data/state.db") -> None:
        self._db_path = db_path
        self._conn: aiosqlite.Connection | None = None

    async def _get_conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            self._conn = await aiosqlite.connect(self._db_path)
            self._conn.row_factory = aiosqlite.Row
            await self._conn.execute("PRAGMA journal_mode = WAL;")
            await self._conn.execute("PRAGMA foreign_keys = ON;")
            await self._conn.execute("PRAGMA busy_timeout = 5000;")
        return self._conn

    async def add_edge(self, edge: dict[str, Any]) -> str:
        conn = await self._get_conn()
        now_ms = current_time_ms()
        edge_id = edge.get("edge_id", generate_edge_id())
        from_node = edge.get("from_node", "")
        to_node = edge.get("to_node", "")
        edge_type = edge.get("edge_type", "enables")

        await conn.execute(
            """
            INSERT INTO skill_edges (edge_id, from_node, to_node, edge_type, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (edge_id, from_node, to_node, edge_type, now_ms),
        )
        await conn.commit()

        if edge_type in ("enables", "causally-linked"):
            await self._sync_to_belief_depends_on(conn, from_node, to_node, add=True)

        logger.info(
            "skill_edge_added from=%s to=%s type=%s",
            from_node,
            to_node,
            edge_type,
        )
        return edge_id

    async def get_edges(
        self, node_name: str | None = None
    ) -> list[dict[str, Any]]:
        conn = await self._get_conn()
        if node_name:
            cursor = await conn.execute(
                """
                SELECT * FROM skill_edges
                WHERE from_node = ? OR to_node = ?
                ORDER BY created_at DESC
                """,
                (node_name, node_name),
            )
        else:
            cursor = await conn.execute(
                "SELECT * FROM skill_edges ORDER BY created_at DESC"
            )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    async def remove_edge(self, edge_id: str) -> None:
        conn = await self._get_conn()
        cursor = await conn.execute(
            "SELECT * FROM skill_edges WHERE edge_id = ?",
            (edge_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            return

        from_node = row["from_node"]
        to_node = row["to_node"]
        edge_type = row["edge_type"]

        await conn.execute(
            "DELETE FROM skill_edges WHERE edge_id = ?",
            (edge_id,),
        )
        await conn.commit()

        if edge_type in ("enables", "causally-linked"):
            await self._sync_to_belief_depends_on(
                conn, from_node, to_node, add=False
            )

        logger.info("skill_edge_removed edge_id=%s", edge_id)

    async def traverse(
        self, start_name: str
    ) -> list[dict[str, Any]]:
        conn = await self._get_conn()
        visited: set[str] = set()
        result: list[dict[str, Any]] = []
        queue: list[str] = [start_name]
        while queue:
            current = queue.pop(0)
            if current in visited:
                continue
            visited.add(current)
            cursor = await conn.execute(
                """
                SELECT sn.*, b.confidence, b.last_accessed
                FROM skill_nodes sn
                LEFT JOIN beliefs b ON sn.belief_id = b.id
                WHERE sn.name = ?
                """,
                (current,),
            )
            row = await cursor.fetchone()
            if row is not None:
                result.append(dict(row))
            cursor = await conn.execute(
                "SELECT to_node FROM skill_edges WHERE from_node = ?",
                (current,),
            )
            for child_row in await cursor.fetchall():
                queue.append(child_row["to_node"])
        return result

    async def _sync_to_belief_depends_on(
        self,
        conn: aiosqlite.Connection,
        from_node: str,
        to_node: str,
        add: bool,
    ) -> None:
        cursor = await conn.execute(
            "SELECT belief_id FROM skill_nodes WHERE name = ?",
            (from_node,),
        )
        from_row = await cursor.fetchone()
        if from_row is None:
            return
        from_belief_id = from_row["belief_id"]

        cursor = await conn.execute(
            "SELECT belief_id FROM skill_nodes WHERE name = ?",
            (to_node,),
        )
        to_row = await cursor.fetchone()
        if to_row is None:
            return
        to_belief_id = to_row["belief_id"]

        cursor = await conn.execute(
            "SELECT depends_on FROM beliefs WHERE id = ?",
            (from_belief_id,),
        )
        belief_row = await cursor.fetchone()
        if belief_row is None:
            return

        depends_on_raw = belief_row["depends_on"] or "[]"
        try:
            depends_on: list[str] = json.loads(depends_on_raw)
        except (json.JSONDecodeError, TypeError):
            depends_on = []

        if add:
            if to_belief_id not in depends_on:
                depends_on.append(to_belief_id)
        else:
            depends_on = [d for d in depends_on if d != to_belief_id]

        await conn.execute(
            "UPDATE beliefs SET depends_on = ? WHERE id = ?",
            (json.dumps(depends_on), from_belief_id),
        )
        await conn.commit()