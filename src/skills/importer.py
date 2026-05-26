from __future__ import annotations

import json
import logging
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.config import get_settings
from src.core.interfaces import IBeliefStore
from src.exceptions import SkillImportError
from src.memory.decay import current_time_ms
from src.skills.manager import PersistentSkillGraph, PersistentSkillStore
from src.skills.utils import generate_node_id

logger = logging.getLogger(__name__)

_SKILLS_DIR = Path("data/skills")
_EXPORT_DIR = Path("data/exports")

_MANIFEST_SCHEMA_VERSION = "1.0"


async def export_skills(
    skill_names: list[str],
    skill_store: PersistentSkillStore,
    skill_graph: PersistentSkillGraph,
    output_path: str | None = None,
) -> str:
    _EXPORT_DIR.mkdir(parents=True, exist_ok=True)

    if output_path is None:
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        output_path = str(_EXPORT_DIR / f"skills_export_{ts}.zip")

    skills_data: list[dict[str, Any]] = []
    dependencies: set[str] = set()

    for name in skill_names:
        skill = await skill_store.get_skill(name)
        if skill is None:
            raise SkillImportError(f"Skill '{name}' not found")

        md_path = _SKILLS_DIR / f"{name}.md"
        md_content = ""
        if md_path.exists():
            md_content = md_path.read_text(encoding="utf-8")

        edges = await skill_graph.get_edges(node_name=name)

        skill_entry = {
            "node_data": skill,
            "edges": edges,
            "markdown": md_content,
        }
        skills_data.append(skill_entry)

        deps = skill.get("dependencies", [])
        if isinstance(deps, str):
            try:
                deps = json.loads(deps)
            except (json.JSONDecodeError, TypeError):
                deps = []
        for dep in deps:
            dependencies.add(dep)

    manifest = {
        "schema_version": _MANIFEST_SCHEMA_VERSION,
        "exported_at": datetime.now(timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        ),
        "skills": skill_names,
        "dependencies": list(dependencies),
    }

    tmp_zip = _EXPORT_DIR / f"_tmp_{datetime.now(timezone.utc).timestamp()}.zip"
    try:
        with zipfile.ZipFile(tmp_zip, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))

            for skill_entry in skills_data:
                name = skill_entry["node_data"].get("name", "unknown")
                md_content = skill_entry["markdown"]
                if md_content:
                    zf.writestr(f"skills/{name}.md", md_content)

                node_json = json.dumps(
                    skill_entry["node_data"],
                    ensure_ascii=False,
                    default=str,
                )
                zf.writestr(f"skills/{name}_node.json", node_json)

                edges_json = json.dumps(
                    skill_entry["edges"],
                    ensure_ascii=False,
                    default=str,
                )
                zf.writestr(f"skills/{name}_edges.json", edges_json)

        shutil.move(str(tmp_zip), output_path)
    except Exception:
        if tmp_zip.exists():
            tmp_zip.unlink()
        raise

    logger.info(
        "skills_exported count=%d path=%s", len(skill_names), output_path
    )
    return output_path


async def import_skills(
    zip_path: str,
    skill_store: PersistentSkillStore,
    skill_graph: PersistentSkillGraph,
) -> dict[str, Any]:
    zip_path_obj = Path(zip_path)
    if not zip_path_obj.exists():
        raise SkillImportError(f"Zip file not found: {zip_path}")

    with zipfile.ZipFile(zip_path_obj, "r") as zf:
        if "manifest.json" not in zf.namelist():
            raise SkillImportError("Missing manifest.json in skill package")

        manifest_raw = zf.read("manifest.json").decode("utf-8")
        manifest: dict[str, Any] = json.loads(manifest_raw)

        if manifest.get("schema_version") != _MANIFEST_SCHEMA_VERSION:
            raise SkillImportError(
                f"Unsupported schema version: "
                f"{manifest.get('schema_version')}"
            )

        skills_to_import = manifest.get("skills", [])
        dependencies = manifest.get("dependencies", [])

        missing_deps = []
        for dep in dependencies:
            existing = await skill_store.get_skill(dep)
            if existing is None:
                missing_deps.append(dep)

        imported: list[str] = []
        skipped: list[str] = []
        incomplete: list[str] = []

        for skill_name in skills_to_import:
            node_path = f"skills/{skill_name}_node.json"
            edges_path = f"skills/{skill_name}_edges.json"

            if node_path not in zf.namelist():
                logger.warning(
                    "missing_node_data skill=%s", skill_name
                )
                continue

            node_raw = zf.read(node_path).decode("utf-8")
            node_data: dict[str, Any] = json.loads(node_raw)

            existing = await skill_store.get_skill(skill_name)
            if existing is not None:
                existing_source = existing.get("version_history", [])
                if isinstance(existing_source, str):
                    try:
                        existing_source = json.loads(existing_source)
                    except (json.JSONDecodeError, TypeError):
                        existing_source = []
                is_community = False
                for v in (
                    existing_source
                    if isinstance(existing_source, list)
                    else []
                ):
                    if isinstance(v, dict) and v.get("source") == "community":
                        is_community = True
                        break
                if not is_community:
                    skipped.append(skill_name)
                    logger.info(
                        "skill_import_skipped name=%s (local skill exists)",
                        skill_name,
                    )
                    continue

            if missing_deps:
                node_data["status"] = "incomplete"
                incomplete.append(skill_name)

            node_data.pop("node_id", None)
            node_data.pop("belief_id", None)
            node_data.pop("created_at", None)
            node_data.pop("updated_at", None)
            node_data["node_id"] = generate_node_id()
            node_id = await skill_store.create_skill(
                node_data, conversation_id="import"
            )
            imported.append(skill_name)

            if edges_path in zf.namelist():
                edges_raw = zf.read(edges_path).decode("utf-8")
                edges_data: list[dict[str, Any]] = json.loads(edges_raw)
                for edge_data in edges_data:
                    edge_data.pop("edge_id", None)
                    edge_data.pop("created_at", None)
                    await skill_graph.add_edge(edge_data)

            md_path = f"skills/{skill_name}.md"
            if md_path in zf.namelist():
                md_content = zf.read(md_path).decode("utf-8")
                _SKILLS_DIR.mkdir(parents=True, exist_ok=True)
                dest_md = _SKILLS_DIR / f"{skill_name}.md"
                dest_md.write_text(md_content, encoding="utf-8")

    result = {
        "imported": imported,
        "skipped": skipped,
        "incomplete": incomplete,
        "missing_dependencies": missing_deps,
    }
    logger.info("skills_imported result=%s", result)
    return result