from __future__ import annotations

import logging

from src.memory.interfaces import IEmotionAnalyzer, IEntityExtractor

logger = logging.getLogger(__name__)

try:
    import jieba.posseg as pseg
    HAS_JIEBA = True
except ImportError:
    HAS_JIEBA = False
    logger.warning("jieba not installed; JiebaEntityExtractor will return empty lists")

try:
    from snownlp import SnowNLP
    HAS_SNOWNLP = True
except ImportError:
    HAS_SNOWNLP = False
    logger.warning("snownlp not installed; SnowNlpEmotionAnalyzer will return 0.5")


_NOUN_FLAGS: set[str] = {"n", "nr", "nr1", "nr2", "nrj", "nrf", "ns", "nsf", "nt", "nz", "nl", "ng"}
_PROPER_FLAGS: set[str] = {"nr", "nr1", "nr2", "nrj", "nrf", "ns", "nsf", "nt"}
_PATTERN_MARKERS: set[str] = {"x", "m", "eng"}


class JiebaEntityExtractor(IEntityExtractor):

    def __init__(self, user_dict_path: str | None = None) -> None:
        if user_dict_path and HAS_JIEBA:
            import jieba
            jieba.load_userdict(user_dict_path)

    def extract(self, text: str) -> list[str]:
        if not HAS_JIEBA or not text.strip():
            return []

        words = pseg.cut(text)
        entities: list[str] = []
        seen: set[str] = set()

        for word, flag in words:
            word = word.strip()
            if not word or len(word) < 2:
                continue

            if flag in _NOUN_FLAGS:
                if word not in seen:
                    entities.append(word)
                    seen.add(word)
            elif flag in _PROPER_FLAGS:
                if word not in seen:
                    entities.append(word)
                    seen.add(word)

        return entities


class SnowNlpEmotionAnalyzer(IEmotionAnalyzer):

    def analyze(self, text: str) -> float:
        if not HAS_SNOWNLP or not text.strip():
            return 0.5

        try:
            s = SnowNLP(text)
            return float(s.sentiments)
        except Exception:
            logger.exception("SnowNLP sentiment analysis failed")
            return 0.5


class CompositeExtractor(IEntityExtractor):

    def __init__(self, extractors: list[IEntityExtractor]) -> None:
        self._extractors = extractors

    def extract(self, text: str) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []

        for extractor in self._extractors:
            for entity in extractor.extract(text):
                if entity not in seen:
                    result.append(entity)
                    seen.add(entity)

        return result
