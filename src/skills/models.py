from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SkillNode:
    node_id: str
    name: str
    node_type: str = "skill"
    belief_id: str = ""
    source: str = "manual"
    description: str = ""
    tags: list[str] = field(default_factory=list)
    preconditions: list[dict[str, Any]] = field(default_factory=list)
    causality_level0: str = ""
    causality_level1: str = ""
    causality_level2: str = ""
    boundaries: list[str] = field(default_factory=list)
    failure_modes: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    version_history: list[dict[str, Any]] = field(default_factory=list)
    status: str = "active"
    is_pinned: bool = False
    created_at: int = 0
    updated_at: int = 0
    confidence: float = 0.6
    last_accessed: int = 0


@dataclass
class SkillEdge:
    edge_id: str
    from_node: str
    to_node: str
    edge_type: str = "enables"
    created_at: int = 0


@dataclass
class SkillUsage:
    usage_id: str
    skill_name: str
    conversation_id: str = ""
    invoked_at: int = 0
    success: bool | None = None
    user_feedback: str | None = None
    duration_ms: int | None = None
