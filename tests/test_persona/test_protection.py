from __future__ import annotations

import pytest

from src.persona.profile import PersonaProfile, StyleDimensions
from src.persona.protection import ProtectionConfig, ProtectionResult, StyleProtectionPipeline


def _make_profile(persona_id: str = "test", has_anchor: bool = True) -> PersonaProfile:
    return PersonaProfile(
        persona_id=persona_id,
        mode="generic",
        style_dimensions=StyleDimensions(),
        style_anchor_vector=[0.5] * 128 if has_anchor else None,
        version=1,
    )


def _make_alternating_anchor(high_val: float = 0.9, low_val: float = 0.1) -> list[float]:
    result = []
    for i in range(64):
        result.append(high_val)
        result.append(low_val)
    return result


def _make_alternating_response(mode: str) -> list[float]:
    patterns = {
        "no_drift": (0.9, 0.1),
        "slight_drift": (0.5, 0.5),
        "moderate_drift": (0.3, 0.7),
        "high_drift": (0.1, 0.9),
    }
    high_val, low_val = patterns[mode]
    result = []
    for i in range(64):
        result.append(high_val)
        result.append(low_val)
    return result


class ControlledPipeline(StyleProtectionPipeline):
    def __init__(self, config=None, response_mode: str = "no_drift"):
        super().__init__(config)
        self._response_mode = response_mode

    def _extract_style_vector(self, text: str) -> list[float]:
        return _make_alternating_response(self._response_mode)


class TestNoDrift:
    def test_no_anchor_vector_passes_immediately(self) -> None:
        pipeline = StyleProtectionPipeline()
        profile = _make_profile(has_anchor=False)
        result = pipeline.check_and_adjust("test response", profile)
        assert result.passed is True
        assert result.drift_score == pytest.approx(0.0, abs=1e-10)
        assert result.alert_level == "none"

    def test_no_drift_when_vectors_identical(self) -> None:
        pipeline = ControlledPipeline(
            ProtectionConfig(review_drift_threshold=0.15, drift_threshold=0.25),
            response_mode="no_drift",
        )
        profile = _make_profile()
        profile.style_anchor_vector = _make_alternating_anchor()

        result = pipeline.check_and_adjust("", profile)
        assert result.passed is True
        assert result.drift_score == pytest.approx(0.0, abs=1e-10)
        assert result.alert_level == "none"


class TestSlightDrift:
    def test_slight_drift_between_thresholds(self) -> None:
        pipeline = ControlledPipeline(
            ProtectionConfig(review_drift_threshold=0.15, drift_threshold=0.25),
            response_mode="slight_drift",
        )
        profile = _make_profile()
        profile.style_anchor_vector = _make_alternating_anchor()

        result = pipeline.check_and_adjust("some response", profile)
        assert result.alert_level == "slight"
        assert result.passed is True
        assert 0.15 <= result.drift_score < 0.25

    def test_slight_drift_returns_passed_true(self) -> None:
        pipeline = ControlledPipeline(
            ProtectionConfig(review_drift_threshold=0.15, drift_threshold=0.25),
            response_mode="slight_drift",
        )
        profile = _make_profile()
        profile.style_anchor_vector = _make_alternating_anchor()

        result = pipeline.check_and_adjust("some response", profile)
        assert result.drift_score < 0.25
        assert result.passed is True


class TestModerateDrift:
    def test_moderate_drift_above_drift_threshold(self) -> None:
        pipeline = ControlledPipeline(
            ProtectionConfig(review_drift_threshold=0.15, drift_threshold=0.25),
            response_mode="moderate_drift",
        )
        profile = _make_profile()
        profile.style_anchor_vector = _make_alternating_anchor()

        result = pipeline.check_and_adjust("very different response", profile)
        assert result.alert_level == "moderate"
        assert result.passed is False
        assert result.drift_score > 0.25

    def test_moderate_drift_generates_calibration_prompt(self) -> None:
        pipeline = ControlledPipeline(
            ProtectionConfig(review_drift_threshold=0.15, drift_threshold=0.25),
            response_mode="moderate_drift",
        )
        profile = _make_profile()
        profile.style_anchor_vector = _make_alternating_anchor()

        result = pipeline.check_and_adjust("very different response", profile)
        assert "风格校准" in result.calibration_prompt
        assert "当前漂移" in result.calibration_prompt

    def test_moderate_drift_increments_counter(self) -> None:
        from src.persona.protection import _DRIFT_COUNTER
        _DRIFT_COUNTER.clear()

        pipeline = ControlledPipeline(
            ProtectionConfig(review_drift_threshold=0.15, drift_threshold=0.25),
            response_mode="moderate_drift",
        )
        profile = _make_profile("test_counter")
        profile.style_anchor_vector = _make_alternating_anchor()

        pipeline.check_and_adjust("response1", profile)
        assert _DRIFT_COUNTER.get("test_counter") == 1


