from __future__ import annotations

import time

import pytest

from src.gateway.utils import (
    decode_cursor,
    encode_cursor,
    set_cursor_secret,
)


class TestCursorEncoding:
    @pytest.fixture(autouse=True)
    def _setup_secret(self) -> None:
        set_cursor_secret("test-secret-key-12345")

    def test_encode_decode_roundtrip(self) -> None:
        ts = 1700000000
        eid = "conv-abc123"
        cursor = encode_cursor(ts, eid)
        result = decode_cursor(cursor)
        assert result is not None
        assert result == (ts, eid)

    def test_decode_tampered_cursor_returns_none(self) -> None:
        ts = 1700000000
        eid = "conv-abc123"
        cursor = encode_cursor(ts, eid)

        tampered = cursor[:-1] + ("A" if cursor[-1] != "A" else "B")
        assert decode_cursor(tampered) is None

    def test_decode_invalid_cursor_returns_none(self) -> None:
        assert decode_cursor("not-a-valid-base64!!!") is None
        assert decode_cursor("") is None
        assert decode_cursor("YWJj") is None

    def test_different_secrets_produce_incompatible_cursors(self) -> None:
        ts = 1700000000
        eid = "conv-test"
        cursor = encode_cursor(ts, eid)

        set_cursor_secret("different-secret-key")
        assert decode_cursor(cursor) is None

        set_cursor_secret("test-secret-key-12345")
        assert decode_cursor(cursor) is not None

    def test_expired_cursor_returns_none(self) -> None:
        old_ts = int(time.time()) - 7200
        cursor = encode_cursor(old_ts, "conv-expired", expires_in=0)
        time.sleep(1)
        assert decode_cursor(cursor) is None

    def test_non_expired_cursor_valid(self) -> None:
        ts = int(time.time())
        cursor = encode_cursor(ts, "conv-fresh", expires_in=300)
        assert decode_cursor(cursor) is not None

    def test_entity_id_with_underscores(self) -> None:
        ts = 1700000000
        eid = "user_a_conv_123"
        cursor = encode_cursor(ts, eid)
        result = decode_cursor(cursor)
        assert result is not None
        assert result == (ts, eid)
