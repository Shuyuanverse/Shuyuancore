from __future__ import annotations

import logging

from src.core.interfaces import IBeliefStore

logger = logging.getLogger(__name__)
_VISITED_MAX: int = 1000


async def propagate_confidence(
    store: IBeliefStore,
    belief_id: str,
    delta: float,
    visited: set[str] | None = None,
) -> None:
    visited = visited or set()
    if belief_id in visited:
        return
    if len(visited) > _VISITED_MAX:
        logger.warning("propagate_confidence visited set exceeded %d entries", _VISITED_MAX)
        return

    visited.add(belief_id)
    belief = await store.get_by_id(belief_id)
    if belief is None:
        return

    belief.confidence = max(0.0, min(1.0, belief.confidence + delta))
    belief.base_confidence = belief.confidence
    await store.update(belief)

    if belief.depends_on:
        child_delta = delta * 0.3
        for dep_id in belief.depends_on:
            await propagate_confidence(store, dep_id, child_delta, visited)

    if belief.child_belief_ids:
        child_delta = delta * 0.2
        for child_id in belief.child_belief_ids:
            await propagate_confidence(store, child_id, child_delta, visited)


async def overthrow(
    store: IBeliefStore,
    old_id: str,
    new_id: str,
    reason: str,
) -> None:
    old_belief = await store.get_by_id(old_id)
    if old_belief is None:
        raise ValueError(f"Belief {old_id} not found for overthrow")

    old_belief.status = "superseded"
    old_belief.superseded_by = new_id
    await store.update(old_belief)

    new_belief = await store.get_by_id(new_id)
    if new_belief is None:
        raise ValueError(f"New belief {new_id} not found for overthrow")

    new_belief.depends_on = list(
        set(new_belief.depends_on + old_belief.depends_on)
    )
    new_belief.metadata["overthrow_reason"] = reason
    new_belief.metadata["supersedes"] = old_id
    await store.update(new_belief)
