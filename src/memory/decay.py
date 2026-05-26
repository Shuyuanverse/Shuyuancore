from __future__ import annotations

import math
import time

from src.core.interfaces import Belief

_DECAY_RATES: dict[int, float] = {
    1: 0.0005,
    2: 0.005,
    3: 0.01,
    4: 0.015,
    5: 0.01,
    6: 0.0,
}
_DEFAULT_DECAY_RATE: float = 0.01
_MIN_CONFIDENCE: float = 0.1


def current_time_ms() -> int:
    return int(time.time() * 1000)


def current_confidence(belief: Belief, now_ms: int | None = None) -> float:
    if belief.status == "superseded":
        return 0.0

    now = now_ms if now_ms is not None else current_time_ms()
    elapsed_days = max(0.0, (now - belief.last_accessed) / 86400000.0)
    rate = _DECAY_RATES.get(belief.layer, _DEFAULT_DECAY_RATE)
    confidence = belief.base_confidence * math.exp(-rate * elapsed_days)
    return max(confidence, _MIN_CONFIDENCE)
