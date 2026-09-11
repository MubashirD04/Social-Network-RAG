import gc
from typing import List, Optional, Set
from fastembed import TextEmbedding
import numpy as np

# fastembed/onnxruntime's peak memory grows with the size of a single
# embed() call and is never released afterward, regardless of thread count
# or the CPU memory arena setting (both were profiled and ruled out).
# Chunking bounds the working set instead of letting it scale with the
# number of texts embedded.
_EMBED_CHUNK_SIZE = 32

class LLMService:
    """
    Provides local embedding generation for the Retrieval Layer.
    Uses fastembed (ONNX Runtime, no PyTorch) to encode text into semantic vectors.
    """

    def __init__(self):
        print("Loading fastembed model...")
        self.embedder = TextEmbedding(model_name="sentence-transformers/all-MiniLM-L6-v2")
        self._dimension = len(next(iter(self.embedder.embed(["dimension probe"]))))
        print(f"Embeddings model loaded successfully (dimension: {self._dimension})")

    def generate_embeddings(self, texts: List[str]) -> np.ndarray:
        """
        Generate embeddings for a list of texts using local model.
        Returns a numpy array of embeddings.
        """
        if not texts:
            return np.array([])

        chunks = []
        for i in range(0, len(texts), _EMBED_CHUNK_SIZE):
            batch = texts[i:i + _EMBED_CHUNK_SIZE]
            chunks.append(np.array(list(self.embedder.embed(batch))))
            gc.collect()

        return np.vstack(chunks)

    def get_embeddings_dimension(self) -> int:
        return self._dimension

    def get_top_k_similar(self, query: str, embeddings: np.ndarray, k: int = 5) -> List[tuple[int, float]]:
        """
        Compute cosine similarity between the query and stored embeddings.
        Returns indices of top K results along with their similarity scores.
        """
        if embeddings.shape[0] == 0:
            return []

        query_embedding = self.generate_embeddings([query])[0]

        # Calculate cosine similarity using numpy dot product
        # normalise vectors to unit length first
        query_norm = np.linalg.norm(query_embedding)
        if query_norm == 0:
            return []
        query_embedding = query_embedding / query_norm

        norms = np.linalg.norm(embeddings, axis=1)
        # Avoid division by zero
        valid_indices = norms > 0

        similarities = np.zeros(embeddings.shape[0])
        safe_embeddings = embeddings[valid_indices] / norms[valid_indices, np.newaxis]

        similarities[valid_indices] = np.dot(safe_embeddings, query_embedding)

        # Get top K indices
        # argsort sorts in ascending order, so we reverse it
        top_indices = np.argsort(similarities)[::-1][:k]

        return [(int(idx), float(similarities[idx])) for idx in top_indices if similarities[idx] > 0]

    async def extract_topics(self, messages: List[str], top_n: int = 5, exclude_terms: Optional[Set[str]] = None) -> List[str]:
        """
        Extract main topics from a list of messages using YAKE.

        `exclude_terms` filters out candidate keywords that exactly match one
        of these terms (case-insensitive) — e.g. chat participant names,
        which otherwise surface as "topics" simply for being frequent,
        capitalized tokens rather than anything actually discussed.

        Also dedupes candidates whose words are a strict subset of another
        candidate's words (e.g. "page" alongside "pricing page" and "page
        redesign") — YAKE scores unigrams that are pieces of a real n-gram
        topic well since they inherit its frequency, but keeping both just
        burns a slot on a less informative repeat of a topic already listed.
        When a more specific phrase shows up after its subset was already
        accepted, it replaces that entry rather than being dropped alongside
        it, so the more informative version wins regardless of which one
        YAKE happened to rank higher.
        """
        try:
            import yake

            # Combine messages into a single text for topic extraction
            text = " ".join(messages)
            if not text.strip():
                return []

            exclude = {t.lower() for t in (exclude_terms or [])}
            # Over-fetch candidates so filtering out excluded terms and
            # subset duplicates still leaves top_n real topics.
            kw_extractor = yake.KeywordExtractor(lan="en", n=2, top=top_n * 5)
            keywords = kw_extractor.extract_keywords(text)

            # Scans every over-fetched candidate (not just the first top_n)
            # so a more specific phrase later in the ranking still gets the
            # chance to replace a subset already accepted earlier — only the
            # final slice below enforces top_n.
            accepted: List[str] = []
            accepted_tokens: List[frozenset] = []
            for kw, _score in keywords:
                if kw.lower() in exclude:
                    continue

                tokens = frozenset(kw.lower().split())

                # An already-accepted topic that this candidate's words fully
                # cover is strictly less specific — drop it in favor of this
                # candidate instead of keeping both.
                subsumed = [i for i, t in enumerate(accepted_tokens) if t < tokens]
                if subsumed:
                    for i in reversed(subsumed):
                        del accepted[i]
                        del accepted_tokens[i]
                    accepted.append(kw)
                    accepted_tokens.append(tokens)
                    continue

                # This candidate's words are already fully covered by (or
                # identical to) something accepted — redundant, skip it.
                if any(tokens <= t for t in accepted_tokens):
                    continue

                accepted.append(kw)
                accepted_tokens.append(tokens)

            return accepted[:top_n]
        except Exception as e:
            print(f"Topic extraction error: {e}")
            return []

# Global singleton instance
retrieval_service = LLMService()
