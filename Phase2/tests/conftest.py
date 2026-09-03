"""
Stubs out the heavy ML dependencies (fastembed, YAKE) with lightweight,
deterministic fakes so the automated test suite can run without downloading
real models. This must execute before any test module imports
src.llm_service (which instantiates a real TextEmbedding at import time) or
src.social_graph_builder (which imports src.llm_service).

Real model behaviour is exercised manually via `just demo` /
`python Phase2/social_demo.py`, not by this suite.
"""
import sys
import types

import numpy as np


class _FakeTextEmbedding:
    """Deterministic stand-in for fastembed.TextEmbedding.

    Encodes each text into a fixed-size vector derived from a hash of its
    content, so identical/similar strings hash close together and cosine
    similarity ranking logic can still be exercised meaningfully.
    """

    _DIM = 16

    def __init__(self, *args, **kwargs):
        pass

    def embed(self, texts):
        for text in texts:
            yield np.random.RandomState(abs(hash(text)) % (2**32)).rand(self._DIM)


_fake_fastembed_module = types.ModuleType("fastembed")
_fake_fastembed_module.TextEmbedding = _FakeTextEmbedding
sys.modules["fastembed"] = _fake_fastembed_module


class _FakeKeywordExtractor:
    """Deterministic stand-in for yake.KeywordExtractor.

    Returns the first `top` distinct words (len > 3) in the text, in the
    (keyword, score) tuple shape the real library returns (lower score =
    better, already sorted best-first). Enough to exercise topic-node
    creation and topic-to-message edge wiring without a real model.
    """

    def __init__(self, lan="en", n=2, top=5, *args, **kwargs):
        self.top = top

    def extract_keywords(self, text):
        seen = []
        for word in text.split():
            cleaned = word.strip(".,!?@").lower()
            if len(cleaned) > 3 and cleaned not in seen:
                seen.append(cleaned)
        return [(word, float(i)) for i, word in enumerate(seen[: self.top])]


_fake_yake_module = types.ModuleType("yake")
_fake_yake_module.KeywordExtractor = _FakeKeywordExtractor
sys.modules["yake"] = _fake_yake_module
