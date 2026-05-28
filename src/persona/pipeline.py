from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

from src.persona.perception import PerceptionResult
from src.persona.profile import PersonaProfile

logger = logging.getLogger(__name__)


class PipelineContext:
    def __init__(self):
        self.drift_history: list[dict] = []
        self.calibration_prompt: str = ""
        self._lock = asyncio.Lock()

    async def record_drift(self, entry: dict) -> None:
        async with self._lock:
            self.drift_history.append(entry)
            logger.info(
                "[pipeline] 记录漂移: drift=%.4f level=%s",
                entry.get("drift_score", 0), entry.get("alert_level", "none"),
            )

    async def get_drift_history(self, limit: int = 50) -> list[dict]:
        async with self._lock:
            return self.drift_history[-limit:]


async def orchestrate_background(
    user_message: str,
    response_text: str,
    conversation_history: list[dict],
    persona_profile: PersonaProfile,
    perception: Optional[PerceptionResult],
    pctx: Optional[PipelineContext] = None,
    evolution_engine: Any = None,
    drift_store: Any = None,
) -> None:
    try:
        if perception and drift_store:
            drift_entry: dict = {
                "persona_id": persona_profile.persona_id,
                "drift_score": getattr(perception, "patience_level", 1.0),
                "alert_level": "background",
                "dimensions": {},
                "calibration_applied": False,
            }
            try:
                if hasattr(drift_store, "add_drift_record"):
                    await drift_store.add_drift_record(drift_entry)
            except Exception:
                pass

            if pctx:
                await pctx.record_drift(drift_entry)

        if evolution_engine and len(conversation_history) % 10 == 0:
            try:
                drift_history = []
                if pctx:
                    drift_history = await pctx.get_drift_history()
                proposals = await evolution_engine.detect_evolution(
                    persona_profile.persona_id,
                    persona_profile,
                    drift_history,
                    conversation_history,
                )
                if proposals:
                    logger.info("[pipeline] 检测到 %d 个演化提议", len(proposals))
                    for prop in proposals:
                        reviewed = await evolution_engine.review_and_apply(prop)
                        logger.info(
                            "[pipeline] 演化提议 %s: %s",
                            reviewed.proposal_id, reviewed.status,
                        )
            except Exception as exc:
                logger.warning("[pipeline] 演化检测异常: %s", exc)
    except Exception as exc:
        logger.warning("[pipeline] 后台管线异常: %s", exc)
