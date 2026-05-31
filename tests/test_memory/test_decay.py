from __future__ import annotations

from src.core.interfaces import Belief
from src.memory.decay import current_confidence

_DAY_MS: int = 86400000


class TestCurrentConfidence:

    def test_fresh_belief_no_decay(self) -> None:
        now = 1_000_000_000_000
        belief = Belief(
            id="b1",
            content="test",
            source="user",
            base_confidence=0.9,
            last_accessed=now,
            layer=1,
        )
        result = current_confidence(belief, now_ms=now)
        assert result == 0.9

    def test_belief_30_days_ago_lower_confidence(self) -> None:
        now = 1_000_000_000_000
        belief = Belief(
            id="b2",
            content="old belief",
            source="user",
            base_confidence=0.9,
            last_accessed=now - 30 * _DAY_MS,
            layer=3,
        )
        result = current_confidence(belief, now_ms=now)
        assert result < 0.9
        assert result >= 0.1

    def test_l1_decays_slower_than_l3(self) -> None:
        now = 1_000_000_000_000
        elapsed = 30 * _DAY_MS

        l1_belief = Belief(
            id="l1_b",
            content="L1 belief",
            source="user",
            base_confidence=1.0,
            last_accessed=now - elapsed,
            layer=1,
        )
        l3_belief = Belief(
            id="l3_b",
            content="L3 belief",
            source="user",
            base_confidence=1.0,
            last_accessed=now - elapsed,
            layer=3,
        )

        l1_conf = current_confidence(l1_belief, now_ms=now)
        l3_conf = current_confidence(l3_belief, now_ms=now)
        assert l1_conf > l3_conf

    def test_superseded_belief_confidence_zero(self) -> None:
        belief = Belief(
            id="b3",
            content="superseded",
            source="user",
            base_confidence=0.9,
            last_accessed=1_000_000_000_000,
            layer=1,
            status="superseded",
        )
        result = current_confidence(belief, now_ms=1_000_000_000_000)
        assert result == 0.0

    def test_different_layers_have_different_decay_rates(self) -> None:
        now = 1_000_000_000_000
        elapsed = 10 * _DAY_MS

        confs: dict[int, float] = {}
        for layer in (1, 2, 3, 4, 5, 6):
            belief = Belief(
                id=f"layer_{layer}",
                content=f"L{layer} belief",
                source="user",
                base_confidence=1.0,
                last_accessed=now - elapsed,
                layer=layer,
            )
            confs[layer] = current_confidence(belief, now_ms=now)

        assert confs[6] == 1.0, "Layer 6 decay rate is 0.0, should not decay"
        assert confs[1] > confs[2], "L1 should decay slower than L2"
        assert confs[2] > confs[3], "L2 should decay slower than L3"

    def test_confidence_floor_applies(self) -> None:
        now = 1_000_000_000_000
        belief = Belief(
            id="b4",
            content="very old belief",
            source="user",
            base_confidence=0.5,
            last_accessed=now - 365 * _DAY_MS,
            layer=3,
        )
        result = current_confidence(belief, now_ms=now)
        assert result == 0.1

    def test_explicit_now_ms_parameter(self) -> None:
        future = 2_000_000_000_000
        belief = Belief(
            id="b5",
            content="future belief",
            source="user",
            base_confidence=0.8,
            last_accessed=future,
            layer=1,
        )
        result = current_confidence(belief, now_ms=1_000_000_000_000)
        assert result == 0.8, "Should use explicit now_ms, not real clock"
