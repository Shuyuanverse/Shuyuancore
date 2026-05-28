from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

import aiosqlite

from src.config import get_settings

try:
    from src.models.router import Router
except ImportError:
    Router = None  # type: ignore

logger = logging.getLogger(__name__)

_STALE_CONFIDENCE_PENALTY = 0.1
_MIN_CONFIDENCE = 0.1
_LLM_REVIEW_PROMPT = (
    "你是一个技能质量评估专家。请评估以下技能定义的质量。\n\n"
    "技能名称: {name}\n"
    "描述: {description}\n"
    "因果链: {causality}\n"
    "边界条件: {boundaries}\n"
    "失败模式: {failure_modes}\n"
    "标签: {tags}\n\n"
    "请返回仅一个 JSON 对象，不要包含其他内容：\n"
    '{{\n'
    '  "quality_score": 0-10,\n'
    '  "issues": ["问题1", "问题2"],\n'
    '  "suggested_action": "keep"\n'
    '}}\n\n'
    "评分标准：\n"
    "- 8-10: 定义清晰，有完整因果链和边界条件\n"
    "- 5-7: 基本可用，但缺少部分关键信息\n"
    "- 0-4: 定义模糊，缺乏实用价值"
)


async def run_curation(
    db_path: str = "data/state.db",
    router: Any | None = None,
) -> dict[str, int]:
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
                   sn.description, sn.causality_level0,
                   sn.boundaries, sn.failure_modes, sn.tags,
                   b.confidence, b.last_accessed, b.status as belief_status
            FROM skill_nodes sn
            LEFT JOIN beliefs b ON sn.belief_id = b.id
            WHERE sn.status = 'active'
            """,
        )
        rows = list(await cursor.fetchall())

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

        llm_result = {"llm_reviewed": 0, "llm_demoted": 0}
        if (
            settings.skills.llm_review_enabled
            and router is not None
        ):
            llm_result = await _llm_review_skills(
                conn=conn,
                rows=rows,
                router=router,
                now_ts=now_ts,
            )

        await conn.commit()

        result = {
            "staled": stale_count,
            "archived": archive_count,
            **llm_result,
        }
        logger.info("curation_complete result=%s", result)
        return result

    finally:
        await conn.close()


async def _llm_review_skills(
    conn: aiosqlite.Connection,
    rows: list[aiosqlite.Row],
    router: Any,
    now_ts: int,
) -> dict[str, int]:
    reviewed = 0
    demoted = 0

    for row in rows:
        if row["is_pinned"]:
            continue

        node_id = row["node_id"]
        belief_id = row["belief_id"]
        name = row["name"]

        prompt = _LLM_REVIEW_PROMPT.format(
            name=name,
            description=row["description"] or "",
            causality=row["causality_level0"] or "",
            boundaries=row["boundaries"] or "[]",
            failure_modes=row["failure_modes"] or "[]",
            tags=row["tags"] or "[]",
        )

        try:
            result = await router.chat(
                history=[
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                max_tokens=256,
            )
            content = result.content.strip()
            if content.startswith("```"):
                content = content.strip("`").strip()
                if content.startswith("json"):
                    content = content[4:].strip()
            review = json.loads(content)
        except Exception:
            logger.warning(
                "curator_llm_review_failed skill=%s", name,
            )
            continue

        reviewed += 1
        quality_score = review.get("quality_score", 5)
        suggested_action = review.get("suggested_action", "keep")

        if quality_score < 5 and suggested_action == "demote":
            confidence = row["confidence"] or 0.6
            new_conf = max(
                confidence - _STALE_CONFIDENCE_PENALTY,
                _MIN_CONFIDENCE,
            )
            await conn.execute(
                "UPDATE skill_nodes SET status = 'stale', updated_at = ? WHERE node_id = ?",
                (now_ts, node_id),
            )
            if belief_id:
                await conn.execute(
                    "UPDATE beliefs SET confidence = ? WHERE id = ?",
                    (new_conf, belief_id),
                )
            demoted += 1
            logger.info(
                "curator_llm_demoted skill=%s quality=%d",
                name, quality_score,
            )
        else:
            logger.debug(
                "curator_llm_keep skill=%s quality=%d action=%s",
                name, quality_score, suggested_action,
            )

    return {"llm_reviewed": reviewed, "llm_demoted": demoted}
