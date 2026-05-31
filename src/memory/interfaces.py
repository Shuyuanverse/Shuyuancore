from __future__ import annotations

from typing import Protocol


class IEntityExtractor(Protocol):
    def extract(self, text: str) -> list[str]: ...


class IEmotionAnalyzer(Protocol):
    def analyze(self, text: str) -> float: ...
