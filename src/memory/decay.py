from __future__ import annotations

import math
import time
from functools import lru_cache

from src.config import get_settings
from src.core.interfaces import Belief


@lru_cache(maxsize=1)
def _get_decay_rates() -> dict[int, float]:
    raw = get_settings().memory.decay_rates
    return {int(k.split("_")[1]): v for k, v in raw.items()}


def current_time_ms() -> int:
    return int(time.time() * 1000)


def current_confidence(belief: Belief, now_ms: int | None = None) -> float:
    if belief.status == "superseded":
        return 0.0

    now = now_ms if now_ms is not None else current_time_ms()
    elapsed_days = max(0.0, (now - belief.last_accessed) / 86400000.0)

    rates = _get_decay_rates()
    rate = rates.get(belief.layer, 0.01)

    confidence = belief.base_confidence * math.exp(-rate * elapsed_days)
    config = get_settings().memory
    return max(confidence, config.confidence_floor)
