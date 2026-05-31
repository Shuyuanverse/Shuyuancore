from __future__ import annotations

import logging
import re
import uuid
from typing import Any

from src.config import get_settings
from src.core.interfaces import Belief, IBeliefStore
from src.memory.interfaces import IEmotionAnalyzer, IEntityExtractor

logger = logging.getLogger(__name__)

_RULE_PATTERNS: list[tuple[re.Pattern[str], str, float]] = [
    (re.compile(r"我(?:叫|姓)\s*(\S+)"), "identity", 0.95),
    (re.compile(r"我(?:的)?名字(?:是|叫)\s*(\S+)"), "identity", 0.95),
    (re.compile(r"我(?:喜欢|热爱|偏爱)\s*(.+?)(?:[，。！？;]|$)"), "preference", 0.85),
    (re.compile(r"我(?:讨厌|不喜欢|反感)\s*(.+?)(?:[，。！？;]|$)"), "preference", 0.85),
    (re.compile(r"记住\s*[:：]\s*(.+)"), "fact", 0.9),
    (re.compile(r"我(?:的)?项目\s*(?:是|叫|为)\s*(.+?)(?:[，。！？;]|$)"), "task", 0.85),
    (re.compile(r"我(?:在|正在)?做\s*(.+?)(?:项目|事情|工作)(?:[，。！？;]|$)"), "task", 0.8),
    (re.compile(r"我(?:的)?目标\s*(?:是|为)\s*(.+?)(?:[，。！？;]|$)"), "agreement", 0.85),
    (re.compile(r"我(?:的)?生日\s*(?:是|为)\s*(\S+)"), "fact", 0.9),
    (re.compile(r"我来自\s*(.+?)(?:[，。！？;]|$)"), "identity", 0.9),
    (re.compile(r"我(?:的)?职业\s*(?:是|为)\s*(.+?)(?:[，。！？;]|$)"), "identity", 0.85),
    (re.compile(r"请(?:你)?(?:记得|记住|记下)\s*[:：]?\s*(.+)"), "fact", 0.85),
]

_LAYER_MAP: dict[str, int] = {
    "identity": 1,
    "preference": 1,
    "fact": 3,
    "task": 2,
    "agreement": 2,
}


class RuleBasedWriter:
    def __init__(
        self,
        store: IBeliefStore,
        entity_extractor: IEntityExtractor,
        emotion_analyzer: IEmotionAnalyzer,
        conversation_id: str,
        source: str = "user",
    ) -> None:
        self._store = store
        self._entity_extractor = entity_extractor
        self._emotion_analyzer = emotion_analyzer
        self._conversation_id = conversation_id
        self._source = source

    async def process(self, text: str, timestamp_ms: int) -> list[Belief]:
        created: list[Belief] = []

        for pattern, memory_type, confidence in _RULE_PATTERNS:
            for match in pattern.finditer(text):
                content = match.group(1).strip()
                if len(content) < 2:
                    continue

                emotion = self._emotion_analyzer.analyze(content)
                entities = self._entity_extractor.extract(content)
                layer = _LAYER_MAP.get(memory_type, 3)

                belief = Belief(
                    id=str(uuid.uuid4()),
                    content=f"[{memory_type}] {content}",
                    source=self._source,
                    confidence=confidence,
                    base_confidence=confidence,
                    last_accessed=timestamp_ms,
                    memory_type=memory_type,
                    layer=layer,
                    entities=entities,
                    emotion=emotion,
                    timestamp=timestamp_ms,
                )

                await self._store.add(self._conversation_id, belief)
                created.append(belief)

        return created


_MANUAL_PREFIX_PATTERN = re.compile(r"记住\s*[:：]\s*", re.IGNORECASE)
_MANUAL_SEPARATOR_PATTERN = re.compile(r"\s*[,，、;；]\s*")


