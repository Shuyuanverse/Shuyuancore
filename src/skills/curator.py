from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

import aiosqlite

from src.config import get_settings

logger = logging.getLogger(__name__)

_STALE_CONFIDENCE_PENALTY = 0.1
_MIN_CONFIDENCE = 0.1


async def run_curation(db_path: str = "data/state.db") -> dict[str, int]:
    from src.memory.decay import current_time_ms

    settings = get_settings()
    now_ts = current_time_ms()
    now = datetime.now(timezone.utc)

    stale_days = settings.skills.stale_days
    archive_days = settings.skills.archive_days
    stale_threshold_ms = int(
        now.timestamp() - stale_days * 86400
    ) * 1000
    archive_threshold_ms = int(
        now.timestamp() - archive_days * 86400
    ) * 1000

    conn = await aiosqlite.connect(db_path)
    conn.row_factory = aiosqlite.Row
    await conn.execute("PRAGMA journal_mode = WAL;")
    await conn.execute("PRAGMA foreign_keys = ON;")
    await conn.execute("PRAGMA busy_timeout = 5000;")

    try:
        cursor = await conn.execute(
            """
            SELECT sn.node_id, sn.name, sn.belief_id, sn.is_pinned,
                   b.confidence, b.last_accessed, b.status as belief_status
            FROM skill_nodes sn
            LEFT JOIN beliefs b ON sn.belief_id = b.id
            WHERE sn.status = 'active'
            """,
        )
        rows = await cursor.fetchall()

        stale_count = 0
        archive_count = 0

        for row in rows:
            if row["is_pinned"]:
                continue

            last_accessed = row["last_accessed"] or 0
            confidence = row["confidence"] or 0.6
            node_id = row["node_id"]
            belief_id = row["belief_id"]
            name = row["name"]

            if last_accessed < archive_threshold_ms:
                await conn.execute(
                    "UPDATE skill_nodes SET status = 'archived', updated_at = ? WHERE node_id = ?",
                    (now_ts, node_id),
                )
                if belief_id:
                    new_conf = max(
                        confidence - _STALE_CONFIDENCE_PENALTY,
                        _MIN_CONFIDENCE,
                    )
                    await conn.execute(
                        "UPDATE beliefs SET confidence = ? WHERE id = ?",
                        (new_conf, belief_id),
                    )
                archive_count += 1
                logger.info(
                    "curator_archived skill=%s days_unused=%d",
                    name,
                    archive_days,
                )

            elif last_accessed < stale_threshold_ms:
                await conn.execute(
                    "UPDATE skill_nodes SET status = 'stale', updated_at = ? WHERE node_id = ?",
                    (now_ts, node_id),
                )
                if belief_id:
                    new_conf = max(
                        confidence - _STALE_CONFIDENCE_PENALTY,
                        _MIN_CONFIDENCE,
                    )
                    await conn.execute(
                        "UPDATE beliefs SET confidence = ? WHERE id = ?",
                        (new_conf, belief_id),
                    )
                stale_count += 1
                logger.info(
                    "curator_staled skill=%s days_unused=%d",
                    name,
                    stale_days,
                )

        await conn.commit()

        result = {"staled": stale_count, "archived": archive_count}
        logger.info("curation_complete result=%s", result)
        return result

    finally:
        await conn.close()