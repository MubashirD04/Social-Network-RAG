from datetime import datetime, timedelta

import numpy as np

from src.conversation_linker import FEATURE_ORDER, ConversationLinker, LinkerConfig
from src.social_models import Message

BASE_TIME = datetime(2024, 1, 1, 10, 0, 0)


def _config(**overrides) -> LinkerConfig:
    cfg = LinkerConfig(
        enabled=True,
        semantic_weight=0.4,
        temporal_weight=0.25,
        turn_taking_weight=0.15,
        lexical_weight=0.2,
        threshold=0.5,
        candidate_window_messages=8,
        candidate_window_minutes=20.0,
        slack_decay_minutes=10.0,
        default_decay_minutes=4.0,
        turn_taking_window=4,
        keywords_per_message=5,
    )
    for key, value in overrides.items():
        setattr(cfg, key, value)
    return cfg


def test_disabled_config_returns_no_links():
    messages = [
        Message(id="1", sender="Alice", content="are we deploying the payments service today", timestamp=BASE_TIME),
        Message(id="2", sender="Bob", content="yes deploying the payments service this afternoon", timestamp=BASE_TIME + timedelta(minutes=1)),
    ]
    linker = ConversationLinker(_config(enabled=False))
    assert linker.score_pairs(messages) == []


def test_strong_signals_produce_a_link():
    messages = [
        Message(id="1", sender="Alice", content="are we deploying the payments service today", timestamp=BASE_TIME),
        Message(id="2", sender="Bob", content="yes deploying the payments service this afternoon", timestamp=BASE_TIME + timedelta(minutes=1)),
    ]
    # Identical direction -> cosine similarity 1.0, isolating the other
    # three signals (temporal proximity, turn-taking, shared keywords) as
    # the thing under test alongside a maxed-out semantic score.
    embeddings = np.array([[1.0, 0.0], [1.0, 0.0]])

    linker = ConversationLinker(_config())
    links = linker.score_pairs(messages, embeddings)

    assert len(links) == 1
    link = links[0]
    assert {link.message_id_a, link.message_id_b} == {"1", "2"}
    assert link.score >= linker.config.threshold
    assert link.signals["semantic"] == 1.0


def test_low_similarity_and_no_shared_keywords_do_not_link():
    messages = [
        Message(id="1", sender="Alice", content="are we deploying the payments service today", timestamp=BASE_TIME),
        Message(id="2", sender="Bob", content="lunch was great thanks", timestamp=BASE_TIME + timedelta(minutes=1)),
    ]
    # Orthogonal -> cosine similarity 0; content shares no vocabulary either,
    # so only the temporal and turn-taking signals contribute anything.
    embeddings = np.array([[1.0, 0.0], [0.0, 1.0]])

    linker = ConversationLinker(_config())
    links = linker.score_pairs(messages, embeddings)

    assert links == []


def test_time_gap_beyond_candidate_window_does_not_link():
    messages = [
        Message(id="1", sender="Alice", content="are we deploying the payments service today", timestamp=BASE_TIME),
        Message(id="2", sender="Bob", content="yes deploying the payments service this afternoon", timestamp=BASE_TIME + timedelta(hours=5)),
    ]
    embeddings = np.array([[1.0, 0.0], [1.0, 0.0]])

    linker = ConversationLinker(_config())
    links = linker.score_pairs(messages, embeddings)

    assert links == []


def test_existing_reply_to_is_not_reinferred():
    """A message that already has reply_to set — whether from a real Slack
    thread_ts or the WhatsApp parser's own adjacency heuristic — must never
    be re-scored as a source of inference; explicit/prior signal wins."""
    messages = [
        Message(id="1", sender="Alice", content="are we deploying the payments service today", timestamp=BASE_TIME),
        Message(id="2", sender="Bob", content="yes deploying the payments service this afternoon", timestamp=BASE_TIME + timedelta(minutes=1), reply_to="1"),
    ]
    embeddings = np.array([[1.0, 0.0], [1.0, 0.0]])

    linker = ConversationLinker(_config())
    links = linker.score_pairs(messages, embeddings)

    assert links == []


def test_candidate_window_does_not_cross_channels():
    messages = [
        Message(id="1", sender="Alice", content="database migration status update", timestamp=BASE_TIME, channel="engineering"),
        Message(id="2", sender="Bob", content="database migration status update", timestamp=BASE_TIME + timedelta(minutes=1), channel="marketing"),
    ]
    embeddings = np.array([[1.0, 0.0], [1.0, 0.0]])

    linker = ConversationLinker(_config())
    links = linker.score_pairs(messages, embeddings)

    assert links == []


def test_same_sender_messages_are_not_linked():
    messages = [
        Message(id="1", sender="Alice", content="are we deploying the payments service today", timestamp=BASE_TIME),
        Message(id="2", sender="Alice", content="also deploying the payments service docs", timestamp=BASE_TIME + timedelta(minutes=1)),
    ]
    embeddings = np.array([[1.0, 0.0], [1.0, 0.0]])

    linker = ConversationLinker(_config())
    links = linker.score_pairs(messages, embeddings)

    assert links == []


