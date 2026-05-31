from __future__ import annotations

import asyncio
import logging
from typing import Any

from src.agents.arbitrator import Arbitrator
from src.agents.interfaces import (
    IUpdater,
    UpdateContext,
    UpdaterResult,
)
from src.agents.reviewer import Reviewer
from src.agents.updater_evidence import EvidenceUpdater
from src.agents.updater_innovation import InnovationUpdater
from src.agents.updater_risk import RiskUpdater
from src.agents.utils import (
    build_updater_belief,
    compute_perturbation_strength,
    determine_update_strategy,
)
from src.config import get_settings
from src.exceptions import (
    CoordinatorTimeoutError,
)
from src.models.interfaces import IModelProvider

logger = logging.getLogger(__name__)


class Coordinator:
    def __init__(
        self,
        model_provider: IModelProvider,
        sub_agent_class: Any = None,
    ) -> None:
        self._model_provider = model_provider
        self._sub_agent_class = sub_agent_class
        self._mode_override: dict[str, str] = {}
        self._evidence: IUpdater = EvidenceUpdater(model_provider)
        self._risk: IUpdater = RiskUpdater(model_provider)
        self._innovation: IUpdater = InnovationUpdater(model_provider)
        self._reviewer = Reviewer(model_provider)
        self._arbitrator = Arbitrator(model_provider)

    def set_mode(self, conversation_id: str, mode: str) -> None:
        if mode in ("quick", "balanced", "deep"):
            self._mode_override[conversation_id] = mode

    def get_mode(self, conversation_id: str) -> str | None:
        return self._mode_override.get(conversation_id)

    async def run(self, ctx: UpdateContext) -> str:
        cfg = get_settings()
        timeout = cfg.agents.coordinator_timeout_seconds

        try:
            return await asyncio.wait_for(
                self._run_internal(ctx),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            logger.warning("coordinator_timeout: conv=%s", ctx.conversation_id)
            raise CoordinatorTimeoutError("协调器执行超时")

    async def _run_internal(self, ctx: UpdateContext) -> str:
        if ctx.belief_store:
            ctx.perturbation_strength = await compute_perturbation_strength(
                ctx.belief_store, ctx.message
            )

        mode = self._mode_override.get(ctx.conversation_id)
        updater_names = determine_update_strategy(
            ctx.perturbation_strength,
            mode_override=mode,
        )

        updater_map: dict[str, IUpdater] = {
            "evidence": self._evidence,
            "risk": self._risk,
            "innovation": self._innovation,
        }

        tasks = []
        for name in updater_names:
            updater = updater_map.get(name)
            if updater:
                tasks.append(self._safe_update(ctx, updater, name))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        valid_results: list[UpdaterResult] = []
        for r in results:
            if isinstance(r, UpdaterResult):
                valid_results.append(r)
            elif isinstance(r, Exception):
                logger.warning("updater_failed: %s", r)

        if not valid_results:
            evidence_fallback = await self._evidence.update(ctx)
            valid_results.append(evidence_fallback)

        draft = await self._arbitrator.arbitrate(ctx, valid_results)

        review_result = await self._reviewer.review(ctx, draft)
        if not review_result.get("pass", True):
            draft = await self._arbitrator.arbitrate(ctx, valid_results)

        if ctx.belief_store:
            for r in valid_results:
                try:
                    belief = build_updater_belief(r, ctx.conversation_id)
                    await ctx.belief_store.add(ctx.conversation_id, belief)
                except Exception:
                    logger.exception("coordinator_belief_write_failed")

        return draft

    async def _safe_update(self, ctx: UpdateContext, updater: IUpdater, name: str) -> UpdaterResult:
        try:
            return await updater.update(ctx)
        except Exception:
            logger.exception("updater_error: name=%s", name)
            raise
