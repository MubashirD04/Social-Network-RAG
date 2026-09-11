"""
Infers conversational links between messages that carry no explicit reply
signal (Slack channel chatter posted outside a thread, and WhatsApp exports,
which have no reply metadata at all).

Explicit signal always wins: a message that already has `reply_to` set
(whether from a real Slack `thread_ts` or the WhatsApp parser's own adjacency
heuristic) is never re-scored as a source of inference here — this layer
only fills gaps left by upstream parsing, and produces a separate edge list
for the retrieval layer rather than touching the social graph's own
REPLIED_TO edges (see SocialGraphBuilder._infer_lexical_continuity, which
already covers that for the visualization graph using word-overlap alone).

Embeddings are the caller's responsibility to compute and pass in (index-
aligned with `messages`) — this module never calls the embedding model
itself, so unit tests can exercise scoring logic with small deterministic
vectors instead of loading a real model.
"""
import math
import os
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Dict, Iterator, List, Optional

import numpy as np

from src.social_models import Message

# Fixed order features are assembled in for a classifier's input vector.
# Shared between ConversationLinker and scripts/train_conversation_linker_classifier.py
# so a trained model and the runtime scorer never disagree about which
# column is which.
FEATURE_ORDER = ("semantic", "temporal", "turn_taking", "lexical")


def _env_bool(name: str, default: bool) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


def _env_float(name: str, default: float) -> float:
    val = os.getenv(name)
    return float(val) if val else default


def _env_int(name: str, default: int) -> int:
    val = os.getenv(name)
    return int(val) if val else default


@dataclass
class LinkerConfig:
    """Weights and thresholds are deliberately config, not hardcoded, since
    the right balance depends on the chat source (Slack vs WhatsApp have
    very different typical response latencies and channel sizes)."""

    enabled: bool = True

    semantic_weight: float = 0.4
    temporal_weight: float = 0.25
    turn_taking_weight: float = 0.15
    lexical_weight: float = 0.2

    threshold: float = 0.45

    # How far back an unlinked message is allowed to look for something it
    # plausibly continues — bounded on both message count and elapsed time
    # so this is never an all-pairs comparison over the whole history.
    candidate_window_messages: int = 8
    candidate_window_minutes: float = 20.0

    # Temporal-decay tuning constant (minutes), keyed by whether the message
    # carries a Slack channel (channel is None for WhatsApp/Telegram, which
    # are faster-paced, single-conversation chats). Deliberately kept within
    # a few multiples of candidate_window_minutes rather than much smaller —
    # a constant tight enough to be near-zero partway through the window
    # would leave semantic/lexical similarity doing all the work for any
    # reply that isn't near-instant, which defeats the point of a temporal
    # signal at all.
    slack_decay_minutes: float = 12.0
    default_decay_minutes: float = 6.0

    # How many recent messages (within the same channel) to look at when
    # scoring speaker turn-taking between a candidate pair.
    turn_taking_window: int = 4

    keywords_per_message: int = 5

    # Tier 2: swaps the hand-tuned weighted sum above for a small trained
    # classifier (see scripts/train_conversation_linker_classifier.py) over
    # the same four features. "weighted_sum" needs nothing extra and is the
    # safe default; "classifier" requires a model already trained and saved
    # at `model_path` — if that file isn't there (or scikit-learn/joblib
    # aren't installed), ConversationLinker logs a warning and falls back to
    # weighted_sum rather than failing the whole pipeline over it.
    scoring_mode: str = "weighted_sum"
    classifier_threshold: float = 0.5
    model_path: str = "Phase2/models/conversation_linker_classifier.joblib"

    @classmethod
    def from_env(cls) -> "LinkerConfig":
        return cls(
            enabled=_env_bool("CONVERSATION_LINKING_ENABLED", True),
            semantic_weight=_env_float("CONVERSATION_LINKING_SEMANTIC_WEIGHT", 0.4),
            temporal_weight=_env_float("CONVERSATION_LINKING_TEMPORAL_WEIGHT", 0.25),
            turn_taking_weight=_env_float("CONVERSATION_LINKING_TURN_TAKING_WEIGHT", 0.15),
            lexical_weight=_env_float("CONVERSATION_LINKING_LEXICAL_WEIGHT", 0.2),
            threshold=_env_float("CONVERSATION_LINKING_THRESHOLD", 0.45),
            candidate_window_messages=_env_int("CONVERSATION_LINKING_CANDIDATE_WINDOW_MESSAGES", 8),
            candidate_window_minutes=_env_float("CONVERSATION_LINKING_CANDIDATE_WINDOW_MINUTES", 20.0),
            slack_decay_minutes=_env_float("CONVERSATION_LINKING_SLACK_DECAY_MINUTES", 12.0),
            default_decay_minutes=_env_float("CONVERSATION_LINKING_DEFAULT_DECAY_MINUTES", 6.0),
            turn_taking_window=_env_int("CONVERSATION_LINKING_TURN_TAKING_WINDOW", 4),
            keywords_per_message=_env_int("CONVERSATION_LINKING_KEYWORDS_PER_MESSAGE", 5),
            scoring_mode=os.getenv("CONVERSATION_LINKING_SCORING_MODE", "weighted_sum").strip().lower(),
            classifier_threshold=_env_float("CONVERSATION_LINKING_CLASSIFIER_THRESHOLD", 0.5),
            model_path=os.getenv("CONVERSATION_LINKING_MODEL_PATH", "Phase2/models/conversation_linker_classifier.joblib"),
        )


