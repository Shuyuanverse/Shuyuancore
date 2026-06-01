from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.core.interfaces import Belief
from src.memory.wake import (
    WakeFrequencyTracker,
    wake_readiness,
    wake_score,
)


@pytest.fixture
def mock_entity_extractor() -> MagicMock:
    ext = MagicMock()
    ext.extract.return_value = []
    return ext


@pytest.fixture
def mock_emotion_analyzer() -> MagicMock:
    ana = MagicMock()
    ana.analyze.return_value = 0.5
    return ana


@pytest.fixture
def sample_belief() -> Belief:
    return Belief(
        id="b1",
        content="我喜欢编程和算法",
        source="user",
        confidence=0.9,
        base_confidence=0.9,
        last_accessed=9999999999999,
        layer=1,
        entities=["编程", "算法"],
        emotion=0.7,
    )


class TestWakeScore:

    def test_exact_keyword_match_high_score(
        self,
        sample_belief: Belief,
        mock_entity_extractor: MagicMock,
        mock_emotion_analyzer: MagicMock,
    ) -> None:
        mock_entity_extractor.extract.return_value = ["编程", "算法"]
        mock_emotion_analyzer.analyze.return_value = 0.7

        score = wake_score(
            sample_belief,
            "我喜欢编程和算法",
            mock_entity_extractor,
            mock_emotion_analyzer,
        )

        assert score > 0.3

    def test_no_match_low_score(
        self,
        sample_belief: Belief,
        mock_entity_extractor: MagicMock,
        mock_emotion_analyzer: MagicMock,
    ) -> None:
        mock_entity_extractor.extract.return_value = ["xyz"]
        mock_emotion_analyzer.analyze.return_value = 0.3

        score = wake_score(
            sample_belief,
            "今天天气真好",
            mock_entity_extractor,
            mock_emotion_analyzer,
        )

        assert score < 0.3

    def test_includes_emotion_match_component(
        self,
        sample_belief: Belief,
        mock_entity_extractor: MagicMock,
        mock_emotion_analyzer: MagicMock,
    ) -> None:
        mock_entity_extractor.extract.return_value = []
        mock_emotion_analyzer.analyze.return_value = 0.7

        score = wake_score(
            sample_belief,
            "hello world",
            mock_entity_extractor,
            mock_emotion_analyzer,
        )

        assert score > 0.0

    def test_emotion_floor_applies(
        self,
        sample_belief: Belief,
        mock_entity_extractor: MagicMock,
        mock_emotion_analyzer: MagicMock,
    ) -> None:
        mock_entity_extractor.extract.return_value = []
        mock_emotion_analyzer.analyze.return_value = 0.0

        score = wake_score(
            sample_belief,
            "something completely different",
            mock_entity_extractor,
            mock_emotion_analyzer,
        )

        assert score > 0.0, "Emotion floor should prevent zero score"


class TestWakeReadiness:

    def test_tech_keywords_high_readiness(self) -> None:
        score = wake_readiness("如何使用Python和Docker部署应用")
        assert score >= 0.4

    def test_short_command_low_readiness(self) -> None:
        score = wake_readiness("你好")
        assert score < 0.4

    def test_consecutive_tech_rounds_boosts_score(self) -> None:
        base = wake_readiness("Python代码")
        boosted = wake_readiness("Python代码", consecutive_tech_rounds=5)
        assert boosted > base

    def test_empty_message_zero_readiness(self) -> None:
        score = wake_readiness("")
        assert score == 0.0

    def test_score_capped_at_one(self) -> None:
        score = wake_readiness(
            "Python JavaScript Rust Docker Kubernetes Git Linux API SQL",
            consecutive_tech_rounds=10,
        )
        assert score <= 1.0


class TestWakeFrequencyTracker:

    def test_tracks_per_belief_calls(self) -> None:
        tracker = WakeFrequencyTracker(session_window_ms=300000)
        tracker.record_belief_wake("b1")
        tracker.record_belief_wake("b1")
        tracker.record_belief_wake("b1")

        count = tracker.belief_wake_count("b1", window_ms=3600000)
        assert count == 3

    def test_should_suppress_after_limit_exceeded(self) -> None:
        tracker = WakeFrequencyTracker(session_window_ms=300000)
        tracker._max_per_belief = 4

        for _ in range(3):
            tracker.record_belief_wake("b1")
        assert not tracker.should_suppress("b1")

        tracker.record_belief_wake("b1")
        assert tracker.should_suppress("b1")

    def test_reset_clears_state(self) -> None:
        tracker = WakeFrequencyTracker(session_window_ms=300000)
        tracker.record_belief_wake("b1")
        tracker.record_session_wake("s1")

        tracker.reset_all()

        assert tracker.belief_wake_count("b1") == 0
        assert tracker.session_wake_count("s1") == 0

    def test_session_wake_count_tracks_sessions(self) -> None:
        tracker = WakeFrequencyTracker(session_window_ms=300000)
        tracker.record_session_wake("s1")
        tracker.record_session_wake("s1")

        assert tracker.session_wake_count("s1") == 2

    def test_reset_session_clears_only_one_session(self) -> None:
        tracker = WakeFrequencyTracker(session_window_ms=300000)
        tracker.record_session_wake("s1")
        tracker.record_session_wake("s2")

        tracker.reset_session("s1")

        assert tracker.session_wake_count("s1") == 0
        assert tracker.session_wake_count("s2") == 1
