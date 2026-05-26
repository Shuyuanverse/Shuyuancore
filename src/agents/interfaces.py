from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from src.core.interfaces import IBeliefStore


@dataclass
class UpdateContext:
    conversation_id: str
    user_id: str
    message: str
    history: list[dict[str, Any]] = field(default_factory=list)
    belief_store: IBeliefStore | None = None
    skill_store: Any = None
    perturbation_strength: float = 0.0
    user_preference_weights: dict[str, float] = field(
        default_factory=lambda: {"evidence": 1.0, "risk": 1.0, "innovation": 1.0}
    )


@dataclass
class UpdaterResult:
    content: str
    confidence: float
    reasoning: str
    source: str
    metadata: dict[str, Any] = field(default_factory=dict)


class IUpdater(ABC):

    @abstractmethod
    async def update(self, ctx: UpdateContext) -> UpdaterResult:
        ...


class IReviewer(ABC):

    @abstractmethod
    async def review(self, ctx: UpdateContext, draft: str) -> dict[str, Any]:
        ...


class IArbitrator(ABC):

    @abstractmethod
    async def arbitrate(
        self, ctx: UpdateContext, updater_results: list[UpdaterResult]
    ) -> str:
        ...


class ISubAgent(ABC):

    @abstractmethod
    async def run(self, task: str, scope: str, context: dict[str, Any]) -> str:
        ...