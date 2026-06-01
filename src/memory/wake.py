from __future__ import annotations

import logging
import re
import time

from src.config import get_settings
from src.core.interfaces import Belief
from src.memory.decay import current_confidence
from src.memory.interfaces import IEmotionAnalyzer, IEntityExtractor

logger = logging.getLogger(__name__)

try:
    import jieba

    HAS_JIEBA = True
except ImportError:
    HAS_JIEBA = False
    logger.warning("jieba not installed; falling back to whitespace tokenization for wake system")

_SEMANTIC_WEIGHT: float = 0.5
_FTS5_WEIGHT: float = 0.2
_ENTITY_WEIGHT: float = 0.15
_EMOTION_WEIGHT: float = 0.1
_EMOTION_FLOOR: float = 0.5


def _tokenize(text: str) -> set[str]:
    lower = text.lower()
    if HAS_JIEBA:
        tokens = set(jieba.lcut(lower))
    else:
        tokens = set(lower.split())
    return {t for t in tokens if len(t) > 1 and not t.isdigit()}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    intersection = a & b
    union = a | b
    return len(intersection) / len(union)


def _keyword_overlap(belief_keywords: list[str], user_keywords: set[str]) -> float:
    if not belief_keywords or not user_keywords:
        return 0.0
    belief_set = {k.lower() for k in belief_keywords}
    overlap = belief_set & user_keywords
    return len(overlap) / max(len(belief_set | user_keywords), 1)


def wake_score(
    belief: Belief,
    user_msg: str,
    entity_extractor: IEntityExtractor,
    emotion_analyzer: IEmotionAnalyzer,
    fts5_scores: dict[str, float] | None = None,
) -> float:
    now_ms = int(time.time() * 1000)
    conf = current_confidence(belief, now_ms)

    user_tokens = _tokenize(user_msg)
    belief_tokens = _tokenize(belief.content)
    semantic_score = _jaccard(user_tokens, belief_tokens) * _SEMANTIC_WEIGHT

    fts5_score = 0.0
    if fts5_scores is not None:
        raw = fts5_scores.get(belief.id, 0.0)
        clamped = max(0.0, min(1.0, raw))
        fts5_score = clamped * _FTS5_WEIGHT

    entity_score = 0.0
    try:
        user_entities = entity_extractor.extract(user_msg)
        belief_entities = entity_extractor.extract(belief.content)
        entity_score = _jaccard(set(user_entities), set(belief_entities)) * _ENTITY_WEIGHT
    except Exception:
        logger.exception("Entity extraction failed in wake_score")

    emotion_score = 0.0
    try:
        user_emotion = emotion_analyzer.analyze(user_msg)
        emotion_diff = 1.0 - abs(user_emotion - belief.emotion)
        emotion_score = max(emotion_diff, _EMOTION_FLOOR) * _EMOTION_WEIGHT
    except Exception:
        logger.exception("Emotion analysis failed in wake_score")

    raw_score = semantic_score + fts5_score + entity_score + emotion_score
    return raw_score * conf


_TECH_KEYWORD_PATTERN = re.compile(
    r"(python|javascript|rust|go|java|typescript|react|docker|kubernetes|"
    r"git|linux|api|sql|database|server|deploy|config|debug|test|"
    r"function|class|module|async|await|import|export|"
    r"terminal|command|script|code|compile|build|merge|commit|"
    r"算法|代码|编程|部署|数据库|接口|终端|脚本|调试|测试)",
    re.IGNORECASE,
)


def wake_readiness(user_msg: str, consecutive_tech_rounds: int = 0) -> float:
    if not user_msg.strip():
        return 0.0

    tech_matches = _TECH_KEYWORD_PATTERN.findall(user_msg)
    tech_density = len(tech_matches) / max(len(user_msg.split()), 1)

    base: float = 0.0
    if tech_density > 0.3:
        base = 0.6
    elif tech_density > 0.15:
        base = 0.4
    else:
        base = 0.2

    momentum = min(consecutive_tech_rounds * 0.1, 1.0)
    return min(base + momentum, 1.0)


class WakeFrequencyTracker:
    def __init__(self, session_window_ms: int = 300000) -> None:
        self._belief_tracker: dict[str, list[int]] = {}
        self._session_tracker: dict[str, int] = {}
        self._session_window_ms: int = session_window_ms
        self._last_reset: int = 0
        cfg = get_settings().memory
        self._max_per_belief: int = cfg.max_wakeups_per_belief_per_day
        self._max_per_session: int = cfg.max_wakeups_per_session

    def record_belief_wake(self, belief_id: str) -> None:
        now_ms = int(time.time() * 1000)
        if belief_id not in self._belief_tracker:
            self._belief_tracker[belief_id] = []
        self._belief_tracker[belief_id].append(now_ms)

    def record_session_wake(self, session_id: str) -> None:
        now_ms = int(time.time() * 1000)
        if session_id not in self._session_tracker:
            self._session_tracker[session_id] = 0
        self._session_tracker[session_id] += 1
        self._last_reset = now_ms

    def belief_wake_count(self, belief_id: str, window_ms: int = 3600000) -> int:
        cutoff = int(time.time() * 1000) - window_ms
        timestamps = self._belief_tracker.get(belief_id, [])
        return sum(1 for ts in timestamps if ts >= cutoff)

    def session_wake_count(self, session_id: str, window_ms: int = 3600000) -> int:
        return self._session_tracker.get(session_id, 0)

    def should_suppress(self, belief_id: str, max_per_hour: int | None = None) -> bool:
        limit = max_per_hour if max_per_hour is not None else self._max_per_belief
        return self.belief_wake_count(belief_id) >= limit

    def reset_session(self, session_id: str) -> None:
        self._session_tracker.pop(session_id, None)

    def reset_all(self) -> None:
        self._belief_tracker.clear()
        self._session_tracker.clear()