class TestSevereDrift:
    def test_severe_drift_after_three_consecutive(self) -> None:
        from src.persona.protection import _DRIFT_COUNTER
        _DRIFT_COUNTER.clear()

        pipeline = ControlledPipeline(
            ProtectionConfig(review_drift_threshold=0.15, drift_threshold=0.25),
            response_mode="moderate_drift",
        )
        profile = _make_profile("test_severe")
        profile.style_anchor_vector = _make_alternating_anchor()

        for _ in range(3):
            pipeline.check_and_adjust("response", profile)

        result = pipeline.check_and_adjust("response", profile)
        assert result.alert_level == "severe"

    def test_severe_drift_reset_on_new_persona(self) -> None:
        from src.persona.protection import _DRIFT_COUNTER
        _DRIFT_COUNTER.clear()

        pipeline = ControlledPipeline(
            ProtectionConfig(review_drift_threshold=0.15, drift_threshold=0.25),
            response_mode="moderate_drift",
        )
        profile_a = _make_profile("persona_a")
        profile_a.style_anchor_vector = _make_alternating_anchor()
        profile_b = _make_profile("persona_b")
        profile_b.style_anchor_vector = _make_alternating_anchor()

        for _ in range(3):
            pipeline.check_and_adjust("response", profile_a)

        result_b = pipeline.check_and_adjust("response", profile_b)
        assert result_b.alert_level == "moderate"
        assert result_b.passed is False

        result_a = pipeline.check_and_adjust("response", profile_a)
        assert result_a.alert_level == "severe"


class TestAdjustmentLogic:
    def test_negative_high_emotion_adjusts_response(self) -> None:
        pipeline = ControlledPipeline(
            ProtectionConfig(review_drift_threshold=0.15, drift_threshold=0.25),
            response_mode="moderate_drift",
        )
        profile = _make_profile("test_adjust")
        profile.style_anchor_vector = _make_alternating_anchor()

        class MockPerception:
            user_emotion_hint = "negative_high"

        result = pipeline.check_and_adjust(
            "原始回复", profile, perception=MockPerception(),
        )
        assert result.adjusted_response is not None
        assert "我理解你的感受" in result.adjusted_response

    def test_high_drift_generic_adjustment(self) -> None:
        pipeline = ControlledPipeline(
            ProtectionConfig(review_drift_threshold=0.15, drift_threshold=0.25),
            response_mode="high_drift",
        )
        profile = _make_profile("test_generic_adjust")
        profile.style_anchor_vector = _make_alternating_anchor()

        class MockPerception:
            user_emotion_hint = "neutral"

        result = pipeline.check_and_adjust(
            "原始回复", profile, perception=MockPerception(),
        )
        assert result.adjusted_response is not None
        assert "简单来说" in result.adjusted_response

    def test_low_drift_no_adjustment(self) -> None:
        pipeline = ControlledPipeline(
            ProtectionConfig(review_drift_threshold=0.15, drift_threshold=0.25),
            response_mode="no_drift",
        )
        profile = _make_profile("test_no_adjust")
        profile.style_anchor_vector = _make_alternating_anchor()

        result = pipeline.check_and_adjust("normal response", profile)
        assert result.adjusted_response is None

    def test_cosine_distance_with_different_lengths(self) -> None:
        pipeline = StyleProtectionPipeline()
        dist = pipeline._cosine_distance([0.5] * 128, [0.5] * 64)
        assert dist == 1.0


class TestPerceptionAwareAdjustment:
    def test_perception_none_no_adjustment(self) -> None:
        pipeline = ControlledPipeline(
            ProtectionConfig(review_drift_threshold=0.15, drift_threshold=0.25),
            response_mode="moderate_drift",
        )
        profile = _make_profile("test_perception_none")
        profile.style_anchor_vector = _make_alternating_anchor()

        result = pipeline.check_and_adjust("response", profile, perception=None)
        assert result.adjusted_response is None