@dataclass
class InferredLink:
    message_id_a: str
    message_id_b: str
    score: float
    signals: Dict[str, float] = field(default_factory=dict)


@dataclass
class Candidate:
    """One candidate pair within the scoring window, with its raw feature
    values — independent of scoring mode or threshold. Yielded regardless of
    whether it would ultimately score as a link, since the classifier
    training script needs the full candidate set (positives and negatives
    alike) to build a labeled dataset, not just the ones a threshold would
    keep."""
    message_id_a: str
    message_id_b: str
    features: Dict[str, float]


class ConversationLinker:
    def __init__(self, config: Optional[LinkerConfig] = None):
        self.config = config or LinkerConfig.from_env()
        # Lazy import, same convention as LLMService.extract_topics — keeps
        # this module importable in test environments that stub `yake` out
        # (see tests/conftest.py) without needing the real package installed.
        import yake

        self._keyword_extractor = yake.KeywordExtractor(lan="en", n=2, top=self.config.keywords_per_message)

        self._model = None
        if self.config.scoring_mode == "classifier":
            self._model = self._load_classifier(self.config.model_path)
            if self._model is None:
                print(
                    f"ConversationLinker: scoring_mode='classifier' but no usable model at "
                    f"'{self.config.model_path}' — falling back to weighted_sum for this instance. "
                    f"Run scripts/train_conversation_linker_classifier.py to produce one."
                )

    @staticmethod
    def _load_classifier(model_path: str):
        try:
            import joblib
            bundle = joblib.load(model_path)
            return bundle["model"] if isinstance(bundle, dict) else bundle
        except Exception:
            return None

    @property
    def using_classifier(self) -> bool:
        return self._model is not None

    def iter_candidates(self, messages: List[Message], embeddings: Optional[np.ndarray] = None) -> Iterator[Candidate]:
        """Yields every candidate pair within the configured per-channel,
        bounded lookback window — for every message that has no `reply_to`
        (real Slack thread_ts or the WhatsApp parser's own adjacency
        heuristic both count as already-linked and are skipped as inference
        sources). Never scores or thresholds; that's score_pairs' job, and
        the classifier training script uses this directly to build its
        labeled dataset from the full candidate set."""
        cfg = self.config
        if len(messages) < 2:
            return

        by_channel: Dict[Optional[str], List[int]] = {}
        for idx, m in enumerate(messages):
            by_channel.setdefault(m.channel, []).append(idx)

        keyword_cache: Dict[int, frozenset] = {}

        for channel, idxs in by_channel.items():
            decay_minutes = cfg.slack_decay_minutes if channel is not None else cfg.default_decay_minutes

            for pos, i in enumerate(idxs):
                msg = messages[i]
                if msg.reply_to:
                    continue

                window_start = max(0, pos - cfg.candidate_window_messages)
                for back_pos in range(pos - 1, window_start - 1, -1):
                    j = idxs[back_pos]
                    prior = messages[j]

                    if prior.sender == msg.sender:
                        continue

                    gap = msg.timestamp - prior.timestamp
                    if gap < timedelta(0):
                        continue
                    if gap > timedelta(minutes=cfg.candidate_window_minutes):
                        break

                    sem = self._semantic_similarity(embeddings, i, j)
                    temp = self._temporal_decay(gap, decay_minutes)
                    turn = self._turn_taking_score(messages, idxs, pos, back_pos)
                    lex = self._lexical_overlap(
                        self._get_keywords(i, messages, keyword_cache),
                        self._get_keywords(j, messages, keyword_cache),
                    )

                    yield Candidate(
                        message_id_a=msg.id,
                        message_id_b=prior.id,
                        features={"semantic": sem, "temporal": temp, "turn_taking": turn, "lexical": lex},
                    )

    def score_pairs(self, messages: List[Message], embeddings: Optional[np.ndarray] = None) -> List[InferredLink]:
        cfg = self.config
        if not cfg.enabled or len(messages) < 2:
            return []

        threshold = cfg.classifier_threshold if self.using_classifier else cfg.threshold

        links = []
        for candidate in self.iter_candidates(messages, embeddings):
            score = self._score_candidate(candidate.features)
            if score >= threshold:
                links.append(InferredLink(
                    message_id_a=candidate.message_id_a,
                    message_id_b=candidate.message_id_b,
                    score=round(score, 4),
                    signals={k: round(v, 4) for k, v in candidate.features.items()},
                ))

        return links

    def _score_candidate(self, features: Dict[str, float]) -> float:
        if self.using_classifier:
            vector = [[features[f] for f in FEATURE_ORDER]]
            return float(self._model.predict_proba(vector)[0][1])

        cfg = self.config
        return (
            cfg.semantic_weight * features["semantic"]
            + cfg.temporal_weight * features["temporal"]
            + cfg.turn_taking_weight * features["turn_taking"]
            + cfg.lexical_weight * features["lexical"]
        )

    def _semantic_similarity(self, embeddings: Optional[np.ndarray], i: int, j: int) -> float:
        if embeddings is None or len(embeddings) <= max(i, j):
            return 0.0
        a, b = embeddings[i], embeddings[j]
        norm_a = float(np.linalg.norm(a))
        norm_b = float(np.linalg.norm(b))
        if norm_a == 0.0 or norm_b == 0.0:
            return 0.0
        # Clamped at 0 — a negative cosine similarity just means "unrelated"
        # for this purpose, same convention llm_service.get_top_k_similar
        # uses (it discards similarities <= 0 outright).
        return max(0.0, float(np.dot(a, b) / (norm_a * norm_b)))

    def _temporal_decay(self, gap: timedelta, decay_minutes: float) -> float:
        if decay_minutes <= 0:
            return 0.0
        gap_minutes = gap.total_seconds() / 60.0
        return math.exp(-gap_minutes / decay_minutes)

    def _turn_taking_score(self, messages: List[Message], idxs: List[int], pos_i: int, pos_j: int) -> float:
        """Boosts pairs where the two speakers have been rapidly alternating
        in the recent window leading up to `pos_i` — a classic sign of a
        live back-and-forth rather than two unrelated messages that happen
        to share a channel."""
        cfg = self.config
        start = max(0, pos_i - cfg.turn_taking_window)
        window_positions = idxs[start:pos_i + 1]

        speaker_a = messages[idxs[pos_i]].sender
        speaker_b = messages[idxs[pos_j]].sender
        relevant = [
            messages[p].sender for p in window_positions
            if messages[p].sender in (speaker_a, speaker_b)
        ]
        if len(relevant) < 2:
            return 0.0

        switches = sum(1 for a, b in zip(relevant, relevant[1:]) if a != b)
        return switches / (len(relevant) - 1)

    def _get_keywords(self, idx: int, messages: List[Message], cache: Dict[int, frozenset]) -> frozenset:
        if idx in cache:
            return cache[idx]

        text = messages[idx].content.strip()
        if not text:
            cache[idx] = frozenset()
            return cache[idx]

        try:
            keywords = self._keyword_extractor.extract_keywords(text)
            cache[idx] = frozenset(kw.lower() for kw, _score in keywords)
        except Exception:
            cache[idx] = frozenset()

        return cache[idx]

    def _lexical_overlap(self, keywords_a: frozenset, keywords_b: frozenset) -> float:
        if not keywords_a or not keywords_b:
            return 0.0
        union = keywords_a | keywords_b
        if not union:
            return 0.0
        return len(keywords_a & keywords_b) / len(union)
