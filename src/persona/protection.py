from __future__ import annotations
import math
import logging
from dataclasses import dataclass, field
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

        if drift < self.config.review_drift_threshold:
            return result

        if drift < self.config.drift_threshold:
            result.alert_level = "slight"
            logger.info("[protection] 轻微漂移: %.4f (persona=%s)", drift, profile.persona_id)
            return result

        result.alert_level = "moderate"
        result.passed = False
        result.calibration_prompt = self._build_calibration_prompt(drift, profile)

        pid = profile.persona_id
        count = _DRIFT_COUNTER.get(pid, 0) + 1
        _DRIFT_COUNTER[pid] = count
        if count >= _SEVERE_ALERT_THRESHOLD:
            result.alert_level = "severe"
            logger.warning("[protection] 严重漂移告警: %d 次连续漂移 (persona=%s)", count, pid)

        if perception is not None:
            result.adjusted_response = self._adjust_response(response_text, result, perception)

        logger.info("[protection] drift=%.4f level=%s persona=%s", drift, result.alert_level, profile.persona_id)
        return result

    def _extract_style_vector(self, text: str) -> list[float]:
        from src.persona.style_encoder import StyleEncoder
        encoder = StyleEncoder()
        dims = encoder.encode(text)
        raw = [
            dims.formality, dims.warmth, dims.directness,
            dims.playfulness, dims.detail_orientation,
            dims.emotional_expression, dims.pace,
        ]
        import numpy as np
        seed = int(sum(raw) * 1e6) % (2**31)
        rng = np.random.default_rng(seed=seed)
        repeat = self.config.anchor_dimensions // 7 + 1
        base = np.array(raw * repeat)[:self.config.anchor_dimensions]
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

    def _adjust_response(self, text: str, result: ProtectionResult, perception: object) -> Optional[str]:
        perception = getattr(perception, "user_emotion_hint", None)
        if perception == "negative_high" and result.drift_score >= 0.15:
            return text + "\n\n（我理解你的感受，让我重新调整一下表达方式）"

        if result.drift_score >= 0.25:
            return text + "\n\n简单来说，"

        return None