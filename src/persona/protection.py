from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Optional

from src.persona.profile import PersonaProfile

logger = logging.getLogger(__name__)


@dataclass
class ProtectionConfig:
    drift_threshold: float = 0.25
    review_drift_threshold: float = 0.15
    enable_proactive: bool = False
    anchor_dimensions: int = 128


@dataclass
class ProtectionResult:
    passed: bool = True
    drift_score: float = 0.0
    alert_level: str = "none"
    calibration_prompt: str = ""
    adjusted_response: Optional[str] = None


_DRIFT_COUNTER: dict[str, int] = {}
_SEVERE_ALERT_THRESHOLD = 3


class StyleProtectionPipeline:
    def __init__(self, config: Optional[ProtectionConfig] = None):
        self.config = config or ProtectionConfig()

    def check_and_adjust(
        self,
        response_text: str,
        profile: PersonaProfile,
        perception: object = None,
    ) -> ProtectionResult:
        result = ProtectionResult()

        if not profile.style_anchor_vector:
            return result

        response_vec = self._extract_style_vector(response_text)
        drift = self._cosine_distance(response_vec, profile.style_anchor_vector)
        result.drift_score = drift

        pid = profile.persona_id

        if drift < self.config.review_drift_threshold:
            _DRIFT_COUNTER[pid] = 0
            return result

        if drift < self.config.drift_threshold:
            _DRIFT_COUNTER[pid] = 0
            result.alert_level = "slight"
            logger.info("[protection] 轻微漂移: %.4f (persona=%s)", drift, pid)
            return result

        count = _DRIFT_COUNTER.get(pid, 0) + 1
        _DRIFT_COUNTER[pid] = count

        result.passed = False
        result.calibration_prompt = self._build_calibration_prompt(drift, profile)

        if count >= _SEVERE_ALERT_THRESHOLD:
            result.alert_level = "severe"
            result.calibration_prompt = (
                "【强制风格校准】已连续 %d 次检测到严重风格漂移（当前漂移: %.2f）。"
                "请严格遵守以下风格特征回复，不允许偏离：\n%s"
            ) % (count, drift, profile.style_dimensions.to_prompt_text())
            logger.warning(
                "[protection] 强制校准触发: %d 次连续漂移 (persona=%s, drift=%.4f)",
                count,
                pid,
                drift,
            )
            _DRIFT_COUNTER[pid] = 0
        else:
            result.alert_level = "moderate"

        if perception is not None:
            result.adjusted_response = self._adjust_response(response_text, result, perception)

        logger.info(
            "[protection] drift=%.4f level=%s persona=%s counter=%d",
            drift,
            result.alert_level,
            pid,
            count,
        )
        return result

    def _extract_style_vector(self, text: str) -> list[float]:
        from src.persona.style.style_encoder import StyleDimension, StyleEncoder

        encoder = StyleEncoder()
        profile = encoder.encode(text)
        raw = [
            profile.dimensions.get(
                "colloquial", StyleDimension(name="colloquial", value=0.5)
            ).value,
            profile.dimensions.get("formal", StyleDimension(name="formal", value=0.5)).value,
            profile.dimensions.get("emotional", StyleDimension(name="emotional", value=0.5)).value,
            profile.dimensions.get(
                "interactive", StyleDimension(name="interactive", value=0.5)
            ).value,
            profile.dimensions.get("logical", StyleDimension(name="logical", value=0.5)).value,
            profile.dimensions.get("concise", StyleDimension(name="concise", value=0.5)).value,
            profile.dimensions.get(
                "expressive", StyleDimension(name="expressive", value=0.5)
            ).value,
        ]

        import numpy as np

        seed = int(sum(raw) * 1e6) % (2**31)
        rng = np.random.default_rng(seed=seed)
        repeat = self.config.anchor_dimensions // 7 + 1
        base = np.array(raw * repeat)[: self.config.anchor_dimensions]
        noise = rng.normal(0, 0.02, self.config.anchor_dimensions)
        vec = np.clip(base + noise, 0, 1)
        return vec.tolist()

    def _cosine_distance(self, v1: list[float], v2: list[float]) -> float:
        if len(v1) != len(v2):
            return 1.0
        dot = sum(a * b for a, b in zip(v1, v2))
        n1 = math.sqrt(sum(a * a for a in v1))
        n2 = math.sqrt(sum(b * b for b in v2))
        if n1 == 0 or n2 == 0:
            return 1.0
        return 1.0 - (dot / (n1 * n2))

    def _build_calibration_prompt(self, drift_score: float, profile: PersonaProfile) -> str:
        prompt = "【风格校准】请注意在接下来的对话中保持以下风格特征：\n"
        prompt += profile.style_dimensions.to_prompt_text() + "\n"
        prompt += f"当前漂移：{drift_score:.2f}（阈值：{self.config.drift_threshold}）"
        return prompt

    def _adjust_response(
        self,
        text: str,
        result: ProtectionResult,
        perception: object,
    ) -> Optional[str]:
        perception = getattr(perception, "user_emotion_hint", None)
        if perception == "negative_high" and result.drift_score >= 0.15:
            return text + "\n\n（我理解你的感受，让我重新调整一下表达方式）"

        if result.drift_score >= 0.25:
            return text + "\n\n简单来说，"

        return None
