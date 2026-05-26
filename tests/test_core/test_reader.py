from __future__ import annotations

from src.core.belief_store import BeliefStore
from src.core.interfaces import Belief
from src.core.reader import Reader


class TestReader:

    def test_read_empty(self) -> None:
        store = BeliefStore()
        reader = Reader(store)
        messages = reader.read("conv_1")
        assert messages == []

    def test_read_single_belief(self) -> None:
        store = BeliefStore()
        store.add(
            "conv_1",
            Belief(
                id="b1",
                content="hello world",
                source="user",
                timestamp=1000,
            ),
        )
        reader = Reader(store)
        messages = reader.read("conv_1")
        assert len(messages) == 1
        assert messages[0]["role"] == "user"
        assert messages[0]["content"] == "hello world"

    def test_read_multiple_beliefs_in_order(self) -> None:
        store = BeliefStore()
        store.add(
            "conv_1",
            Belief(
                id="b1",
                content="first",
                source="user",
                timestamp=1000,
            ),
        )
        store.add(
            "conv_1",
            Belief(
                id="b2",
                content="second",
                source="assistant",
                timestamp=2000,
            ),
        )
        reader = Reader(store)
        messages = reader.read("conv_1")
        assert len(messages) == 2
        assert messages[0]["content"] == "first"
        assert messages[1]["content"] == "second"

    def test_read_with_max_tokens(self) -> None:
        store = BeliefStore()
        for i in range(5):
            store.add(
                "conv_1",
                Belief(
                    id=f"b{i}",
                    content="x" * 200,
                    source="user",
                    timestamp=i,
                ),
            )
        reader = Reader(store)
        messages = reader.read("conv_1", max_tokens=150)
        assert len(messages) < 5
        for msg in messages:
            assert msg["role"] == "user"

    def test_read_tool_beliefs_proper_role(self) -> None:
        store = BeliefStore()
        store.add(
            "conv_1",
            Belief(
                id="b1",
                content="user msg",
                source="user",
                timestamp=1000,
            ),
        )
        store.add(
            "conv_1",
            Belief(
                id="b2",
                content="tool result",
                source="tool",
                timestamp=2000,
            ),
        )
        reader = Reader(store)
        messages = reader.read("conv_1")
        assert len(messages) == 2
        assert messages[1]["role"] == "tool"

    def test_read_tool_as_role(self) -> None:
        store = BeliefStore()
        store.add(
            "conv_1",
            Belief(
                id="b1",
                content="tool data",
                source="tool",
                timestamp=1000,
            ),
        )
        reader = Reader(store)
        messages = reader.read("conv_1")
        assert messages[0]["role"] == "tool"
