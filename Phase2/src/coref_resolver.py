"""
Optional Tier 2 preprocessing step: cross-message pronoun/coreference
resolution via fastcoref's spaCy pipeline component (the FCoref model), run
over a bounded window of a channel's messages before they're embedded — so a
short, pronoun-heavy reply ("yeah I agree with that", "she's right") has
*some* standalone semantic content for MiniLM to work with, instead of
almost none. This is the gap the semantic signal in
src/conversation_linker.py can't help with on its own.

Deliberately NOT part of the default installation or Docker image.
fastcoref pulls in torch + transformers (CPU wheels, but still real weight)
— see Phase2/requirements-coref.txt and the Dockerfile's optional
`runtime-coref` build stage. Every function here degrades to a no-op
(original text, unchanged) if the optional dependency isn't installed or
fails to load, so importing this module — or calling it with
CONVERSATION_LINKING_COREF_ENABLED unset — never requires fastcoref to be
present, and never breaks the rest of the pipeline if it isn't.

message.content itself, YAKE keyword extraction, and everything displayed to
a viewer always use the original text — coreference resolution only ever
changes what gets fed to the embedding model.
"""
import os
from typing import List, Optional

from src.social_models import Message

# A message boundary marker unlikely to appear in real chat text and
# structurally inert to the coref model (no pronouns, no nouns) — survives
# resolution untouched, so splitting the resolved document back on this
# exact string reliably recovers per-message text without needing to track
# token offsets ourselves.
_SEPARATOR = "\n<<<FASTCOREF_MSG_BOUNDARY>>>\n"

# Bounded so a busy channel's entire history is never joined into one
# document and run through a transformer at once — same "never an all-pairs
# comparison over the whole history" principle conversation_linker's own
# candidate window follows. Chunks don't overlap, so a pronoun right at the
# start of one chunk won't resolve against an antecedent at the end of the
# previous chunk; a deliberate, documented limitation in exchange for
# bounded, predictable compute.
_DEFAULT_WINDOW_MESSAGES = 20


def _env_bool(name: str, default: bool) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


def _env_int(name: str, default: int) -> int:
    val = os.getenv(name)
    return int(val) if val else default


class CorefResolver:
    """Lazily loads fastcoref's spaCy component on first use, so importing
    this module — or constructing this class — never requires the optional
    dependency to be installed. Only actually calling resolve_conversation()
    does, and even then it degrades to a no-op on failure rather than
    raising."""

    def __init__(self):
        self._nlp = None
        self._available: Optional[bool] = None

    def _ensure_loaded(self) -> bool:
        if self._available is not None:
            return self._available

        try:
            import spacy
            # Plain `import fastcoref` does NOT register the "fastcoref"
            # spaCy factory — fastcoref/__init__.py only exports
            # FCoref/LingMessCoref/CorefResult, and the @Language.factory
            # decorator lives in the spacy_component submodule, which
            # __init__.py never imports. Confirmed against fastcoref 2.1.6's
            # actual source after this failed with spaCy's E002 ("Can't find
            # factory for 'fastcoref'") on a plain `import fastcoref`.
            import fastcoref.spacy_component  # noqa: F401 — import registers the "fastcoref" spaCy factory

            # A real tagged pipeline is required here, not spacy.blank("en").
            # fastcoref's own resolve_text=True logic only substitutes a
            # mention if some span in its cluster has a NOUN/PROPN token.pos_
            # (see fastcoref's _get_span_noun_indices) — a blank pipeline
            # never runs a tagger, so pos_ is always empty and resolve_text
            # silently resolves nothing at all, even though the underlying
            # coref model still finds correct clusters. Confirmed by testing
            # both ways: spacy.blank("en") returned every coref_clusters
            # correctly but doc._.resolved_text was always identical to the
            # input; switching to en_core_web_sm fixed it immediately.
            # parser/ner/lemmatizer are disabled — only the tagger (and the
            # tok2vec it depends on) is actually needed for pos_.
            nlp = spacy.load("en_core_web_sm", disable=["parser", "ner", "lemmatizer"])
            nlp.add_pipe("fastcoref", config={"device": "cpu"})
            self._nlp = nlp
            self._available = True
        except Exception as e:
            print(
                f"CorefResolver: fastcoref unavailable ({e}) — coreference resolution disabled, "
                "using original message text. Install Phase2/requirements-coref.txt to enable it."
            )
            self._available = False

        return self._available

    def resolve_conversation(self, texts: List[str]) -> List[str]:
        """Given the message texts of ONE conversation window, in
        chronological order, returns a same-length list with pronouns
        resolved to their antecedent wherever fastcoref found a confident
        cross-message coreference cluster. Falls back to the original texts,
        unchanged, on any failure — this must never break the embedding step
        it feeds."""
        if not texts:
            return []
        if not self._ensure_loaded():
            return list(texts)

        joined = _SEPARATOR.join(texts)
        try:
            doc = self._nlp(joined, component_cfg={"fastcoref": {"resolve_text": True}})
            resolved = doc._.resolved_text
        except Exception as e:
            print(f"CorefResolver: resolution failed ({e}) — using original text for this batch.")
            return list(texts)

        parts = resolved.split(_SEPARATOR.strip())
        if len(parts) != len(texts):
            # Extremely unlikely (the separator is inert to the model), but
            # if it ever happens, misaligning message <-> resolved text
            # would be worse than just skipping resolution for this batch.
            print(
                "CorefResolver: resolved text didn't split back into the original message "
                "count — using original text for this batch."
            )
            return list(texts)

        return [p.strip() for p in parts]


# Module-level singleton, same convention as llm_service.retrieval_service —
# loaded once, reused across requests, never per-message.
coref_resolver = CorefResolver()


def resolve_messages_by_channel(messages: List[Message], resolver: Optional[CorefResolver] = None, window_messages: Optional[int] = None) -> List[str]:
    """Returns texts index-aligned with `messages`: each channel's messages
    are grouped (channel=None still groups together, e.g. all of a WhatsApp
    export) and resolved in chronological, bounded windows, so a pronoun can
    resolve against an antecedent earlier in the same conversation rather
    than only within its own message."""
    resolver = resolver or coref_resolver
    window = window_messages or _env_int("CONVERSATION_LINKING_COREF_WINDOW_MESSAGES", _DEFAULT_WINDOW_MESSAGES)

    by_channel = {}
    for idx, m in enumerate(messages):
        by_channel.setdefault(m.channel, []).append(idx)

    resolved_texts = [m.content for m in messages]
    for channel_idxs in by_channel.values():
        for chunk_start in range(0, len(channel_idxs), window):
            chunk_idxs = channel_idxs[chunk_start:chunk_start + window]
            chunk_texts = [messages[i].content for i in chunk_idxs]
            resolved = resolver.resolve_conversation(chunk_texts)
            for i, text in zip(chunk_idxs, resolved):
                resolved_texts[i] = text

    return resolved_texts


def get_embedding_texts(messages: List[Message]) -> List[str]:
    """The texts that should be fed to the embedding model: coreference-
    resolved if CONVERSATION_LINKING_COREF_ENABLED is set (and fastcoref is
    installed and loads successfully), otherwise each message's own content,
    unchanged. This is the single call site everything else — POST /analyse,
    the eval script, the classifier training script — should use instead of
    reading `.content` directly, so the toggle has one place to take effect."""
    if not _env_bool("CONVERSATION_LINKING_COREF_ENABLED", False):
        return [m.content for m in messages]
    return resolve_messages_by_channel(messages)
