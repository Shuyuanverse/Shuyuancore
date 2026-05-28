from __future__ import annotations

import re
import uuid
from collections import deque
from typing import Any

import yaml

from src.skills.models import SkillNode

_L0_PATTERN = re.compile(r"^##\s+因果链\s*$", re.MULTILINE)
_L1_PATTERN = re.compile(r"^##\s+完整因果链\s*$", re.MULTILINE)
_L2_PATTERN = re.compile(r"^##\s+详细推理\s*$", re.MULTILINE)
_SECTION_PATTERN = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)


def generate_node_id() -> str:
    return f"sk_{uuid.uuid4().hex[:12]}"


def generate_edge_id() -> str:
    return f"se_{uuid.uuid4().hex[:12]}"


def generate_usage_id() -> str:
    return f"su_{uuid.uuid4().hex[:12]}"


def parse_markdown_to_node(md_content: str) -> dict[str, Any]:
    lines = md_content.split("\n")
    front_matter: dict[str, Any] = {}
    body_lines: list[str] = []

    if lines and lines[0].strip() == "---":
        end_idx = -1
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                end_idx = i
                break
        if end_idx > 0:
            raw_yaml = "\n".join(lines[1:end_idx])
            front_matter = yaml.safe_load(raw_yaml) or {}
            body_lines = lines[end_idx + 1 :]
        else:
            body_lines = lines
    else:
        body_lines = lines

    body = "\n".join(body_lines)
    sections = _split_sections(body)

    node: dict[str, Any] = {
        "name": front_matter.get("name", ""),
        "description": front_matter.get("description", ""),
        "node_type": front_matter.get("node_type", "skill"),
        "tags": front_matter.get("tags", []),
        "preconditions": front_matter.get("preconditions", []),
        "causality_level0": sections.get("因果链", "").strip(),
        "causality_level1": sections.get("完整因果链", "").strip(),
        "causality_level2": sections.get("详细推理", "").strip(),
        "boundaries": front_matter.get("boundaries", []),
        "failure_modes": front_matter.get("failure_modes", []),
        "dependencies": front_matter.get("dependencies", []),
        "version_history": front_matter.get("version_history", []),
        "status": front_matter.get("status", "active"),
        "is_pinned": front_matter.get("is_pinned", False),
    }
    return node


def _split_sections(body: str) -> dict[str, str]:
    sections: dict[str, str] = {}
    parts = _SECTION_PATTERN.split(body)
    if not parts:
        return sections
    current_key: str | None = None
    current_lines: list[str] = []
    for part in parts:
        stripped = part.strip()
        if not stripped:
            continue
        if current_key is None:
            current_key = stripped
            current_lines = []
        else:
            current_lines.append(stripped)
            sections[current_key] = "\n".join(current_lines).strip()
            current_key = None
            current_lines = []
    return sections


def node_to_markdown(node: SkillNode) -> str:
    front = {
        "name": node.name,
        "description": node.description,
        "node_type": node.node_type,
        "tags": node.tags,
        "preconditions": node.preconditions,
        "boundaries": node.boundaries,
        "failure_modes": node.failure_modes,
        "dependencies": node.dependencies,
        "version_history": node.version_history,
        "status": node.status,
        "is_pinned": node.is_pinned,
    }
    front_str = yaml.dump(
        front, allow_unicode=True, default_flow_style=False, sort_keys=False
    )
    sections = ""
    if node.causality_level0:
        sections += f"\n## 因果链\n\n{node.causality_level0}\n"
    if node.causality_level1:
        sections += f"\n## 完整因果链\n\n{node.causality_level1}\n"
    if node.causality_level2:
        sections += f"\n## 详细推理\n\n{node.causality_level2}\n"
    return f"---\n{front_str}---{sections}"


def preconditions_satisfied(
    preconditions: list[dict[str, Any]],
    skill_confidence_map: dict[str, float],
    belief_confidence_map: dict[str, float],
) -> bool:
    for prec in preconditions:
        prec_type = prec.get("type", "")
        ref = prec.get("ref", "")
        min_conf = prec.get("min_confidence", 0.5)
        if prec_type == "skill":
            conf = skill_confidence_map.get(ref, 0.0)
            if conf < min_conf:
                return False
        elif prec_type == "belief":
            conf = belief_confidence_map.get(ref, 0.0)
            if conf < min_conf:
                return False
    return True


def bfs_traverse(
    graph: dict[str, list[str]],
    start: str,
) -> list[str]:
    visited: set[str] = set()
    result: list[str] = []
    queue: deque[str] = deque([start])
    while queue:
        node = queue.popleft()
        if node in visited:
            continue
        visited.add(node)
        result.append(node)
        for neighbor in graph.get(node, []):
            if neighbor not in visited:
                queue.append(neighbor)
    return result


def dfs_traverse(
    graph: dict[str, list[str]],
    start: str,
    visited: set[str] | None = None,
) -> list[str]:
    if visited is None:
        visited = set()
    if start in visited:
        return []
    visited.add(start)
    result: list[str] = [start]
    for neighbor in graph.get(start, []):
        result.extend(dfs_traverse(graph, neighbor, visited))
    return result
