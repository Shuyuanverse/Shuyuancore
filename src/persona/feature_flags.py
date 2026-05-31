"""该模块仅服务于 persona 模块，提供特性标志（feature flags）的查询接口。"""

from __future__ import annotations

import logging

from src.config import get_settings

logger = logging.getLogger(__name__)


def is_enabled(flag_name: str) -> bool:
    settings = get_settings()
    flags = settings.persona.feature_flags
    if flag_name == "ENABLE_HARD_FACT_GUARD":
        return flags.enable_hard_fact_guard
    if not flags.enable_persona_system:
        return False
    mapping = {
        "ENABLE_PERSONA_SYSTEM": "enable_persona_system",
        "ENABLE_STYLE_PROTECTION": "enable_style_protection",
        "ENABLE_IDENTITY_INJECTION": "enable_identity_injection",
        "ENABLE_PERCEPTION": "enable_perception",
        "ENABLE_SELF_REVIEW": "enable_self_review",
        "ENABLE_ADJUSTMENT": "enable_adjustment",
        "ENABLE_AUTONOMOUS_EVOLUTION": "enable_autonomous_evolution",
        "ENABLE_INNER_REACTION": "enable_inner_reaction",
    }
    key = mapping.get(flag_name, "")
    return getattr(flags, key, False) if key else False


def get_all_flags() -> dict:
    settings = get_settings()
    flags = settings.persona.feature_flags
    return {
        "ENABLE_PERSONA_SYSTEM": flags.enable_persona_system,
        "ENABLE_HARD_FACT_GUARD": flags.enable_hard_fact_guard,
        "ENABLE_STYLE_PROTECTION": is_enabled("ENABLE_STYLE_PROTECTION"),
        "ENABLE_IDENTITY_INJECTION": is_enabled("ENABLE_IDENTITY_INJECTION"),
        "ENABLE_PERCEPTION": is_enabled("ENABLE_PERCEPTION"),
        "ENABLE_SELF_REVIEW": is_enabled("ENABLE_SELF_REVIEW"),
        "ENABLE_ADJUSTMENT": is_enabled("ENABLE_ADJUSTMENT"),
        "ENABLE_AUTONOMOUS_EVOLUTION": is_enabled("ENABLE_AUTONOMOUS_EVOLUTION"),
        "ENABLE_INNER_REACTION": is_enabled("ENABLE_INNER_REACTION"),
    }


def log_startup_status() -> None:
    flags = get_all_flags()
    parts = [f"{k}={'ON' if v else 'OFF'}" for k, v in flags.items()]
    logger.info("[persona] feature flags: %s", ", ".join(parts))