class ManualMemoryWriter:
    def __init__(
        self,
        store: IBeliefStore,
        entity_extractor: IEntityExtractor,
        emotion_analyzer: IEmotionAnalyzer,
        conversation_id: str,
        source: str = "user",
    ) -> None:
        self._store = store
        self._entity_extractor = entity_extractor
        self._emotion_analyzer = emotion_analyzer
        self._conversation_id = conversation_id
        self._source = source

    async def process(self, text: str, timestamp_ms: int) -> list[Belief]:
        if not _MANUAL_PREFIX_PATTERN.match(text):
            return []

        cleaned = _MANUAL_PREFIX_PATTERN.sub("", text).strip()
        items = _MANUAL_SEPARATOR_PATTERN.split(cleaned)
        items = [item.strip() for item in items if item.strip()]

        created: list[Belief] = []

        for item in items:
            emotion = self._emotion_analyzer.analyze(item)
            entities = self._entity_extractor.extract(item)

            belief = Belief(
                id=str(uuid.uuid4()),
                content=f"[manual] {item}",
                source=self._source,
                confidence=0.9,
                base_confidence=0.9,
                last_accessed=timestamp_ms,
                memory_type="fact",
                layer=3,
                entities=entities,
                emotion=emotion,
                timestamp=timestamp_ms,
            )

            await self._store.add(self._conversation_id, belief)
            created.append(belief)

        return created


class AiInferenceWriter:
    def __init__(
        self,
        store: IBeliefStore,
        entity_extractor: IEntityExtractor,
        emotion_analyzer: IEmotionAnalyzer,
        conversation_id: str,
        source: str = "assistant",
    ) -> None:
        self._store = store
        self._entity_extractor = entity_extractor
        self._emotion_analyzer = emotion_analyzer
        self._conversation_id = conversation_id
        self._source = source
        self._threshold: float = get_settings().memory.ai_importance_threshold

    async def process_llm_output(
        self,
        llm_content: str,
        importance: float,
        timestamp_ms: int,
        metadata: dict[str, Any] | None = None,
    ) -> Belief | None:
        if importance < self._threshold:
            return None

        emotion = self._emotion_analyzer.analyze(llm_content)
        entities = self._entity_extractor.extract(llm_content)

        belief = Belief(
            id=str(uuid.uuid4()),
            content=llm_content,
            source=self._source,
            confidence=importance,
            base_confidence=importance,
            last_accessed=timestamp_ms,
            memory_type="fact",
            layer=3,
            entities=entities,
            emotion=emotion,
            timestamp=timestamp_ms,
            metadata=metadata or {},
        )

        await self._store.add(self._conversation_id, belief)
        return belief


class CompositeBeliefDetector:
    def __init__(
        self,
        store: IBeliefStore,
        entity_extractor: IEntityExtractor,
        emotion_analyzer: IEmotionAnalyzer,
        conversation_id: str,
        source: str = "assistant",
    ) -> None:
        self._store = store
        self._entity_extractor = entity_extractor
        self._emotion_analyzer = emotion_analyzer
        self._conversation_id = conversation_id
        self._source = source
        cfg = get_settings().memory
        self._min_rounds: int = cfg.composite_min_rounds
        self._composite_confidence: float = cfg.composite_confidence

    async def process_multi_turn(
        self,
        turns: list[dict[str, Any]],
        timestamp_ms: int,
    ) -> list[Belief]:
        if len(turns) < self._min_rounds:
            return []

        combined_text = " ".join(turn.get("content", "") for turn in turns)

        if len(combined_text) < 100:
            return []

        entities = self._entity_extractor.extract(combined_text)
        if len(entities) < 3:
            return []

        emotion = self._emotion_analyzer.analyze(combined_text)
        all_emotions = [self._emotion_analyzer.analyze(turn.get("content", "")) for turn in turns]

        topic_keywords = list(
            {kw for turn in turns for kw in self._entity_extractor.extract(turn.get("content", ""))}
        )

        belief = Belief(
            id=str(uuid.uuid4()),
            content=combined_text[:500],
            source=self._source,
            confidence=self._composite_confidence,
            base_confidence=self._composite_confidence,
            last_accessed=timestamp_ms,
            memory_type="fact",
            layer=3,
            entities=topic_keywords,
            emotion=emotion,
            is_composite=True,
            timestamp=timestamp_ms,
            metadata={
                "turn_count": len(turns),
                "emotion_range": [min(all_emotions), max(all_emotions)],
                "combined_length": len(combined_text),
            },
        )

        await self._store.add(self._conversation_id, belief)
        return [belief]