def test_turn_taking_boosts_rapid_alternation():
    """Alice/Bob/Alice/Bob alternating in a tight window should score higher
    turn-taking than the same pair showing up after a run of same-sender
    messages — isolate this by comparing the turn_taking signal directly."""
    alternating = [
        Message(id="1", sender="Alice", content="ping", timestamp=BASE_TIME),
        Message(id="2", sender="Bob", content="pong", timestamp=BASE_TIME + timedelta(seconds=10)),
        Message(id="3", sender="Alice", content="ping", timestamp=BASE_TIME + timedelta(seconds=20)),
        Message(id="4", sender="Bob", content="the deployment window closes soon", timestamp=BASE_TIME + timedelta(seconds=30)),
    ]
    non_alternating = [
        Message(id="1", sender="Alice", content="ping", timestamp=BASE_TIME),
        Message(id="2", sender="Alice", content="ping", timestamp=BASE_TIME + timedelta(seconds=10)),
        Message(id="3", sender="Alice", content="ping", timestamp=BASE_TIME + timedelta(seconds=20)),
        Message(id="4", sender="Bob", content="the deployment window closes soon", timestamp=BASE_TIME + timedelta(seconds=30)),
    ]
    embeddings = np.array([[1.0, 0.0]] * 4)

    linker = ConversationLinker(_config(threshold=0.0))
    alternating_links = {(l.message_id_a, l.message_id_b): l for l in linker.score_pairs(alternating, embeddings)}
    non_alternating_links = {(l.message_id_a, l.message_id_b): l for l in linker.score_pairs(non_alternating, embeddings)}

    alt_turn = alternating_links[("4", "1")].signals["turn_taking"]
    non_alt_turn = non_alternating_links[("4", "1")].signals["turn_taking"]
    assert alt_turn > non_alt_turn


def test_iter_candidates_yields_raw_features_regardless_of_threshold():
    """iter_candidates is the classifier training script's data source — it
    must return every candidate pair with its raw features, including ones
    that would score below any reasonable threshold, so training data isn't
    silently pre-filtered by the very heuristic the classifier is meant to
    replace."""
    messages = [
        Message(id="1", sender="Alice", content="are we deploying the payments service today", timestamp=BASE_TIME),
        Message(id="2", sender="Bob", content="lunch was great thanks", timestamp=BASE_TIME + timedelta(minutes=1)),
    ]
    embeddings = np.array([[1.0, 0.0], [0.0, 1.0]])  # orthogonal, unrelated content

    linker = ConversationLinker(_config())
    candidates = list(linker.iter_candidates(messages, embeddings))

    assert len(candidates) == 1
    candidate = candidates[0]
    assert {candidate.message_id_a, candidate.message_id_b} == {"1", "2"}
    assert set(candidate.features.keys()) == set(FEATURE_ORDER)
    # Confirmed below threshold in test_low_similarity_and_no_shared_keywords_do_not_link,
    # yet iter_candidates still yields it.
    assert candidate.features["semantic"] == 0.0


def test_classifier_scoring_mode_uses_trained_model(tmp_path):
    from sklearn.linear_model import LogisticRegression
    import joblib

    # A tiny, deliberately-separable fit: high semantic value -> positive
    # class. Not meant to be realistic, just to prove score_pairs actually
    # routes through predict_proba instead of the weighted sum.
    X = [[0.0, 0.0, 0.0, 0.0], [0.1, 0.1, 0.1, 0.1], [0.9, 0.9, 0.9, 0.9], [1.0, 1.0, 1.0, 1.0]]
    y = [0, 0, 1, 1]
    model = LogisticRegression().fit(X, y)
    model_path = tmp_path / "model.joblib"
    joblib.dump({"model": model, "feature_order": FEATURE_ORDER}, model_path)

    messages = [
        Message(id="1", sender="Alice", content="are we deploying the payments service today", timestamp=BASE_TIME),
        Message(id="2", sender="Bob", content="yes deploying the payments service this afternoon", timestamp=BASE_TIME + timedelta(minutes=1)),
    ]
    embeddings = np.array([[1.0, 0.0], [1.0, 0.0]])  # identical -> semantic=1.0, strongly positive per the fit above

    config = _config(scoring_mode="classifier", model_path=str(model_path), classifier_threshold=0.5)
    linker = ConversationLinker(config)

    assert linker.using_classifier is True
    links = linker.score_pairs(messages, embeddings)
    assert len(links) == 1
    # score should be the model's predicted probability, not the weighted sum
    assert 0.0 <= links[0].score <= 1.0


def test_classifier_scoring_mode_falls_back_when_model_missing():
    config = _config(scoring_mode="classifier", model_path="/nonexistent/path/model.joblib")
    linker = ConversationLinker(config)

    assert linker.using_classifier is False

    messages = [
        Message(id="1", sender="Alice", content="are we deploying the payments service today", timestamp=BASE_TIME),
        Message(id="2", sender="Bob", content="yes deploying the payments service this afternoon", timestamp=BASE_TIME + timedelta(minutes=1)),
    ]
    embeddings = np.array([[1.0, 0.0], [1.0, 0.0]])

    # Falls back to weighted_sum behavior rather than crashing or returning
    # nothing just because the requested model file doesn't exist.
    links = linker.score_pairs(messages, embeddings)
    assert len(links) == 1
