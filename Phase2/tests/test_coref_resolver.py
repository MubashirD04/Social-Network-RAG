import os
from datetime import datetime, timedelta

import pytest

from src.coref_resolver import (
    CorefResolver,
    get_embedding_texts,
    resolve_messages_by_channel,
)
from src.social_models import Message

BASE_TIME = datetime(2024, 1, 1, 10, 0, 0)


class _UppercaseResolver:
    """Stand-in for CorefResolver that doesn't need fastcoref installed —
    verifies resolve_messages_by_channel's channel-grouping/windowing wiring
    without depending on the optional real model."""

    def resolve_conversation(self, texts):
        return [t.upper() for t in texts]


def test_fastcoref_not_installed_falls_back_to_original_text():
    """fastcoref is an optional extra (requirements-coref.txt), not part of
    the default install this test suite runs against — resolve_conversation
    must degrade to returning the input unchanged rather than raising."""
    resolver = CorefResolver()
    texts = ["she said it was fine", "he agreed"]
    assert resolver.resolve_conversation(texts) == texts


def test_get_embedding_texts_defaults_to_original_content(monkeypatch):
    monkeypatch.delenv("CONVERSATION_LINKING_COREF_ENABLED", raising=False)
    messages = [
        Message(id="1", sender="Alice", content="hello there", timestamp=BASE_TIME),
        Message(id="2", sender="Bob", content="general kenobi", timestamp=BASE_TIME + timedelta(minutes=1)),
    ]
    assert get_embedding_texts(messages) == ["hello there", "general kenobi"]


def test_get_embedding_texts_enabled_but_unavailable_still_returns_original(monkeypatch):
    """Enabling the flag without the optional dependency installed must not
    crash the embedding step — it should silently behave as if disabled."""
    monkeypatch.setenv("CONVERSATION_LINKING_COREF_ENABLED", "true")
    messages = [
        Message(id="1", sender="Alice", content="hello there", timestamp=BASE_TIME),
        Message(id="2", sender="Bob", content="general kenobi", timestamp=BASE_TIME + timedelta(minutes=1)),
    ]
    assert get_embedding_texts(messages) == ["hello there", "general kenobi"]


def test_resolve_messages_by_channel_groups_and_preserves_order():
    messages = [
        Message(id="1", sender="Alice", content="a", timestamp=BASE_TIME, channel="engineering"),
        Message(id="2", sender="Bob", content="b", timestamp=BASE_TIME + timedelta(minutes=1), channel="watercooler"),
        Message(id="3", sender="Alice", content="c", timestamp=BASE_TIME + timedelta(minutes=2), channel="engineering"),
    ]
    resolved = resolve_messages_by_channel(messages, resolver=_UppercaseResolver())
    assert resolved == ["A", "B", "C"]


def test_resolve_messages_by_channel_chunks_within_window_size():
    """A channel longer than window_messages must be split into multiple
    resolve_conversation calls rather than one unbounded call — verified via
    a resolver stub that records how it was invoked."""
    calls = []

    class _RecordingResolver:
        def resolve_conversation(self, texts):
            calls.append(list(texts))
            return [t.upper() for t in texts]

    messages = [
        Message(id=str(i), sender="Alice", content=f"msg{i}", timestamp=BASE_TIME + timedelta(minutes=i), channel="engineering")
        for i in range(5)
    ]
    resolved = resolve_messages_by_channel(messages, resolver=_RecordingResolver(), window_messages=2)

    assert resolved == ["MSG0", "MSG1", "MSG2", "MSG3", "MSG4"]
    assert calls == [["msg0", "msg1"], ["msg2", "msg3"], ["msg4"]]
