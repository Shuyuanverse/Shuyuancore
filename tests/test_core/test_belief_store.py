from __future__ import annotations

from src.core.belief_store import BeliefStore
from src.core.interfaces import Belief


class TestBeliefStore:

    def test_add_and_get(self) -> None:
        store = BeliefStore()
        belief = Belief(
            id="b1", content="hello", source="user", timestamp=1000
        )
        store.add("conv_1", belief)
        beliefs = store.get("conv_1")
        assert len(beliefs) == 1
        assert beliefs[0].content == "hello"
        assert beliefs[0].source == "user"

    def test_get_empty_conversation(self) -> None:
        store = BeliefStore()
        beliefs = store.get("nonexistent")
        assert beliefs == []

    def test_get_with_limit(self) -> None:
        store = BeliefStore()
        for i in range(10):
            store.add(
                "conv_1",
                Belief(
                    id=f"b{i}",
                    content=f"msg {i}",
                    source="user",
                    timestamp=i,
                ),
            )
        beliefs = store.get("conv_1", limit=3)
        assert len(beliefs) == 3
        assert beliefs[-1].content == "msg 9"

    def test_clear(self) -> None:
        store = BeliefStore()
        store.add(
            "conv_1",
            Belief(id="b1", content="hello", source="user", timestamp=1),
        )
        store.clear("conv_1")
        assert store.get("conv_1") == []

    def test_clear_nonexistent(self) -> None:
        store = BeliefStore()
        store.clear("nonexistent")

    def test_remove(self) -> None:
        store = BeliefStore()
        store.add(
            "conv_1",
            Belief(id="b1", content="one", source="user", timestamp=1),
        )
        store.add(
            "conv_1",
            Belief(id="b2", content="two", source="user", timestamp=2),
        )
        store.remove("conv_1", "b1")
        beliefs = store.get("conv_1")
        assert len(beliefs) == 1
        assert beliefs[0].id == "b2"

    def test_remove_nonexistent(self) -> None:
        store = BeliefStore()
        store.remove("conv_1", "b1")

    def test_isolated_conversations(self) -> None:
        store = BeliefStore()
        store.add(
            "conv_1",
            Belief(id="b1", content="hello", source="user", timestamp=1),
        )
        store.add(
            "conv_2",
            Belief(id="b2", content="world", source="user", timestamp=1),
        )
        assert len(store.get("conv_1")) == 1
        assert len(store.get("conv_2")) == 1

    def test_create_belief(self) -> None:
        belief = BeliefStore.create_belief(
            content="test",
            source="user",
            confidence=0.8,
            dependencies=["dep1"],
            metadata={"key": "val"},
        )
        assert belief.content == "test"
        assert belief.source == "user"
        assert belief.confidence == 0.8
        assert belief.dependencies == ["dep1"]
        assert belief.metadata == {"key": "val"}
        assert belief.id != ""
        assert belief.timestamp > 0

    def test_create_belief_defaults(self) -> None:
        belief = BeliefStore.create_belief(
            content="hello", source="assistant"
        )
        assert belief.confidence == 1.0
        assert belief.dependencies == []
        assert belief.metadata == {}
